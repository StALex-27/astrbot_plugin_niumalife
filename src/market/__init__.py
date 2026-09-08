"""
通用交易系统服务

支持的物品类别 (user['inventory'] 中 item['type'] 字段):
  - fish   - 鱼 (按 base_price * 重量倍率)
  - food   - 食物 (消耗品, 不计重量)
  - item   - 装备/材料/杂物 (持久品)

价格表: data/config/market.json
  每个物品配置: { base, weight_multiplier, volatility, category }

提供:
  - calc_sell_price(name, weight, user=...)  - 算售价 (含价格波动)
  - calc_buy_price(name)                      - 算买入价 (与商店同价)
  - can_sell(name)                            - 是否可卖
  - sell_fish_item(user, fish_name, count, mode)  - 卖鱼 (含大/小/全)
  - sell_food_item(user, food_name, count)
  - sell_generic_item(user, item_name, count)
"""
import json
import math
import random as _r
from pathlib import Path
from typing import Optional

# 加载价格表
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "config"
try:
    _MARKET_RAW = json.loads((_DATA_DIR / "market.json").read_text(encoding="utf-8"))
    MARKET: dict = {
        k: v for k, v in _MARKET_RAW.items() if not k.startswith("_")
    }
except Exception:
    MARKET = {"fish": {}, "food": {}, "item": {}}

# 加载鱼类基础数据 (鱼用 fishes.json 的 base_price 兜底)
try:
    _FISHES_RAW = json.loads((_DATA_DIR / "fishes.json").read_text(encoding="utf-8"))
    FISHES_DATA: dict = {
        k: v for k, v in _FISHES_RAW.items() if not k.startswith("_")
    }
except Exception:
    FISHES_DATA = {}

# 加载食物数据 (foods.json 提供 base_price 等)
try:
    _FOODS_RAW = json.loads((_DATA_DIR / "foods.json").read_text(encoding="utf-8"))
    FOODS_DATA: dict = {
        k: v for k, v in _FOODS_RAW.items() if not k.startswith("_")
    }
except Exception:
    FOODS_DATA = {}

# 加载物品数据 (items.json)
try:
    _ITEMS_RAW = json.loads((_DATA_DIR / "items.json").read_text(encoding="utf-8"))
    ITEMS_DATA: dict = {
        k: v for k, v in _ITEMS_RAW.items() if not k.startswith("_")
    }
except Exception:
    ITEMS_DATA = {}

# ============================================================
# 集中化注册: market.json 自动从 fishes/foods/items.json 补齐缺失条目
# 未来添加新鱼/食物/物品只需在对应的 *source*.json 加, 不再需要同时改 market.json
# ============================================================
_MERGE_DEFAULTS = {
    "fish": {"weight_multiplier": 1.0, "sell_ratio": 0.8, "volatility": 0.15},
    "food": {"weight_multiplier": 0.0, "sell_ratio": 0.8, "volatility": 0.10},
    "item": {"weight_multiplier": 0.0, "sell_ratio": 0.8, "volatility": 0.10},
}

def _auto_register_missing():
    """扫描 fishes/foods/items.json, 任何不在 market.json 的自动注册。"""
    sources = [
        ("fish", FISHES_DATA, "base_price"),
        ("food", FOODS_DATA, "price"),
        ("item", ITEMS_DATA, "price"),
    ]
    added = 0
    for cat, source_dict, price_field in sources:
        market_cat = MARKET.setdefault(cat, {})
        defaults = _MERGE_DEFAULTS[cat]
        for name, entry in source_dict.items():
            if name in market_cat:
                continue  # 已配置, 跳过
            base = entry.get(price_field, 10) if price_field else 10
            if base <= 0:
                continue
            market_cat[name] = {
                "base": base,
                **defaults,
                "_auto": True,  # 标记自动注册 (调试/管理用)
            }
            added += 1
    return added

_REGISTERED_COUNT = _auto_register_missing()


def _get_market_entry(name: str) -> Optional[dict]:
    """从 market.json 查物品, 找不到返回 None。

    鱼如果在 market.json 找不到, 但 fishes.json 里有 base_price,
    fallback 生成默认 entry (weight_multiplier=1, sell_ratio=0.8, volatility=0.15).
    这样保证所有已存在的鱼都能卖, 不需要手动维护全部 65 条鱼。
    """
    for cat in ("fish", "food", "item"):
        if name in MARKET.get(cat, {}):
            entry = MARKET[cat][name]
            return {**entry, "category": cat}

    # 鱼 fallback: 用 fishes.json 的 base_price 兜底
    if name in FISHES_DATA:
        fish = FISHES_DATA[name]
        base = fish.get("base_price", 10)
        return {
            "base": base,
            "weight_multiplier": 1.0,
            "sell_ratio": 0.8,
            "volatility": 0.15,
            "category": "fish",
            "_fallback": True,
        }
    return None


def can_sell(name: str) -> bool:
    """是否可卖。"""
    return _get_market_entry(name) is not None


def calc_sell_price(name: str, weight: float = 0, user: dict = None, rarity: str = None) -> int:
    """9/8: 计算售价 - 按钓上时估价公式 (无波动)

    公式: estimated = base × rarity_mult × weight_bonus × (1 + price_bonus/100)
    - base_price: 来自 fishes.json
    - rarity_mult: 1.5^n 升档加成 (n = final_rarity_idx - base_rarity_idx)
      ⚠️ 若不传 rarity, 视为 base_rarity (= 1.0x 升档)
    - weight_bonus: 重量相对中位数 ±10%
    - price_bonus: 装备词条 (不传, 卖鱼场景无装备上下文)

    Args:
        name: 物品名 (鱼专属, 其他物品走兜底)
        weight: 鱼的重量 (kg)
        user: 用户数据 (保留参数兼容性, 当前未使用)
        rarity: inventory entry 的升档后稀有度 (钓鱼用, 卖价按升档计算)

    Returns:
        售价金币 (最少 1)
    """
    # 鱼走 fishes.json 估价公式
    if name in FISHES_DATA:
        fish = FISHES_DATA[name]
        base_price = fish.get("base_price", 0)
        if base_price <= 0:
            return max(1, int(base_price * 0.5))
        # weight_bonus: 重量相对中位数 ±10%
        wr = fish.get("weight_range", []) or []
        if len(wr) >= 2 and wr[1] > 0 and weight > 0:
            median_w = (wr[0] + wr[1]) / 2
            if median_w > 0:
                ratio = (weight - median_w) / median_w
                ratio = max(-1.0, min(1.0, ratio))
                weight_bonus = 1.0 + ratio * 0.10
            else:
                weight_bonus = 1.0
        else:
            weight_bonus = 1.0
        # 9/8: rarity 升档加成 (升 N 档 = 1.5^N)
        if rarity:
            from ..fishing.fishing_manager import RARITY_LADDER
            base_rarity = fish.get("rarity", "common")
            try:
                base_idx = RARITY_LADDER.index(base_rarity)
                final_idx = RARITY_LADDER.index(rarity)
                boost_tier = final_idx - base_idx
                if boost_tier < 0:
                    boost_tier = 0
                rarity_mult = (1.5 ** boost_tier)
            except ValueError:
                rarity_mult = 1.0
        else:
            rarity_mult = 1.0
        return max(1, int(base_price * rarity_mult * weight_bonus))

    # 非鱼: 用 market.json base 兜底
    entry = _get_market_entry(name)
    if not entry:
        return 0
    return max(1, int(entry.get("base", 0)))


def calc_buy_price(name: str) -> int:
    """算买入价 (与商店同价)。"""
    return calc_sell_price(name, weight=0)


# === 背包操作工具 ===

def _list_inventory_by_name(user: dict, name: str, item_type: str = None) -> list[dict]:
    """列出背包中指定名字的物品 (可过滤类型)。"""
    return [
        it for it in user.get("inventory", [])
        if it.get("name") == name and (item_type is None or it.get("type") == item_type)
    ]


def _remove_from_inventory(user: dict, item: dict) -> bool:
    """从背包移除指定物品 (按引用)。"""
    try:
        user["inventory"].remove(item)
        return True
    except ValueError:
        return False


# === 鱼类卖 (支持 大/小/全部) ===

def sell_fish_items(user: dict, fish_name: str = None, count: int = None,
                    mode: str = "all") -> tuple[list[dict], int]:
    """卖鱼。返回 (卖出记录, 总金币)。"""
    fish_list = _list_inventory_by_name(user, fish_name or "", "fish")
    if not fish_list:
        return [], 0

    if fish_name:
        fish_list = [it for it in fish_list if it.get("name") == fish_name]
    if not fish_list:
        return [], 0

    # 按重量排序
    fish_list.sort(key=lambda x: -x.get("weight", 0))

    if mode == "largest":
        to_sell = fish_list[:1]
    elif mode == "smallest":
        to_sell = fish_list[-1:] if fish_list else []
    elif count is not None:
        to_sell = fish_list[:count]
    else:
        to_sell = list(fish_list)

    sold = []
    total = 0
    for fish in to_sell:
        weight = fish.get("weight", 0)
        rarity = fish.get("rarity")  # 9/8: 升档后稀有度
        price = calc_sell_price(fish["name"], weight, user, rarity=rarity)
        # 长度：优先 inventory 里的 length_cm（apply_catch 写入），缺则按 size_label 兜底
        length_cm = fish.get("length_cm")
        if length_cm is None and fish.get("size_label"):
            from ..fishing.fishing_manager import length_for_size_label, format_length, get_fish
            fish_obj = get_fish(fish["name"]) or None
            length_cm = length_for_size_label(fish["size_label"], fish_obj)
            length_str = format_length(length_cm)
        else:
            from ..fishing.fishing_manager import format_length
            length_str = format_length(length_cm) if length_cm is not None else ""
        # 9/6: 鱼 rarity 染色 (查 FISHES)
        from ..fishing.fishing_manager import FISHES, _ensure_loaded as _fl_ensure
        _fl_ensure()
        fish_def = FISHES.get(fish["name"], {})
        rarity = fish_def.get("rarity", "common")
        from modules.item import rarity_hex, RARITY_NAMES
        rarity_cn = RARITY_NAMES.get(rarity, "")
        sold.append({
            "name": fish["name"],
            "weight": weight,
            "size_label": fish.get("size_label", ""),
            "length_str": format_length(length_cm) if length_cm is not None else "",
            "gold": price,
            "rarity": rarity,
            "rarity_color": rarity_hex(rarity),
            "rarity_cn": rarity_cn,
        })
        _remove_from_inventory(user, fish)
        total += price

    return sold, total


# === 通用物品卖 (非鱼) ===

def sell_generic_items(user: dict, name: str, count: int = None) -> tuple[list[dict], int]:
    """卖通用物品 (food / item)。"""
    items = _list_inventory_by_name(user, name)
    if not items:
        return [], 0

    if count is None or count >= len(items):
        to_sell = list(items)
    else:
        to_sell = items[:count]

    sold = []
    total = 0
    for item in to_sell:
        qty = item.get("quantity", 1)
        price_each = calc_sell_price(name, weight=0, user=user)
        # 食物/物品按基础价 (无重量)
        price = price_each * qty
        # 9/6: 物品 rarity 染色 (查 ITEMS)
        from modules.item import ITEMS, rarity_hex, RARITY_NAMES
        item_def = ITEMS.get(name, {})
        rarity = item_def.get("rarity", "common")
        rarity_cn = RARITY_NAMES.get(rarity, "")
        sold.append({
            "name": name,
            "quantity": qty,
            "gold": price,
            "rarity": rarity,
            "rarity_color": rarity_hex(rarity),
            "rarity_cn": rarity_cn,
        })
        _remove_from_inventory(user, item)
        total += price

    return sold, total


# === 统一入口 ===

def sell_items(user: dict, name: str = None, count: Optional[int] = None,
               mode: str = "all") -> tuple[list[dict], int, str]:
    """统一卖入口。

    Args:
        user: 用户数据
        name: 物品名 (None = 卖全部可卖物)
        count: 数量 (None = 全部, int = 前 N 个)
        mode: all / largest / smallest (仅鱼有效)

    Returns:
        (卖出记录列表, 总金币, 错误信息)
    """
    if name is None:
        # 卖背包里所有可卖物
        sold_all = []
        total = 0
        for it in list(user.get("inventory", [])):
            n = it.get("name")
            if n and can_sell(n):
                if it.get("type") == "fish":
                    sold, gold = sell_fish_items(user, n, count=None, mode="all")
                else:
                    sold, gold = sell_generic_items(user, n, count=None)
                sold_all.extend(sold)
                total += gold
        return sold_all, total, ""

    if not can_sell(name):
        return [], 0, f"❌ [{name}] 不可卖 (不在市场表)"

    # 判断类型走不同路径
    if name in FISHES_DATA:
        sold, total = sell_fish_items(user, name, count, mode)
        return sold, total, ""
    else:
        # 通用物品 (food/item)
        sold, total = sell_generic_items(user, name, count)
        return sold, total, ""


def sell_all_sellable(user: dict) -> tuple[list[dict], int]:
    """卖背包里所有可卖物品。返回 (记录, 总金币)。"""
    sold_all = []
    total = 0
    for it in list(user.get("inventory", [])):
        n = it.get("name")
        if n and can_sell(n):
            if it.get("type") == "fish":
                sold, gold = sell_fish_items(user, n, count=None, mode="all")
            else:
                sold, gold = sell_generic_items(user, n, count=None)
            sold_all.extend(sold)
            total += gold
    return sold_all, total


def list_sellable_inventory(user: dict) -> tuple[list[dict], int, int]:
    """列出背包里所有可卖物品（不执行售卖）。

    Returns:
        (items_summary, total_count, total_gold)

        items_summary: [{
            'name': str,
            'type': 'fish' | 'food' | 'item',
            'category': 同上,
            'count': int,           # 总数量 (鱼按条数, 物品按 quantity 求和)
            'weight': float,        # 仅鱼, 总重量
            'unit_price': int,      # 单价金币
            'total_gold': int,      # 总价值
            'rarity': str,          # 9/6: 稀有度 (common/uncommon/rare/epic/legendary/mythic)
            'rarity_color': str,    # 9/6: hex 颜色 (#RRGGBB), UI 渲染边框/文字
        }]
    """
    summary = []
    total_count = 0
    total_gold = 0
    seen = {}  # name -> aggregate

    # 9/6: 懒加载 FISHES + ITEMS 用于查 item rarity
    # 注意: market 是 src.market 子包, 用绝对导入避免 relative import 跨包失败
    from fishing.fishing_manager import FISHES, _ensure_loaded
    _ensure_loaded()
    from modules.item import ITEMS, rarity_hex

    for it in user.get("inventory", []):
        n = it.get("name", "")
        t = it.get("type", "")
        if not n or not can_sell(n):
            continue
        if n not in seen:
            # 9/6: 查 rarity (鱼查 FISHES, 物品查 ITEMS)
            if t == "fish":
                fish_def = FISHES.get(n, {})
                rarity = fish_def.get("rarity", "common")
            else:
                item_def = ITEMS.get(n, {})
                rarity = item_def.get("rarity", "common")
            from modules.item import RARITY_NAMES
            seen[n] = {
                "name": n,
                "type": t,
                "count": 0,
                "weight": 0.0,
                "unit_price": calc_sell_price(n, weight=0, user=user),
                "total_gold": 0,
                "rarity": rarity,
                "rarity_color": rarity_hex(rarity),
                "rarity_cn": RARITY_NAMES.get(rarity, ""),
            }
        agg = seen[n]
        if t == "fish":
            # 鱼每条独立计费 (不同重量价格不同)
            w = it.get("weight", 0)
            p = calc_sell_price(n, weight=w, user=user)
            agg["count"] += 1
            agg["weight"] += w
            agg["total_gold"] += p
        else:
            # 通用物品, 每件单价相同
            q = it.get("quantity", 1)
            agg["count"] += q
            agg["total_gold"] += calc_sell_price(n, weight=0, user=user) * q

    for agg in seen.values():
        total_count += agg["count"]
        total_gold += agg["total_gold"]
        summary.append(agg)

    # 按总价值降序
    summary.sort(key=lambda x: -x["total_gold"])
    return summary, total_count, total_gold


def list_stock_holdings(user: dict) -> tuple[list[dict], int]:
    """列出用户股票持仓 (静态快照, 不含当前价)。

    价格随 tick 变化, 详细市值请用 /股市 持股。

    Returns:
        (holdings, total_cost)

        holdings: [{
            'code': str,
            'name': str,
            'quantity': int,
            'cost_price': int,
            'cost_total': int,    # 持股总成本
        }]
    """
    holdings_raw = user.get("stock_holdings", {})
    if not holdings_raw:
        return [], 0

    holdings = []
    total_cost = 0
    for code, info in holdings_raw.items():
        qty = info.get("quantity", 0)
        if qty <= 0:
            continue
        cost = info.get("cost_price", 0)
        cost_total = qty * cost
        holdings.append({
            "code": code,
            "name": info.get("name", code),
            "quantity": qty,
            "cost_price": cost,
            "cost_total": cost_total,
        })
        total_cost += cost_total

    holdings.sort(key=lambda x: -x["cost_total"])
    return holdings, total_cost


def list_other_assets(user: dict) -> tuple[list[dict], int]:
    """列出其他可出售资产 (如房契/地段/股票期权等)。

    目前只列出已实现的: residence_houses + unlocked_spots

    Returns:
        (assets, total_value)

        assets: [{
            'type': 'residence' | 'spot' | 'item_equip',
            'name': str,
            'detail': str,
            'sell_price': int,     # 当前售价 (0 = 不可卖)
        }]
    """
    assets = []
    total = 0

    # 房产 (residence)
    houses = user.get("houses", [])
    for h in houses:
        h_name = h if isinstance(h, str) else h.get("name", "?")
        # 房产当前不在 market 表里, 兜底按固定价
        price = 500  # 默认 500 金币/处
        assets.append({
            "type": "residence",
            "name": h_name,
            "detail": "🏠 房产",
            "sell_price": price,
        })
        total += price

    # 钓鱼解锁的地点 (永久解锁的钓鱼点)
    unlocked = user.get("unlocked_spots", [])
    if isinstance(unlocked, list):
        for s in unlocked:
            if isinstance(s, dict):
                spot_name = s.get("name", "?")
                purchased = s.get("purchased", False)
                if purchased:
                    price = 200
                    assets.append({
                        "type": "spot",
                        "name": spot_name,
                        "detail": "🎣 钓鱼点 (永久)",
                        "sell_price": price,
                    })
                    total += price

    return assets, total
