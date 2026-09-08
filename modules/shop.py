"""
商店系统 V3 - 统合商店模块

9/4重构:
- 取消基础商店/公司商店分离
- 取消固定/随机商品池配置
- 所有可售卖物品 (price>0) 统一进商店
- 按 4 大分类展示: 食物 / 药品 / 装备 / 渔具
- /商店 无参数: 整合页面, 每类随机 6 种 (2x3)
- /商店 <分类>: 完整列表 (按 tier 排序)
- /商店 买 <物品名> [数量]: 购买
"""
import random
from typing import Optional, Tuple, List

from .constants import ITEMS
from .skills import get_skill_level as _get_skill_level, get_skill_exp_rate as _get_skill_exp_rate
from ..src.data.content_registry import ContentRegistry


# ============================================================
# 分类筛选
# ============================================================

# 9/7 命名统一: 全部加 fishing_ 前缀
FISHING_SUBS = {"fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_reel", "fishing_bait", "fishing_lure", "fishing_waders"}
FISHING_SLOTS = {"fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_bait", "fishing_reel", "fishing_lure", "fishing_waders"}
FISHING_CATEGORIES = {"tool"}  # 渔具有些 category=tool

CATEGORY_NAMES = {
    "food": "食物",
    "props": "道具",
    "equip": "装备",
    "fishing": "渔具",
    "daily": "日用品",
}

CATEGORY_EMOJI = {
    "food": "🍞",
    "props": "🧪",
    "equip": "🎒",
    "fishing": "🎣",
    "daily": "🧻",
}


# ============================================================
# Effects 格式化
# ============================================================

SIZE_LABELS = {
    "tiny": "微型", "small": "小型", "medium": "中型",
    "large": "大型", "huge": "巨型", "giant": "超巨型", "titan": "泰坦级",
}
HABITAT_LABELS = {"pond": "池", "river": "河", "reservoir": "库", "coast": "海岸", "shallow_sea": "浅海", "deep_sea": "深海"}
DIET_LABELS = {"carnivore": "肉", "herbivore": "草", "omnivore": "杂"}
FOOD_ATTR_LABELS = {"strength": "体力", "health": "健康", "satiety": "饱食", "mood": "心情", "energy": "精力"}

# 优先级 + 显示标签
EFFECTS_PRIORITY = [
    ("target_size_weights", "尺寸"),
    ("habitat_filter", "水域"),
    ("target_diet", "食性"),
    ("load_capacity_max", "承载"),
    ("max_hook_slots", "钩槽"),
    ("fishing_bonus", "中鱼"),
    ("habitat_bonus", "水域"),
    ("rare_bonus", "稀有"),
    ("duration_reduce", "收竿"),
]


def format_effects_short(effects: dict, max_len: int = 70) -> str:
    """格式化 effects 为短文本

    Args:
        effects: 物品 effects 字典
        max_len: 最大字符数
    """
    if not effects:
        return ""

    parts = []
    for key, label in EFFECTS_PRIORITY:
        if key not in effects:
            continue
        v = effects[key]
        if key == "target_size_weights" and isinstance(v, dict):
            sz = ",".join(f"{SIZE_LABELS.get(k, k)}{int(w*100)}%" for k, w in v.items())
            parts.append(f"{label}:{sz}")
        elif key == "habitat_filter" and isinstance(v, list):
            parts.append(f"{label}:{'.'.join(HABITAT_LABELS.get(h, h) for h in v)}")
        elif key == "habitat_bonus" and isinstance(v, dict):
            # 鱼竿: {reservoir: 0.1} → "水域:库+10%"
            parts.append(f"水域:" + ",".join(f"{HABITAT_LABELS.get(h, h)}+{int(w*100)}%" for h, w in v.items()))
        elif key == "target_diet" and isinstance(v, list):
            parts.append(f"{label}:{'.'.join(DIET_LABELS.get(d, d) for d in v)}")
        elif key == "load_capacity_max":
            parts.append(f"{label}{v}kg")
        elif key == "max_hook_slots":
            parts.append(f"{label}{int(v)}")
        elif key == "duration_reduce":
            if v > 0:
                parts.append(f"{label}-{int(v)}")
        elif isinstance(v, float) and v > 0:
            parts.append(f"{label}+{int(v*100)}%")
        elif isinstance(v, (int, float)) and v > 0:
            parts.append(f"{label}+{v}")
        # 长度控制
        if len(" · ".join(parts)) > max_len:
            break

    # 食物/药品属性
    if not parts:
        food_attrs = []
        for attr in ["strength", "health", "satiety", "mood", "energy"]:
            if attr in effects:
                food_attrs.append(f"+{effects[attr]}{FOOD_ATTR_LABELS.get(attr, attr)}")
        if food_attrs:
            parts.extend(food_attrs)

    return " · ".join(parts)[:max_len]


# ============================================================
# 解锁条件检查
# ============================================================

def get_player_level(user: dict) -> int:
    """计算玩家总等级: 基于属性 / 技能 / 累计"""
    # 1. 属性等级
    attrs = user.get("attributes", {})
    attr_level = max([v // 20 for v in attrs.values()] + [0])
    # 2. 技能等级 (从 skill_exp 算)
    skills = user.get("skills", {})
    skill_level = max(list(skills.values()) + [0])
    # 3. 总等级 = max(属性, 技能)
    return max(attr_level, skill_level, 1)


def get_user_skill_level(user: dict, skill_name: str) -> int:
    """获取用户某技能等级 (兼容 old/new)

    9/4: 从 skills.json 读 exp_rate (如 钓鱼 = fishing_30), 让曲线生效
    """
    # 新格式 skill_exp
    skill_exp = user.get("skill_exp", {})
    if skill_name in skill_exp:
        # 9/4: 按 skills.json 的 exp_rate 查等级, 不再简化 // 100
        exp_rate = _get_skill_exp_rate(skill_name)
        return _get_skill_level(skill_exp[skill_name], exp_rate)
    # 旧格式 skills[skill_name]
    skills = user.get("skills", {})
    return int(skills.get(skill_name, 0))


def check_unlock_requirements(user: dict, item_info: dict) -> tuple[bool, str]:
    """检查用户是否满足物品解锁条件

    Args:
        user: 用户数据
        item_info: 物品配置 dict

    Returns:
        (unlocked, reason): (True, "") 解锁 / (False, "原因") 锁定
    """
    # 9/7: ContentRegistry.to_dict() 把 unlock_requirements 存在 extra 子 dict,
    #       必须先扁平化以兼容 item_info["unlock_requirements"] 直接访问
    req = item_info.get("unlock_requirements") or item_info.get("extra", {}).get("unlock_requirements") or {}
    if not req:
        return True, ""

    # 1. 玩家等级
    if "min_player_level" in req:
        need = req["min_player_level"]
        cur = get_player_level(user)
        if cur < need:
            return False, f"需要玩家等级 Lv.{need}（当前 Lv.{cur}）"

    # 2. 钓鱼技能等级
    if "min_fishing_level" in req:
        need = req["min_fishing_level"]
        cur = get_user_skill_level(user, "钓鱼")
        if cur < need:
            return False, f"需要钓鱼技能 Lv.{need}（当前 Lv.{cur}）"

    # 3. 苦力技能等级
    if "min_labor_level" in req:
        need = req["min_labor_level"]
        cur = get_user_skill_level(user, "苦力")
        if cur < need:
            return False, f"需要苦力技能 Lv.{need}（当前 Lv.{cur}）"

    # 4. 公司好感度
    if "min_company_favor" in req:
        need = req["min_company_favor"]
        favor = user.get("company_favorability", {})
        max_favor = max(favor.values()) if favor else 0
        if max_favor < need:
            return False, f"需要公司好感度 {need}（当前最高 {max_favor}）"

    # 5. 称号
    if "required_title" in req:
        need = req["required_title"]
        titles = user.get("titles", [])
        if need not in titles:
            return False, f"需要称号「{need}」"

    return True, ""


def _is_fishing_item(v: dict) -> bool:
    """判断是否渔具: subcategory 或 slot 在 FISHING_SUBS/SLOTS 即算渔具"""
    if v.get("subcategory") in FISHING_SUBS:
        return True
    if v.get("slot") in FISHING_SLOTS:
        return True
    return False


def _classify_item(v: dict) -> Optional[str]:
    """返回物品分类 key: food/props/equip/fishing/daily/None (不可售卖)

    9/4晚: 道具栏只收纳 药品 + 附魔券
    优先级: 渔具 > 食物 > 道具 > 装备
    """
    if v.get("price", 0) <= 0:
        return None  # 无价/不可售卖
    if _is_fishing_item(v):
        return "fishing"
    cat = v.get("category", "")
    if cat == "food":
        return "food"
    # 9/4晚: 道具栏只收纳 药品 + 附魔券
    if cat == "medicine":
        return "props"
    if cat == "enchant":
        return "props"
    if cat == "daily":
        return "daily"
    # 通用装备: slot in (clothing/head/accessory/tool/phone) 或 category=equipment
    slot = v.get("slot", "")
    if cat == "equipment":
        return "equip"
    if slot in ("clothing", "head", "accessory", "tool", "phone", "neck", "waist"):
        return "equip"
    return None


def get_sellable_items() -> dict:
    """返回 {category: [(item_id, item_info), ...]} 所有可售卖物品

    按 tier 排序

    9/6: 改用 ContentRegistry.instance().filter_by_action("sell") 替代遍历 ITEMS dict。
    ContentRegistry 自动按 category/slot/price 推导 actions (price>0 即可 sell)。
    9/4晚: 道具栏只收纳 药品 + 附魔券 (medicine/enchant → "props" 桶)
    """
    groups = {"food": [], "props": [], "equip": [], "fishing": [], "daily": []}
    # 9/6: 从 ContentRegistry 取所有可卖物品 (ContentDef), 转回 dict 格式给旧调用方
    reg = ContentRegistry.instance()
    sellable = reg.filter_by_action("sell", content_type="item")
    for d in sellable:
        item = d.to_dict()
        # 9/4晚: 道具栏合并 (medicine + enchant → "props")
        cat = _classify_item(item)
        if not cat:
            continue
        # ContentDef 用 tuple of tuple 存 effects, 转回 dict 给调用方
        groups[cat].append((d.content_id, item))
    # 按 tier 排序
    for cat in groups:
        groups[cat].sort(key=lambda x: (x[1].get("tier", 1), x[1].get("price", 0)))
    return groups


# ============================================================
# 商店刷新 (随机抽取)
# ============================================================

SHOP_REFRESH_STATE = {}  # {category: [(item_id, ts), ...]}


def refresh_category_items(category: str, count: int = 6, seed: Optional[int] = None) -> List[Tuple[str, dict]]:
    """随机抽取某个分类的 count 个物品 (按 tier 均匀抽样)

    策略: 按 tier 权重, 每个 tier 抽 1-2 个, 保证展示多样性
    """
    all_items = get_sellable_items().get(category, [])
    if not all_items:
        return []
    if len(all_items) <= count:
        return all_items.copy()

    # 按 tier 分桶
    by_tier = {}
    for item_id, item in all_items:
        tier = item.get("tier", 1)
        by_tier.setdefault(tier, []).append((item_id, item))

    tiers = sorted(by_tier.keys())
    result = []

    rng = random.Random(seed) if seed is not None else random.Random()

    # 第一轮: 每个 tier 抽 1 个
    for tier in tiers:
        if len(result) >= count:
            break
        if by_tier[tier]:
            pick = rng.choice(by_tier[tier])
            result.append(pick)
            by_tier[tier].remove(pick)

    # 第二轮: 仍不够, 随机补齐
    if len(result) < count:
        remaining = [x for tier_items in by_tier.values() for x in tier_items if x not in result]
        rng.shuffle(remaining)
        for pick in remaining:
            if len(result) >= count:
                break
            result.append(pick)

    return result[:count]


def get_shop_display_items(plugin=None, seed: Optional[int] = None) -> dict:
    """获取整合商店页面展示的物品

    每分类随机 6 个
    """
    display = {}
    for cat in ["food", "props", "equip", "fishing"]:
        display[cat] = refresh_category_items(cat, count=6, seed=seed)
    return display


# ============================================================
# 整合商店页面渲染
# ============================================================

def format_shop_unified(plugin=None, user: Optional[dict] = None) -> str:
    """整合商店首页 - 4 分类各 6 种 (2 行 3 列)"""
    lines = [
        "═══════════════════════════════════════════",
        "        「 🏪 商 店 」",
        "═══════════════════════════════════════════",
    ]
    if user:
        lines.append(f"💰 金币: ¥{int(user.get('gold', 0))}")
        lines.append("")

    display = get_shop_display_items(plugin)
    for cat_key, items in display.items():
        if not items:
            continue
        cat_name = CATEGORY_NAMES[cat_key]
        cat_emoji = CATEGORY_EMOJI[cat_key]
        lines.append(f"── {cat_emoji} {cat_name} ──")
        lines.extend(_format_grid(items, cols=3))
        lines.append("")

    lines.append("═══════════════════════════════════════════")
    lines.append("📋 /商店 <分类>   查看完整列表")
    lines.append("   /商店 买 <物品名> [数量]   购买")
    lines.append("   分类: 食物 / 道具 / 装备 / 渔具 / 日用品")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


def _format_grid(items: list, cols: int = 3) -> list:
    """2D 网格格式化 (默认 2 行 3 列)

    Returns: 字符串行列表
    """
    if not items:
        return ["  (无)"]

    lines = []
    row = []
    for item_id, item in items:
        name = item.get("name", item_id)
        price = item.get("price", 0)
        rarity = item.get("rarity", "common")
        rarity_dot = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}.get(rarity, "⚪")
        row.append(f"{rarity_dot}{name} ¥{price}")
        if len(row) >= cols:
            lines.append("  " + "  |  ".join(row))
            row = []
    if row:
        lines.append("  " + "  |  ".join(row))
    return lines


def format_shop_category(category=None, plugin=None, user: dict = None, tier_groups: list = None, page_title: str = "") -> str:
    """完整展示某个分类 (按 tier 排序)

    Args:
        category: 分类 key (兼容旧调用, 可选)
        plugin: 兼容旧签名
        user: 用户 (用于昵称/金币等)
        tier_groups: 已按 tier 分组的物品 (新调用) - 优先使用
        page_title: 页面标题
    """
    lines = [
        "═══════════════════════════════════════════",
    ]
    if page_title:
        lines.append(f"  📦 「 {page_title} 」")
    else:
        cat_name = CATEGORY_NAMES.get(category, category)
        cat_emoji = CATEGORY_EMOJI.get(category, "📦")
        lines.append(f"  {cat_emoji} 「 {cat_name} 商店 」")
    lines.extend([
        "═══════════════════════════════════════════",
    ])

    # 优先用 tier_groups (新调用方式)
    if tier_groups:
        for grp in tier_groups:
            tier = grp.get("tier", 1)
            items = grp.get("item_list", [])
            lines.append(f"── T{tier} ──")
            for card in items:
                if isinstance(card, dict):
                    nm = card.get("name", "?")
                    pr = card.get("price", 0)
                    lines.append(f"  {nm} ¥{pr}")
                else:
                    lines.append(f"  {card}")
        lines.append("═══════════════════════════════════════════")
        return "\n".join(lines)

    # fallback: 用 category 查
    all_items = get_sellable_items().get(category, [])
    if not all_items:
        return f"❌ 无该分类商品: {category}"

    lines.append(f"  共 {len(all_items)} 件商品")
    lines.append("═══════════════════════════════════════════")

    # 按 tier 分组
    by_tier = {}
    for item_id, item in all_items:
        tier = item.get("tier", 1)
        by_tier.setdefault(tier, []).append((item_id, item))

    for tier in sorted(by_tier.keys()):
        lines.append(f"── T{tier} ──")
        lines.extend(_format_grid(by_tier[tier], cols=3))
        lines.append("")

    lines.append("═══════════════════════════════════════════")
    lines.append(f"📋 /商店 买 <物品名> [数量]")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines)


# ============================================================
# 购买逻辑 (兼容旧 buy_item 接口)
# ============================================================

def buy_item(
    plugin, user: dict, item_id: str, quantity: int = 1
) -> tuple[bool, str]:
    """购买物品 - 9/4 重构: 不依赖店铺分类, 任何可售卖物品都买

    Args:
        plugin: 插件实例 (兼容旧接口)
        user: 用户数据
        item_id: 物品 ID
        quantity: 数量

    Returns:
        tuple[bool, str]: (成功, 消息)
    """
    item = ITEMS.get(item_id)
    if not item:
        return False, "❌ 物品不存在"

    if item.get("price", 0) <= 0:
        return False, "❌ 该物品不可购买"

    price = item.get("price", 0) * quantity
    if user.get("gold", 0) < price:
        return False, f"❌ 金币不足，需要 {price} 金币，你只有 {int(user.get('gold', 0))}"

    # 加 inventory
    inventory = user.get("inventory", [])
    is_food = item.get("category") == "food" or item.get("category") == "medicine" or item.get("category") == "daily"
    is_stackable = item.get("stackable", False) or is_food  # 食物药品默认可堆叠

    if is_stackable:
        # 堆叠: 找已有同名物品
        stacked = False
        for inv_item in inventory:
            if inv_item.get("id") == item_id:
                inv_item["quantity"] = inv_item.get("quantity", 1) + quantity
                # 补全字段
                for k in ["category", "type", "effects", "name"]:
                    if k not in inv_item:
                        inv_item[k] = item.get(k)
                stacked = True
                break
        if not stacked:
            inventory.append({
                "id": item_id,
                "name": item.get("name"),
                "category": item.get("category"),
                "type": item.get("type"),
                "quantity": quantity,
                "effects": item.get("effects", {}),
            })
    else:
        # 装备/渔具: 不堆叠, 多个就多个 entry
        # 9/4晚: 补全 slot/category/type 字段, 防止后续 equip_item 误判
        # 9/4晚: 加 rarity + rarity_mult (持久化词条抽取结果)
        # 9/4晚: 消耗性鱼饵无 rarity (保持原样), 渔具和拟饵加 rarity="common"
        from .entry_lib import make_inventory_entry

        # 9/7 命名统一: 全部加 fishing_ 前缀
        is_consumable_bait = (
            item.get("slot") == "fishing_bait"
            and item.get("subcategory") != "fishing_lure"
            and item.get("consumable", False)
        )

        for _ in range(quantity):
            if is_consumable_bait:
                # 消耗性鱼饵: 无 rarity, 旧字段
                inventory.append({
                    "id": item_id,
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "type": item.get("type"),
                    "slot": item.get("slot"),
                    "base_effects": item.get("base_effects", {}),
                    "consumable": item.get("consumable", False),
                })
            else:
                # 渔具/拟饵/通用装备: 商店默认 common, 持久化 rarity_mult
                entry = make_inventory_entry(item_id, "common")
                entry["name"] = item.get("name")
                entry["category"] = item.get("category")
                entry["type"] = item.get("type")
                entry["slot"] = item.get("slot")
                entry["consumable"] = item.get("consumable", False)
                inventory.append(entry)

    user["inventory"] = inventory
    user["gold"] = user.get("gold", 0) - price

    return True, f"✅ 购买 {item.get('name')} ×{quantity} 成功 (花费 {price} 金币)"


# ============================================================
# 兼容旧接口
# ============================================================

def get_shop_items(plugin, shop_id: str) -> tuple[list, list]:
    """兼容旧接口: 返回固定/随机"""
    return [], get_sellable_items().get(shop_id, [])[:20]


# 保留旧 SHOPS 字典 (防止外部 import 报错, 但不再使用)
SHOPS = {}
