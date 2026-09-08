"""
UserView — 用户数据访问视图层（ARCHITECTURE.md P1 #3）

设计目标：
- 消除 user["fishing"]["fish_caught"] 散落 30+ 处的嵌套访问
- 提供 typed accessor，每个函数有明确返回值
- 自动补默认值（老数据缺字段时仍能正常读）
- **不**改存储格式：user dict 的字段布局保持不变，UserView 只是便捷读法
- **不**包成 class：纯函数 + module-level，无状态，方便单测

ARCHITECTURE.md P1 #3 落地：
- 建 src/data/user_view.py
- UserView.get_profile(user_id) / get_shop_view() / get_fishing_state()
- 返回模板所需完整 dict，不暴露 user["fishing"] 嵌套
"""
from __future__ import annotations

from typing import Optional, Dict, List, Any


# ============================================================
# 基础字段访问（防 KeyError）
# ============================================================

def get_gold(user: dict) -> int:
    """金币。"""
    return int(user.get("gold", 0))


def get_status(user: dict) -> str:
    """当前状态（"空闲" / "工作中" / "学习中" 等）。"""
    return user.get("status", "空闲")


def get_nickname(user: dict) -> str:
    """昵称（缺省"未知"）。"""
    return user.get("nickname", "未知")


def get_residence(user: dict) -> str:
    """住所名。"""
    return user.get("residence", "桥下")


def get_attributes(user: dict) -> dict:
    """四维属性 (health/strength/mood/satiety/energy/sanity)。"""
    return user.get("attributes", {}) or {}


def get_skills(user: dict) -> dict:
    """技能 dict {skill_name: {level, exp, ...}}。"""
    return user.get("skills", {}) or {}


# 9/7: 老数据 slot 名迁移 (float → fishing_float, reel → fishing_reel)
_LEGACY_SLOT_MAP = {
    "float": "fishing_float",
    "reel": "fishing_reel",
}


def get_inventory(user: dict) -> List[dict]:
    """背包物品列表。

    9/7: 兼容老数据 slot 名 (float → fishing_float, reel → fishing_reel)
    """
    raw = user.get("inventory", []) or []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            out.append(item)
            continue
        slot = item.get("slot")
        if slot in _LEGACY_SLOT_MAP:
            new_item = dict(item)
            new_item["slot"] = _LEGACY_SLOT_MAP[slot]
            out.append(new_item)
        else:
            out.append(item)
    return out


def get_equipped(user: dict, slot: str) -> Optional[dict]:
    """装备槽单件。slot 例: fishing_rod / line / hook / float / bait。

    返回装备 dict（含 effects）, 没装返回 None。
    """
    eq = user.get("equipped_items", {}) or {}
    return eq.get(slot)


def get_all_equipped(user: dict) -> dict:
    """所有装备槽 {slot: item}。"""
    equipped = user.get("equipped_items", {}) or {}
    # 9/6 兼容: 老数据 equipped["fishing_line"] → "line"
    if "fishing_line" in equipped and "line" not in equipped:
        equipped["line"] = equipped.pop("fishing_line")
    return equipped


def get_settings(user: dict) -> dict:
    """用户设置 (notification_enabled / sub_group_daily / ...)。"""
    return user.get("settings", {}) or {}


# 9/6: 老玩家 settings 默认值 — 加新设置时只需在这里加一行, 全局生效
_DEFAULT_SETTINGS = {
    "notification_enabled": False,  # 关闭为安全默认 (opt-in)
    "sub_group_daily": True,         # 群订阅日报默认开
    "auto_fish_check": True,         # 自动检查鱼竿
    "sell_confirm_threshold": 1000,  # 单次卖卖 > 该金币需二次确认
}


def get_setting(user: dict, key: str, default=None):
    """读单个设置项, 带默认值。"""
    settings = get_settings(user)
    if default is None and key in _DEFAULT_SETTINGS:
        default = _DEFAULT_SETTINGS[key]
    return settings.get(key, default)


def ensure_settings_defaults(user: dict) -> dict:
    """为老玩家 settings 自动补默认值 (9/6).

    调用场景: 命令入口 / LLM tool 入口, store.get_user() 后调一次。
    用户在 Settings 命令里显式改过的值不会被覆盖 (因为 setdefault 语义)。
    """
    settings = user.setdefault("settings", {})
    for k, v in _DEFAULT_SETTINGS.items():
        settings.setdefault(k, v)
    return settings


def get_action_detail(user: dict) -> Optional[dict]:
    """当前 action 详情 (job_id/course_id/start_time/total_hours/...)。

    无 action 时返回 None。
    """
    return user.get("action_detail")


# ============================================================
# 子模块视图（消除 user["xxx"]["yyy"] 嵌套）
# ============================================================

def get_fishing(user: dict) -> dict:
    """钓鱼子模块视图。

    返回统一结构，老数据缺字段自动补默认:
        {
            "fish_caught": {"草鱼": 3, ...},
            "fish_records": [...],
            "total_fishing_count": 0,
            "total_fishing_value": 0,
            "biggest_catch": {},
            "fish_title": "",
        }
    """
    fishing = user.get("fishing", {}) or {}
    return {
        "fish_caught": fishing.get("fish_caught", {}) or {},
        "fish_records": fishing.get("fish_records", []) or [],
        "total_fishing_count": int(fishing.get("total_fishing_count", 0)),
        "total_fishing_value": int(fishing.get("total_fishing_value", 0)),
        "biggest_catch": fishing.get("biggest_catch", {}) or {},
        "fish_title": fishing.get("fish_title", "") or "",
    }


def get_fish_caught(user: dict) -> dict:
    """图鉴 {鱼名: 数量}。"""
    return get_fishing(user)["fish_caught"]


def get_biggest_catch(user: dict) -> dict:
    """最大一条鱼记录。"""
    return get_fishing(user)["biggest_catch"]


def get_fish_title(user: dict) -> str:
    """钓鱼称号。"""
    return get_fishing(user)["fish_title"]


def get_checkin(user: dict) -> dict:
    """签到子模块视图。

    老数据缺字段自动补默认:
        {
            "last_date": None,
            "streak": 0,
            "total_days": 0,
            "total_gold": 0,
            "lucky_drops": 0,
            "active_buffs": [],
            "last_luck": 50,
        }
    """
    c = user.get("checkin", {}) or {}
    return {
        "last_date": c.get("last_date"),
        "streak": int(c.get("streak", 0)),
        "total_days": int(c.get("total_days", 0)),
        "total_gold": int(c.get("total_gold", 0)),
        "lucky_drops": int(c.get("lucky_drops", 0)),
        "active_buffs": c.get("active_buffs", []) or [],
        "last_luck": int(c.get("last_luck", 50)),
    }


def get_lifetime_stats(user: dict) -> dict:
    """累计统计（终身）。"""
    return user.get("lifetime_stats", {}) or {}


def get_daily_stats(user: dict) -> dict:
    """每日统计 (date_str -> {gold_earned, work_count, ...})。"""
    return user.get("daily_stats", {}) or {}


def get_pressures(user: dict) -> dict:
    """压力 (身体 + 精神)。

    返回 {"body": 0, "mind": 0}
    """
    return {
        "body": int(user.get("body_pressure", 0)),
        "mind": int(user.get("mind_pressure", 0)),
    }


def get_active_debuffs(user: dict) -> List[dict]:
    """当前 debuff 列表。"""
    return user.get("active_debuffs", []) or []


def get_stock_holdings(user: dict) -> dict:
    """股票持仓 {stock_name: shares}。"""
    return user.get("stock_holdings", {}) or {}


# ============================================================
# 写辅助（mutator wrapper）
# ============================================================

def set_status(user: dict, status: str) -> None:
    """设置用户状态。"""
    user["status"] = status


def add_gold(user: dict, delta: int) -> int:
    """增减金币，返回新值。允许负数。"""
    user["gold"] = int(user.get("gold", 0)) + int(delta)
    return user["gold"]


def add_fish(user: dict, fish_name: str, n: int = 1) -> None:
    """累加图鉴鱼数。"""
    fishing = user.setdefault("fishing", {})
    fish_caught = fishing.setdefault("fish_caught", {})
    fish_caught[fish_name] = int(fish_caught.get(fish_name, 0)) + int(n)


def add_fish_record(user: dict, record: dict) -> None:
    """追加一条钓鱼记录（玩家鱼塘列表显示用）。

    record: {"fish_name": "草鱼", "weight": 0.42, "time": "...", "rarity": "common"}
    """
    fishing = user.setdefault("fishing", {})
    records = fishing.setdefault("fish_records", [])
    records.append(record)


def set_biggest_catch(user: dict, record: dict) -> bool:
    """如果 record.weight > 现有最大, 覆盖并返回 True; 否则 False。"""
    fishing = user.setdefault("fishing", {})
    current = fishing.get("biggest_catch", {}) or {}
    if record.get("weight", 0) > current.get("weight", 0):
        fishing["biggest_catch"] = record
        return True
    return False


def equip_item(user: dict, slot: str, item: dict) -> None:
    """装备 item 到 slot。覆盖式。"""
    eq = user.setdefault("equipped_items", {})
    eq[slot] = item


def unequip_slot(user: dict, slot: str) -> Optional[dict]:
    """卸下 slot, 返回卸下的 item。无装备返回 None。"""
    eq = user.get("equipped_items", {}) or {}
    item = eq.pop(slot, None)
    return item


# ============================================================
# 模板视图（ARCHITECTURE.md "返回模板所需完整 dict"）
# ============================================================

def view_for_profile_card(user: dict) -> dict:
    """档案卡片所需完整 dict（避免 render_profile 自己散落 user["xxx"]）。

    调用方:
        data = UserView.view_for_profile_card(user)
        url = await renderer.render_profile(user, event, data=data)  # 需 render_xxx 改造支持
    """
    attrs = get_attributes(user)
    ck = get_checkin(user)
    return {
        # 基础
        "nickname": get_nickname(user),
        "gold": get_gold(user),
        "residence": get_residence(user),
        "residence_emoji": user.get("residence_emoji", "🏠"),
        "status": get_status(user),
        # 签到
        "streak": ck["streak"],
        "total_days": ck["total_days"],
        "total_gold_earned": int(get_lifetime_stats(user).get("total_gold_earned", 0)),
        "peak_gold": int(get_lifetime_stats(user).get("peak_gold", 0)),
        # 钓鱼
        "fish_count": int(get_lifetime_stats(user).get("total_fish_caught", 0)),
        "fish_value": int(get_fishing(user)["total_fishing_value"]),
        "fish_species": len(get_fish_caught(user)),
        "fish_title": get_fish_title(user),
        "biggest_catch": get_biggest_catch(user),
        # 压力
        "body_pressure": get_pressures(user)["body"],
        "mind_pressure": get_pressures(user)["mind"],
        "active_debuffs": get_active_debuffs(user),
        # 属性
        "health": attrs.get("health", 0),
        "strength": attrs.get("strength", 0),
        "mood": attrs.get("mood", 0),
        "satiety": attrs.get("satiety", 0),
        "energy": attrs.get("energy", 0),
        "sanity": attrs.get("sanity", 0),
    }


def view_for_fish_dex_card(user: dict, all_fish: dict) -> dict:
    """鱼塘图鉴卡片所需完整 dict。"""
    from ..fishing.fishing_manager import format_weight  # 9/8: 紧凑重量格式
    fish_caught = get_fish_caught(user)
    biggest = get_biggest_catch(user)
    biggest_w_str = format_weight(biggest.get("weight", 0)) if biggest else ""
    return {
        "nickname": get_nickname(user),
        "fish_caught": fish_caught,
        "all_fish": all_fish,
        "completion_pct": len(fish_caught) / max(1, len(all_fish)) * 100,
        "biggest_catch": biggest,
        "biggest_weight_str": biggest_w_str,  # 9/8: 紧凑格式
        "fish_title": get_fish_title(user),
        "fish_count": int(get_lifetime_stats(user).get("total_fish_caught", 0)),
    }


def view_for_fishing_gear_card(user: dict, capacity: Optional[dict] = None, diet_zh: str = "不限") -> dict:
    """渔具卡片所需完整 dict.

    9/6: 加 capacity/diet_zh/inventory_gear 字段, 补齐与 render_fishing_gear 字段差异。
    调用方负责传 capacity / diet_zh / inventory_gear / effects_summary。
    9/6 v9.5: gear_slots 改为 list (供模板 {% for slot in gear_slots %} 迭代),
               每项含 {key, emoji, name, item_id, effect} 字段。
    """
    eq = get_all_equipped(user)
    gear_slots_keys = ["fishing_rod", "line", "hook", "fishing_float", "bait", "fishing_reel"]
    SLOT_EMOJI_LOCAL = {"fishing_rod": "🎣", "line": "🪢", "hook": "🪝", "fishing_float": "🎈", "bait": "🪱", "fishing_reel": "🎡"}
    SLOT_NAME_ZH = {"fishing_rod": "鱼竿", "line": "鱼线", "hook": "鱼钩", "fishing_float": "鱼漂", "bait": "鱼饵", "fishing_reel": "鱼轮"}

    gear_slots_list = []
    for s in gear_slots_keys:
        item = eq.get(s)
        if item and isinstance(item, dict):
            gear_slots_list.append({
                "key": s,
                "emoji": SLOT_EMOJI_LOCAL.get(s, "📦"),
                "name": SLOT_NAME_ZH.get(s, s),
                "item_id": item.get("name") or item.get("id", ""),
                "effect": "",  # 由调用方补充
            })
        else:
            gear_slots_list.append({
                "key": s,
                "emoji": SLOT_EMOJI_LOCAL.get(s, "📦"),
                "name": SLOT_NAME_ZH.get(s, s),
                "item_id": "",
                "effect": "",
            })

    gear_dict = {s: eq[s] for s in gear_slots_keys if eq.get(s)}
    empty = [s for s in gear_slots_keys if not eq.get(s)]
    # 9/7: 钓鱼状态显示 (渔具顶部)
    is_fishing = bool(user.get("is_fishing", False))
    fishing_spot = user.get("fishing_spot_name", "")
    if is_fishing and not fishing_spot:
        from ..fishing.fishing_manager import get_spot  # 9/7: 相对 import
        spot_id = user.get("current_spot_id", "")
        spot_def = get_spot(spot_id) or {}
        fishing_spot = spot_def.get("name", spot_id or "未知水域")

    return {
        "user_id": user.get("user_id", ""),
        "nickname": get_nickname(user),
        "gear": gear_dict,
        "empty_slots": empty,
        "gear_slots": gear_slots_list,  # 改为 list 给模板用
        "effects": {},
        "effects_summary": "",
        "capacity_fishing_rod": (capacity or {}).get("fishing_rod", 0),
        "capacity_fishing_rod_int": int((capacity or {}).get("fishing_rod", 0)),  # 9/7: 整数显示
        "capacity_fishing_line": (capacity or {}).get("fishing_line", 0),
        "capacity_fishing_line_int": int((capacity or {}).get("fishing_line", 0)),  # 9/7
        "diet_zh": diet_zh,
        "inventory_gear": [],
        "equipped_count": len(gear_dict),
        "is_fishing": is_fishing,
        "fishing_spot": fishing_spot,
    }


def view_for_backpack_card(user: dict, filter_label: str = "") -> dict:
    """背包卡片所需完整 dict。"""
    inv = get_inventory(user)
    return {
        "nickname": get_nickname(user),
        "items": inv,
        "filter_label": filter_label,
        "total_count": len(inv),
    }


# ============================================================
# 9/6: 附魔卡片 view (9/6 模板字段补齐)
# ============================================================
def view_for_enchant_card(
    user: dict,
    target_entry: dict,
    old_rarity: str,
    old_mult: float,
    new_rarity: str,
    new_mult: float,
    new_effects: dict,
    scroll_name: str,
    scroll_remaining: int,
    scroll_color: str,
) -> dict:
    """附魔结果卡片所需完整 dict.

    将 raw new_effects dict 转为模板所需的 entries[] / base_attrs[] 列表.
    (原来在 renderer.render_enchant() 内完成, 9/6 拆到 view 层)
    """
    from ...modules.item import RARITY_NAMES
    from ...modules.entry_lib import COMMON_ENTRY_LIB, SPECIAL_ENTRY
    from ...modules.renderer import (
        _ENTRY_ICON, _ENTRY_NAME, _BASE_ATTR_NAME,
        get_entry_icon, get_entry_name, get_base_attr_name, format_base_attr_value,
    )

    # 基础属性白名单
    BASE_ATTR_KEYS = {"load_capacity_max", "max_hook_slots", "duration_reduce",
                      "habitat_filter", "target_diet", "target_size_weights"}

    # 词条分类: flat vs pct
    entries = []
    for k, v in new_effects.items():
        if not isinstance(v, (int, float)):
            continue
        if k in BASE_ATTR_KEYS:
            continue
        is_pct_field = k.endswith("_pct")
        raw_k = k[:-4] if is_pct_field else k
        entry_type = "pct" if is_pct_field else "flat"
        if raw_k in COMMON_ENTRY_LIB:
            if not is_pct_field:
                entry_type = COMMON_ENTRY_LIB[raw_k].get("type", "flat")
        elif raw_k in SPECIAL_ENTRY:
            if not is_pct_field:
                entry_type = SPECIAL_ENTRY[raw_k].get("type", "flat")
        else:
            continue
        if v == 0:
            continue
        entries.append({
            "icon": get_entry_icon(raw_k),
            "name": get_entry_name(raw_k),
            "type": entry_type,
            "value": round(v, 2),
        })
    entries.sort(key=lambda e: (0 if e["type"] == "pct" else 1, -e["value"]))

    # 基础属性
    base_attrs = []
    for k, v in new_effects.items():
        if not isinstance(v, (int, float)):
            continue
        if k not in BASE_ATTR_KEYS:
            continue
        if k == "duration_reduce" and v <= 0:
            continue
        base_attrs.append({
            "name": get_base_attr_name(k),
            "old": "",
            "new": format_base_attr_value(k, v),
            "diff": False,
        })

    rarity_color_map = {
        "common":    ("#9e9e9e", "#616161"),
        "uncommon":  ("#7CFC00", "#228B22"),
        "rare":      ("#4FC3F7", "#0288D1"),
        "epic":      ("#BA68C8", "#7B1FA2"),
        "legendary": ("#FFB74D", "#E65100"),
        "mythic":    ("#EF5350", "#B71C1C"),
    }
    new_rarity_color, new_rarity_color_dark = rarity_color_map.get(new_rarity, ("#9e9e9e", "#616161"))

    item_name = target_entry.get("name") or target_entry.get("id", "未知")
    return {
        "nickname": get_nickname(user),
        "item_name": item_name,
        "old_rarity_cn": RARITY_NAMES.get(old_rarity, old_rarity),
        "old_mult": old_mult,
        "new_rarity_cn": RARITY_NAMES.get(new_rarity, new_rarity),
        "new_mult": new_mult,
        "new_rarity_color": new_rarity_color,
        "new_rarity_color_dark": new_rarity_color_dark,
        "entries": entries,
        "entry_count": len(entries),
        "base_attrs": base_attrs,
        "scroll_name": scroll_name,
        "scroll_color": scroll_color,
        "scroll_remaining": scroll_remaining,
    }


# ============================================================
# 9/7: 物品详情卡片 view (背包 <物品名>)
# ============================================================
def view_for_item_detail_card(
    user: dict,
    *,
    name: str,
    emoji: str,
    rarity: str,
    quantity: int,
    item_type_cn: str,
    subcategory: str = "",
    desc: str = "",
    stats_rows: list = None,
    enchant_entries: list = None,
    is_fish: bool = False,
    base_price: int = 0,
    weight: float = 0,
    sell_price: int = 0,
    buy_price: int = 0,
    unlock_requirement: str = "",
    source_hint: str = "",
    show_price: bool = False,
    show_sell_price: bool = False,
    footer_hint: str = "",
    header_subtitle: str = "🔍 物品详情",
) -> dict:
    """物品详情卡片所需 dict.

    Args:
        name: 物品名称
        emoji: emoji 图标
        rarity: 稀有度 (common/uncommon/.../mythic)
        quantity: 持有数量
        item_type_cn: 类型中文 (如: 食物/装备/渔具/鱼)
        stats_rows: 属性行 [{label, value}, ...]
        enchant_entries: 词条 [{name, desc, color?}, ...]
        is_fish: 是否是鱼
        sell_price: 出售单价 (金币/件)
        buy_price: 商店售价 (金币)
        unlock_requirement: 解锁要求文本
        source_hint: 获取方式
    """
    from ...modules.item import RARITY_NAMES, rarity_hex  # 9/7: 相对 import (兼容 AstrBot runtime)
    from ..fishing.fishing_manager import format_weight, format_length_compact  # 9/8: 紧凑格式
    return {
        "nickname": get_nickname(user),
        "name": name,
        "emoji": emoji,
        "rarity": rarity,
        "rarity_cn": RARITY_NAMES.get(rarity, "普通"),
        "rarity_color": rarity_hex(rarity),
        "quantity": quantity,
        "item_type_cn": item_type_cn,
        "subcategory": subcategory,
        "desc": desc,
        "stats_rows": stats_rows or [],
        "enchant_entries": enchant_entries or [],
        "is_fish": is_fish,
        "weight_str": format_weight(weight) if is_fish else "",  # 9/8: 紧凑格式
        "base_price": base_price,
        "weight": weight,
        "sell_price": sell_price,
        "buy_price": buy_price,
        "unlock_requirement": unlock_requirement,
        "source_hint": source_hint,
        "show_price": show_price,
        "show_sell_price": show_sell_price,
        "footer_hint": footer_hint,
        "header_subtitle": header_subtitle,
    }
