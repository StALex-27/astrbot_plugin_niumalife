"""
9/7: 物品详情查询 (背包 <物品名>) — 匹配逻辑 + 视图组装
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from ...modules.item import ITEMS, RARITY_NAMES, RARITY_HEX_COLORS, rarity_hex
from ...modules.templates import CardType
from ..data.user_view import view_for_item_detail_card
from ..fishing.fishing_manager import FISHES, _ensure_loaded

if TYPE_CHECKING:
    pass


# 9/7: 装备 subcategory 列表 (决定"🎣 渔具" vs "👕 装备")
# 9/7 统一: subcategory 与 slot 对齐, 移除 fishing_rod/float/reel 等不一致名
FISHING_SUBCATEGORIES = frozenset({
    "fishing_rod", "line", "hook", "fishing_float", "fishing_reel", "bait", "lure", "waders"
})


def _strip_rarity_prefix(query: str) -> str:
    """9/7: 去除用户输入中的稀有度前缀 (如 "优秀竹竿" → "竹竿")

    返回去前缀后的字符串; 如果 query 不含已知稀有度前缀, 返回原 query.
    "普通" 不剥离 (普通装备不显示前缀, 用户不会输"普通竹竿").
    """
    if not query:
        return query
    # RARITY_NAMES 是 dict {common, ..., mythic} → 中文名
    SKIP_RARITY_CN = {"普通"}  # 9/7: 普通装备不带前缀, 防止误剥离 "普通xx" → "xx"
    for cn_name in RARITY_NAMES.values():
        if cn_name in SKIP_RARITY_CN or not cn_name:
            continue
        if query.startswith(cn_name):
            stripped = query[len(cn_name):].strip()
            if stripped:
                return stripped
    return query


def _norm(s: str) -> str:
    """标准化: 去除空格 + 全/半角括号统一."""
    if not s:
        return ""
    s = s.strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace(" ", "")
    return s


def _resolve_item(query: str, user: dict) -> Optional[dict]:
    """从背包中查找物品 (按 ID 或 name 匹配).

    Returns:
        dict 包含:
            - 'source': 'inventory'
            - 'id': 物品 ID
            - 'name': 物品显示名
            - 'quantity': 数量
            - 'entries': [所有匹配的 inventory entries] (鱼不合并)
            - 'is_fish': bool
            - 'info': ITEMS 字典里的源数据 (鱼则 FISHES)
            - 'inventory_entry': 第一个 entry (用于显示附魔等)
    """
    q = _norm(query).lower()
    if not q:
        return None

    inventory = user.get("inventory", [])

    # 收集所有 (id, name) 选项 (用于 INVENTORY 匹配)
    by_id = {}
    by_name = {}
    for entry in inventory:
        eid = entry.get("id") or entry.get("name")
        ename = entry.get("name", "")
        if not eid:
            continue
        by_id.setdefault(eid, []).append(entry)
        if ename:
            by_name.setdefault(ename, []).append(entry)

    # 1. 精确匹配 ID
    if q in by_id:
        entries = by_id[q]
        return _build_from_entries(entries, source="inventory")

    # 2. 精确匹配 name
    if q in by_name:
        entries = by_name[q]
        return _build_from_entries(entries, source="inventory")

    # 3. 大小写不敏感匹配 name
    for k, entries in by_name.items():
        if _norm(k).lower() == q:
            return _build_from_entries(entries, source="inventory")

    # 3.5 去稀有度前缀匹配 (用户输 "优秀竹竿" → 实际 entry.name="竹竿")
    strip_query = _strip_rarity_prefix(q)
    if strip_query and strip_query != q:
        if strip_query in by_id:
            return _build_from_entries(by_id[strip_query], source="inventory")
        if strip_query in by_name:
            return _build_from_entries(by_name[strip_query], source="inventory")
        for k, entries in by_name.items():
            if _norm(k).lower() == strip_query:
                return _build_from_entries(entries, source="inventory")

    # 4. 鱼 - 在 FISHES 里找 (仅 fish entry 不存在时)
    _ensure_loaded()
    if q in FISHES:
        return _build_fish(q, FISHES[q], inventory)

    # 5. 鱼名模糊匹配 (中文)
    for fish_name, fish_def in FISHES.items():
        if _norm(fish_name).lower() == q:
            return _build_fish(fish_name, fish_def, inventory)

    return None


def _build_from_entries(entries: list, source: str) -> dict:
    """从 inventory entries 构建结果."""
    first = entries[0]
    eid = first.get("id") or first.get("name")
    name = first.get("name") or eid

    # 鱼类型合并
    if first.get("type") == "fish":
        # 鱼不合并 quantity, 因为每条 unique
        return {
            "source": source,
            "id": eid,
            "name": name,
            "quantity": len(entries),
            "entries": entries,
            "is_fish": True,
            "info": FISHES.get(name, {}),
            "inventory_entry": first,
        }

    # 普通物品 - 堆叠合并
    qty = sum(e.get("quantity", 1) for e in entries)
    info = ITEMS.get(eid, {})
    return {
        "source": source,
        "id": eid,
        "name": info.get("name") or name,
        "quantity": qty,
        "entries": entries,
        "is_fish": False,
        "info": info,
        "inventory_entry": first,
    }


def _build_fish(name: str, fish_def: dict, inventory: list) -> dict:
    """从 FISHES 构建鱼结果."""
    # 查找玩家是否持有此鱼
    fish_entries = [e for e in inventory
                    if e.get("type") == "fish" and e.get("name") == name]
    qty = len(fish_entries)
    return {
        "source": "fish_def",
        "id": name,
        "name": name,
        "quantity": qty,
        "entries": fish_entries,
        "is_fish": True,
        "info": fish_def,
        "inventory_entry": fish_entries[0] if fish_entries else None,
    }


def _format_effects_short(effects: dict) -> list:
    """格式化 effects 字典为 stats_rows."""
    if not effects:
        return []
    rows = []
    # 字段中文映射
    label_map = {
        "fishing_bonus_pct": "🎣 中鱼率",
        "rare_bonus_pct": "⭐ 稀有率",
        "tier_bonus": "🏆 稀有加成",
        "weight_capacity": "⚖️ 承重",
        "strength": "💪 强度",
        "capacity_kg": "⚖️ 承重",
        "slot_lock": "🔒 锁定槽位",
        "boost": "📈 强化",
        "satiety_restore": "🍖 饱腹",
        "mood_restore": "😊 心情",
        "duration_min": "⏱️ 时长",
        "unlock_level": "🔓 解锁等级",
        "tier": "📊 档位",
        "diet": "🍴 食性",
        "habitat": "🌊 水域",
        "rarity": "🌟 稀有度",
    }
    for k, v in effects.items():
        label = label_map.get(k, k)
        if isinstance(v, (int, float)):
            if v >= 1:
                value = f"+{v}" if v > 0 else str(v)
            else:
                value = f"+{int(v * 100)}%" if v < 1 else str(v)
            value = str(v) if not isinstance(v, float) else (f"{v:.2f}" if abs(v) < 1 else str(int(v)))
        elif isinstance(v, list):
            value = ", ".join(str(x) for x in v)
        elif isinstance(v, dict):
            value = ", ".join(f"{kk}+{vv}" for kk, vv in v.items())
        else:
            value = str(v)
        rows.append({"label": label, "value": value})
    return rows


def _format_enchant_entries(effects: dict, inventory_entry: dict = None) -> list:
    """从 effects 字典提取词条 (用于详情卡片)."""
    if not effects:
        return []
    entries = []
    # 简单的词条展示: 直接遍历
    color_map = {
        "fishing_bonus_pct": "#7bed9f",
        "rare_bonus_pct": "#ffa726",
        "tier_bonus": "#c586c0",
        "weight_capacity": "#4fc3f7",
    }
    label_map = {
        "fishing_bonus_pct": "中鱼率提升",
        "rare_bonus_pct": "稀有鱼概率",
        "tier_bonus": "稀有度提升",
        "weight_capacity": "承重提升",
    }
    for k, v in effects.items():
        label = label_map.get(k, k)
        # 描述
        if isinstance(v, (int, float)):
            if v < 1:
                desc = f"+{int(v * 100)}%"
            else:
                desc = f"+{v}"
        else:
            desc = str(v)
        entries.append({
            "name": label,
            "desc": desc,
            "color": color_map.get(k, "#ffa726"),
        })
    return entries


def build_item_detail_view(user: dict, item_result: dict) -> dict:
    """构建物品详情卡片 view."""
    is_fish = item_result["is_fish"]
    info = item_result["info"]
    first_entry = item_result.get("inventory_entry") or {}

    # 基本字段
    rarity = info.get("rarity") or first_entry.get("rarity") or "common"
    if first_entry.get("rarity") and first_entry.get("rarity") != info.get("rarity"):
        # 附魔后改变 (优先用 entry 的)
        rarity = first_entry["rarity"]
    name = item_result["name"]
    emoji = info.get("emoji", "🐟" if is_fish else "📦")
    quantity = item_result["quantity"]

    # 类型中文
    if is_fish:
        item_type_cn = "🐟 鱼类"
        subcategory = info.get("size_class", "")
    else:
        cat = info.get("category", "item")
        sub = info.get("subcategory", "")
        type_map = {
            "food": "🍞 食物",
            "props": "🧪 道具",
            "equipment": "🎣 渔具" if sub in FISHING_SUBCATEGORIES else "👕 装备",
            "tool": "🔧 工具",
            "fishing": "🎣 渔具",  # 兼容老数据
            "daily": "🏠 日用品",
        }
        item_type_cn = type_map.get(cat, "📦 物品")
        subcategory = info.get("subcategory") or info.get("slot") or ""

    # 描述
    desc = info.get("desc") or ""

    # 属性行
    stats_rows = []
    if not is_fish:
        # 装备/工具: 价格、解锁、效果
        if info.get("price"):
            stats_rows.append({"label": "💰 售价", "value": f"{info['price']} 金币"})
        if info.get("unlock_level") is not None and info.get("unlock_level", 0) > 0:
            stats_rows.append({"label": "🔓 解锁", "value": f"等级 {info['unlock_level']}"})
        if info.get("tier"):
            stats_rows.append({"label": "📊 档位", "value": f"T{info['tier']}"})
        if info.get("satiety_restore"):
            stats_rows.append({"label": "🍖 饱腹", "value": f"+{info['satiety_restore']}"})
        if info.get("mood_restore"):
            stats_rows.append({"label": "😊 心情", "value": f"+{info['mood_restore']}"})
        # 其他属性 (effects 展开)
        base_effects = info.get("effects", {})
        if base_effects:
            stats_rows.extend(_format_effects_short(base_effects))

    # 鱼 - 体重, 水域, 价格, 食性
    if is_fish:
        stats_rows.append({"label": "📊 档位", "value": f"T{info.get('tier', '?')}"})
        if info.get("habitat"):
            stats_rows.append({"label": "🌊 水域", "value": ", ".join(info["habitat"])})
        if info.get("diet"):
            diet_map = {"carnivore": "肉食", "herbivore": "草食", "omnivore": "杂食"}
            stats_rows.append({"label": "🍴 食性", "value": diet_map.get(info["diet"], info["diet"])})
        if info.get("weight_range"):
            w_min, w_max = info["weight_range"]
            stats_rows.append({"label": "⚖️ 体重", "value": f"{w_min} ~ {w_max} kg"})
        if info.get("base_price"):
            stats_rows.append({"label": "💎 基础价", "value": f"{info['base_price']} 金币"})

    # 词条 (附魔效果)
    enchant_entries = []
    if first_entry.get("effects") and is_fish is False:
        # 附魔后词条 (装备)
        enchant_entries = _format_enchant_entries(first_entry["effects"], first_entry)

    # 鱼特殊: 显示鱼的实际属性
    weight = first_entry.get("weight", 0) if first_entry else 0
    base_price = info.get("base_price", 0)

    # 出售价格 (卖鱼/卖装备)
    sell_price = 0
    show_sell_price = False
    if is_fish and first_entry and first_entry.get("weight"):
        # 鱼: 基础价 × 波动 (10/7 改后用 base_price)
        sell_price = base_price
        show_sell_price = True
    elif not is_fish and info.get("price"):
        sell_price = int(info["price"] * 0.5)
        show_sell_price = True

    # 商店售价 (仅装备类)
    buy_price = info.get("price", 0) if not is_fish else 0
    show_price = buy_price > 0

    # 解锁要求
    unlock_req = ""
    if info.get("unlock_level", 0) > 0:
        unlock_req = f"需要等级 {info['unlock_level']}"

    # 获取方式
    source = "🎣 钓鱼捕获" if is_fish else "🏪 商店购买"
    if info.get("category") == "food":
        source = "🏪 商店购买 / 🍳 烹饪"
    if info.get("category") == "props":
        source = "🏪 商店购买 / 🎁 任务奖励"

    # footer hint
    if is_fish:
        footer = "🎣 鱼类 · 可在 /卖 卖出 · 钓鱼记录自动保存"
    else:
        footer = "💡 持有多件时数量会累加显示"

    return view_for_item_detail_card(
        user,
        name=name,
        emoji=emoji,
        rarity=rarity,
        quantity=quantity,
        item_type_cn=item_type_cn,
        subcategory=subcategory,
        desc=desc,
        stats_rows=stats_rows,
        enchant_entries=enchant_entries,
        is_fish=is_fish,
        base_price=base_price,
        weight=weight,
        sell_price=sell_price,
        buy_price=buy_price,
        unlock_requirement=unlock_req,
        source_hint=source,
        show_price=show_price,
        show_sell_price=show_sell_price,
        footer_hint=footer,
        header_subtitle="🔍 物品详情",
    )


def get_fallback_text(view: dict) -> str:
    """纯文本降级显示."""
    lines = [
        "═══════════════════════════",
        f"🔍 {view['name']} 详情",
        "═══════════════════════════",
        f"{view['emoji']} {view['rarity_cn']}{view['name']}",
    ]
    if view.get("quantity", 0) > 1:
        lines.append(f"持有: ×{view['quantity']}")
    lines.append(f"类型: {view['item_type_cn']}")
    if view.get("desc"):
        lines.append(f"说明: {view['desc']}")
    if view.get("stats_rows"):
        lines.append("")
        lines.append("📊 属性:")
        for r in view["stats_rows"]:
            lines.append(f"  {r['label']}: {r['value']}")
    if view.get("enchant_entries"):
        lines.append("")
        lines.append("✨ 词条:")
        for e in view["enchant_entries"]:
            lines.append(f"  {e['name']}: {e['desc']}")
    if view.get("show_price") and view.get("buy_price"):
        lines.append(f"\n🏷️ 商店售价: {view['buy_price']} 金币")
    if view.get("show_sell_price") and view.get("sell_price"):
        lines.append(f"💵 出售价格: {view['sell_price']} 金币/件")
    lines.append("═══════════════════════════")
    return "\n".join(lines)