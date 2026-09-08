"""
物品系统模块 v3
支持背包堆叠、装备栏位、商店系统
"""
from typing import Optional
from .constants import ITEMS
from .entry_lib import resolve_effects as _resolve_effects, get_item_rarity as _get_entry_rarity, get_entry_rarity_mult as _get_entry_rarity_mult


# ============================================================
# 稀有度配置
# ============================================================

RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]

RARITY_COLORS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟠",  # 9/4晚: 黄→橙
    "mythic": "🔴",     # 9/4晚: 新增神话级
}

# 9/6: rarity → hex 颜色 (UI 渲染用). 与 RARITY_COLORS (emoji) 并存.
RARITY_HEX_COLORS = {
    "common":    "#9e9e9e",  # 灰
    "uncommon":  "#7bed9f",  # 绿
    "rare":      "#4fc3f7",  # 蓝
    "epic":      "#c586c0",  # 紫
    "legendary": "#ffa726",  # 橙
    "mythic":    "#ff6b6b",  # 红
}


def rarity_hex(rarity: Optional[str]) -> str:
    """rarity → hex 颜色 (UI 渲染). 未知值回退 common 灰."""
    return RARITY_HEX_COLORS.get(rarity or "common", "#9e9e9e")

RARITY_NAMES = {
    "common": "普通",
    "uncommon": "优秀",
    "rare": "稀有",
    "epic": "史诗",
    "legendary": "传说",
    "mythic": "神话",     # 9/4晚: 新增神话级
}

# 9/4晚: rarity 排序 (用于比较)
RARITY_RANK = {
    "common": 0, "uncommon": 1, "rare": 2,
    "epic": 3, "legendary": 4, "mythic": 5,
}

# 9/4晚: 词条系统 - rarity 基础数值倍率范围 (等比缩放, 神话不超过 2.5)
RARITY_MULT_RANGE = {
    "common":    (1.00, 1.00),   # 固定
    "uncommon":  (1.05, 1.15),
    "rare":      (1.15, 1.35),
    "epic":      (1.35, 1.65),
    "legendary": (1.65, 2.00),
    "mythic":    (2.00, 2.50),
}

# 9/4晚: 词条数 (rarity 决定抽几个词条)
RARITY_BONUS_COUNT = {
    "common":    0,
    "uncommon":  1,
    "rare":      2,
    "epic":      3,
    "legendary": 4,
    "mythic":    5,
}

# 栏位配置
SLOTS = {
    "clothing": "服装",
    "head": "头部",
    "tool": "工具",
    "accessory": "饰品",
    "phone": "手机",
    # 9/3: 渔具子系统 (双轨制, 不复用通用5 槽)
    "fishing_rod": "鱼竿",
    "fishing_line": "鱼线",
    "fishing_hook": "鱼钩",
    "fishing_float": "浮漂",
    "fishing_bait": "鱼饵",
    # 9/3 (晚): 鱼轮 (钓鱼经验加成 + duration_reduce + rare_bonus)
    "fishing_reel": "鱼轮",
}

SLOT_EMOJI = {
    "clothing": "👔",
    "head": "🧢",
    "tool": "🎒",
    "accessory": "💍",
    "phone": "📱",
    "fishing_rod": "🎣",
    "fishing_line": "🪢",
    "fishing_hook": "🪝",
    "fishing_float": "🪶",
    "fishing_bait": "🪱",
    "fishing_lure": "🪝",
    "fishing_reel": "🧵",
    "fishing_waders": "👖",
}

# 渔具栏位中文名 → 槽位 key (供 /渔具 命令用)
FISHING_GEAR_SLOTS = {
    "鱼竿": "fishing_rod",
    "鱼线": "fishing_line",
    "鱼钩": "fishing_hook",
    "浮漂": "fishing_float",
    "鱼饵": "fishing_bait",
    "拟饵": "fishing_lure",
    "鱼轮": "fishing_reel",
    "涉水裤": "fishing_waders",
}


# ============================================================
# 物品查询
# ============================================================

def get_item_by_id(item_id: str) -> dict:
    """获取物品信息"""
    return ITEMS.get(item_id, {})


def is_stackable(item_id: str) -> bool:
    """物品是否可堆叠"""
    item = ITEMS.get(item_id, {})
    return item.get("stackable", False)


def is_consumable(item_id: str) -> bool:
    """物品是否可消耗"""
    item = ITEMS.get(item_id, {})
    return item.get("consumable", False)


def is_equipment(item_id: str) -> bool:
    """物品是否是装备（有栏位）"""
    item = ITEMS.get(item_id, {})
    return bool(item.get("slot"))


# ============================================================
# 背包管理
# ============================================================

def add_to_inventory(user: dict, item_id: str, quantity: int = 1) -> bool:
    """添加物品到背包
    
    Args:
        user: 用户数据
        item_id: 物品ID
        quantity: 数量
    
    Returns:
        bool: 是否成功添加
    """
    item = ITEMS.get(item_id)
    if not item:
        return False
    
    inventory = user.get("inventory", [])
    
    # 检查是否可堆叠
    if item.get("stackable", False):
        # 查找是否有同名物品
        for inv_item in inventory:
            if inv_item.get("id") == item_id:
                inv_item["quantity"] = inv_item.get("quantity", 1) + quantity
                user["inventory"] = inventory
                return True
        
        # 没有找到，添加新条目
        inventory.append({
            "id": item_id,
            "name": item.get("name"),
            "quantity": quantity
        })
    else:
        # 不可堆叠，直接添加多个
        for _ in range(quantity):
            inventory.append({
                "id": item_id,
                "name": item.get("name")
            })
    
    user["inventory"] = inventory
    return True


def remove_from_inventory(user: dict, item_id: str, quantity: int = 1) -> bool:
    """从背包移除物品
    
    Args:
        user: 用户数据
        item_id: 物品ID
        quantity: 数量
    
    Returns:
        bool: 是否成功移除
    """
    inventory = user.get("inventory", [])
    remaining = quantity
    
    new_inventory = []
    for inv_item in inventory:
        if inv_item.get("id") == item_id and remaining > 0:
            qty = inv_item.get("quantity", 1)
            if qty <= remaining:
                remaining -= qty
            else:
                inv_item["quantity"] = qty - remaining
                remaining = 0
                new_inventory.append(inv_item)
        else:
            new_inventory.append(inv_item)
    
    user["inventory"] = new_inventory
    return remaining == 0


def get_inventory_count(user: dict, item_id: str) -> int:
    """获取背包中某物品的数量"""
    inventory = user.get("inventory", [])
    total = 0
    for inv_item in inventory:
        if inv_item.get("id") == item_id:
            total += inv_item.get("quantity", 1)
    return total


def get_all_inventory(user: dict) -> list:
    """获取背包所有物品（带数量）"""
    return user.get("inventory", [])


# ============================================================
# 装备栏位管理
# ============================================================

def get_items_by_slot(user: dict, slot: str) -> list:
    """获取背包中指定栏位的装备物品
    
    Args:
        user: 用户数据
        slot: 栏位名称 (clothing/head/tool/accessory/phone)
    
    Returns:
        list: 该栏位的物品列表
    """
    inventory = user.get("inventory", [])
    result = []
    for inv_item in inventory:
        item_id = inv_item.get("id")
        item_info = ITEMS.get(item_id, {})
        if item_info.get("slot") == slot:
            result.append({
                "id": item_id,
                "name": item_info.get("name", item_id),
                "quantity": inv_item.get("quantity", 1)
            })
    return result


def get_equipped_items(user: dict) -> dict:
    """获取用户已装备的物品

    9/7 命名统一: 不再做反向兼容 (fishing_line → line), 数据统一用 fishing_ 前缀
    """
    equipped = user.get("equipped_items", {})
    return equipped


def equip_item(user: dict, item_id: str) -> tuple[bool, str, dict]:
    """装备物品到对应栏位

    9/4晚: 多槽系统
    - hook: 鱼竿 max_hook_slots 决定钩槽数, 追加到 hook_slots
    - bait: 槽数 = len(hook_slots), 装备时自动合并 inventory 同种饵料 quantity
    - 拟饵 (consumable=False): 不消耗, quantity=null
    - 消耗饵 (consumable=True): 合并 inventory quantity 到 bait_slot
    """
    item_info = ITEMS.get(item_id)
    if not item_info:
        return False, "物品不存在", {}

    slot = item_info.get("slot")
    if not slot:
        return False, "该物品无法装备", {}

    # 检查背包中是否有该物品 (9/4晚: 拟饵/鱼钩不消耗, 但仍需在背包)
    inventory = user.get("inventory", [])
    item_found = False
    item_index = -1
    qty = 0
    inv_entry = None  # 9/4晚: 保留 inventory entry (含 rarity/rarity_mult)

    for i, inv_item in enumerate(inventory):
        if inv_item.get("id") == item_id:
            item_found = True
            item_index = i
            qty = inv_item.get("quantity", 1)
            inv_entry = inv_item
            break

    if not item_found:
        return False, "背包中没有该物品", {}

    # 9/4晚: 计算装备后实际生效 effects
    # 9/7 命名统一: slot key 加 fishing_ 前缀
    if slot == "fishing_bait" and inv_entry is not None and inv_entry.get("subcategory") != "fishing_lure" and inv_entry.get("consumable", item_info.get("consumable", False)):
        # 消耗性鱼饵: 不走词条系统 (无 rarity)
        equip_effects = item_info.get("base_effects", {})
        rarity = "common"
        rarity_mult = 1.0
    else:
        # 渔具/拟饵: 读 inventory entry 的 rarity/rarity_mult
        rarity = _get_entry_rarity(inv_entry) if inv_entry else "common"
        rarity_mult = _get_entry_rarity_mult(inv_entry) if inv_entry else 1.0
        equip_effects = _resolve_effects(item_info, rarity, rarity_mult)

    equipped = user.get("equipped_items", {})

    # ===== 9/4晚: 鱼钩多槽 =====
    if slot == "fishing_hook":
        rod_id = equipped.get("fishing_rod", {}).get("id", "")
        rod_info = ITEMS.get(rod_id, {})
        # 9/4晚: 用鱼竿的 resolved effects (含 rarity_mult) 查 max_hook_slots
        rod_rarity = equipped.get("fishing_rod", {}).get("rarity", "common")
        rod_mult = equipped.get("fishing_rod", {}).get("rarity_mult", 1.0)
        rod_effects = _resolve_effects(rod_info, rod_rarity, rod_mult)
        max_hooks = int(rod_effects.get("max_hook_slots", rod_info.get("base_effects", {}).get("max_hook_slots", 1)))
        hook_slots = equipped.get("hook_slots", [])
        if not isinstance(hook_slots, list):
            hook_slots = []
        current_count = sum(1 for s in hook_slots if s)
        replaced_msg = ""
        # 9/4: 槽满时替换第一个 (最旧), 而不是拒绝
        if current_count >= max_hooks:
            # 找第一个非空槽位, 替换
            for i, s in enumerate(hook_slots):
                if s:
                    old_id = s.get("id", "")
                    old_def = ITEMS.get(old_id, {})
                    old_name = old_def.get("name", old_id)
                    # 卸下的鱼钩加回背包 (鱼钩 stackable=False, 整个 entry)
                    inventory.append({
                        "id": old_id,
                        "name": old_name,
                        "rarity": s.get("rarity", "common"),
                        "rarity_mult": s.get("rarity_mult", 1.0),
                    })
                    hook_slots[i] = {
                        "id": item_id,
                        "name": item_info.get("name"),
                        "rarity": rarity,
                        "rarity_mult": rarity_mult,
                        "effects": equip_effects,
                    }
                    replaced_msg = f" (已卸下 {old_name})"
                    break
            equipped["hook_slots"] = hook_slots
            # 从背包移除新鱼钩
            if item_index >= 0:
                if qty > 1:
                    inventory[item_index]["quantity"] = qty - 1
                else:
                    inventory.pop(item_index)
            user["equipped_items"] = equipped
            user["inventory"] = inventory
            return True, f"已装备 {item_info.get('name')}{replaced_msg}", item_info
        hook_slots.append({
            "id": item_id,
            "name": item_info.get("name"),
            "rarity": rarity,
            "rarity_mult": rarity_mult,
            "effects": equip_effects,
        })
        equipped["hook_slots"] = hook_slots
        # 从背包移除鱼钩 (鱼钩不消耗)
        if item_index >= 0:
            if qty > 1:
                inventory[item_index]["quantity"] = qty - 1
            else:
                inventory.pop(item_index)
        user["equipped_items"] = equipped
        user["inventory"] = inventory
        return True, f"已装备 {item_info.get('name')} (鱼钩槽 {current_count + 1}/{max_hooks})", item_info

    # ===== 9/4晚: 鱼饵多槽 = sum(每个鱼钩的 max_bait_per_hook), 上限3 =====
    if slot == "fishing_bait":
        hook_slots = equipped.get("hook_slots", [])
        if not hook_slots:
            return False, "请先装备鱼钩, 才能装鱼饵", item_info
        # 9/5: 计算每个鱼钩的 bait 槽位, 累加, 上限 3
        max_bait = 0
        from .item import ITEMS as _ITEMS_HOOK
        for hs in hook_slots:
            if not hs:
                continue
            hook_id = hs.get("id", "")
            hook_def = _ITEMS_HOOK.get(hook_id, {})
            per_hook = int(hook_def.get("base_effects", {}).get("max_bait_per_hook", 1))
            # 鱼钩词条 bait_slots 也加成 +1 (传说/神话鱼钩)
            hook_effects = hs.get("effects", {})
            per_hook += int(hook_effects.get("bait_slots", 0))
            max_bait += per_hook
        max_bait = min(max_bait, 3)  # 硬上限3
        bait_slots = equipped.get("bait_slots", [])
        if not isinstance(bait_slots, list):
            bait_slots = []
        current_count = sum(1 for s in bait_slots if s)
        is_consumable = bool(item_info.get("consumable", False))
        # 9/4晚: 合并逻辑 - 如果同种饵已在 slot 中, 直接 +qty (不创建新槽)
        for existing in bait_slots:
            if existing.get("id") == item_id:
                if is_consumable:
                    existing["quantity"] = (existing.get("quantity") or 0) + qty
                # 从背包移除 (消耗饵全扣到 slot, 拟饵不消耗)
                if is_consumable and item_index >= 0:
                    if qty > 1:
                        inventory[item_index]["quantity"] = qty - 1
                    else:
                        inventory.pop(item_index)
                equipped["bait_slots"] = bait_slots
                user["equipped_items"] = equipped
                user["inventory"] = inventory
                return True, f"已合并 {item_info.get('name')} (现有槽, 总数 {existing.get('quantity', 0)})", item_info
        # 新槽
        if current_count >= max_bait:
            return False, f"鱼饵槽已满 ({current_count}/{max_bait})", item_info
        slot_entry = {
            "id": item_id,
            "name": item_info.get("name"),
            "rarity": rarity,
            "rarity_mult": rarity_mult,
            "effects": equip_effects,
            "consumable": is_consumable,
        }
        if is_consumable:
            slot_entry["quantity"] = qty  # 初始 = inventory 现有数量
        else:
            slot_entry["quantity"] = None  # 拟饵永不消耗
        bait_slots.append(slot_entry)
        equipped["bait_slots"] = bait_slots
        # 从背包移除 (消耗饵装上后合并 qty, 拟饵不消耗)
        if is_consumable and item_index >= 0:
            if qty > 1:
                inventory[item_index]["quantity"] = qty - 1
            else:
                inventory.pop(item_index)
        user["equipped_items"] = equipped
        user["inventory"] = inventory
        return True, f"已装备 {item_info.get('name')} (饵料槽 {current_count + 1}/{max_bait})", item_info

    # ===== 普通单槽装备 (鱼竿/鱼线/浮漂/鱼轮/通用装备) =====
    current_equipped = equipped.get(slot)
    # 卸下当前 (放回背包)
    replaced_msg = ""
    if current_equipped:
        old_name = current_equipped.get("name", current_equipped.get("id", ""))
        old_entry = {
            "id": current_equipped.get("id"),
            "name": current_equipped.get("name"),
            "rarity": current_equipped.get("rarity", "common"),
            "rarity_mult": current_equipped.get("rarity_mult", 1.0),
        }
        if is_stackable(current_equipped.get("id", "")):
            add_to_inventory(user, current_equipped.get("id"), 1)
        else:
            inventory.append(old_entry)
        replaced_msg = f" (已卸下 {old_name})"

    equipped[slot] = {
        "id": item_id,
        "name": item_info.get("name"),
        "rarity": rarity,
        "rarity_mult": rarity_mult,
        "effects": equip_effects,
    }

    # 从背包移除
    if item_index >= 0:
        if qty > 1:
            inventory[item_index]["quantity"] = qty - 1
        else:
            inventory.pop(item_index)

    user["equipped_items"] = equipped
    user["inventory"] = inventory

    return True, f"已装备 {item_info.get('name')}{replaced_msg}", item_info


def unequip_item(user: dict, slot: str) -> tuple[bool, str]:
    """卸下指定栏位的装备"""
    if slot not in SLOTS:
        return False, "无效的栏位"

    equipped = user.get("equipped_items", {})
    current = equipped.get(slot)

    # 9/4晚: bait/hook 多槽兼容 - 优先检查 _slots list
    # 9/7 命名统一: slot 加 fishing_ 前缀, 但 _slots list 字段保持不变 (兼容老数据)
    if not current and slot in ("fishing_hook", "fishing_bait"):
        # 9/7: 兼容老 slot 名 (hook/bait → fishing_hook/fishing_bait)
        list_key = f"{slot}_slots"
        # 兜底: 查老 list_key (hook_slots/bait_slots)
        if not equipped.get(list_key) and slot in ("fishing_hook", "fishing_bait"):
            old_slot = slot.replace("fishing_", "")
            list_key = f"{old_slot}_slots"
        slots_list = equipped.get(list_key, [])
        if isinstance(slots_list, list) and slots_list:
            # 卸第一个非空槽 (单槽卸下语义)
            removed = slots_list.pop(0)
            equipped[list_key] = slots_list
            # 写回背包
            if removed.get("consumable") and removed.get("quantity"):
                add_to_inventory(user, removed.get("id"), removed["quantity"])
            else:
                user.setdefault("inventory", []).append({
                    "id": removed.get("id"),
                    "name": removed.get("name"),
                    "category": removed.get("category") or ITEMS.get(removed.get("id"), {}).get("category"),
                    "type": removed.get("type") or ITEMS.get(removed.get("id"), {}).get("type"),
                    "slot": removed.get("slot") or ITEMS.get(removed.get("id"), {}).get("slot"),
                    "consumable": removed.get("consumable", False),
                })
            user["equipped_items"] = equipped
            return True, f"已卸下 {removed.get('name')}"

    if not current:
        return False, "该栏位没有装备"

    # 放入背包
    add_to_inventory(user, current.get("id"), 1)

    # 清除装备
    del equipped[slot]
    user["equipped_items"] = equipped

    return True, f"已卸下 {current.get('name')}"


def auto_equip_if_empty(user: dict, item_id: str) -> bool:
    """如果对应栏位为空，自动装备物品"""
    item_info = ITEMS.get(item_id)
    if not item_info:
        return False
    
    slot = item_info.get("slot")
    if not slot:
        return False
    
    equipped = user.get("equipped_items", {})
    
    if slot not in equipped or not equipped[slot]:
        equipped[slot] = {
            "id": item_id,
            "name": item_info.get("name"),
            "effects": item_info.get("effects", {}),
        }
        user["equipped_items"] = equipped
        return True
    
    return False


# ============================================================
# 装备效果计算
# ============================================================

def calc_equipped_effects(user: dict) -> dict:
    """计算用户已装备物品的总效果

    9/4晚: 支持渔具词条系统
    - flat 字段累加 (success_rate, habitat_*, size_*, diet_*, load_capacity_max 等)
    - pct 字段累加百分比 (rarity_pct_bonus, exp_bonus, price_bonus, load_capacity_pct 等)
    - 通用装备字段直接累加
    """
    # 通用装备字段 (老系统) - 兼容
    effects: dict[str, float] = {
        "strength_bonus": 0,
        "energy_bonus": 0,
        "mood_bonus": 0,
        "health_bonus": 0,
        "satiety_bonus": 0,
        "work_income_bonus": 0,
        "learn_exp_bonus": 0,
        "entertain_mood_bonus": 0,
        "sleep_strength_bonus": 0,
        "sleep_energy_bonus": 0,
        "passive_gold": 0,
        "passive_mood": 0,
        "work_time_reduce": 0,
    }

    # 9/4晚: pct 字段累加器 (新系统) - 渔具百分比词条
    pct_sums: dict[str, float] = {}

    equipped = user.get("equipped_items", {})
    if not equipped:
        return effects

    def _iter_items():
        """生成所有装备 entry"""
        for slot, item_data in equipped.items():
            if not item_data:
                continue
            if slot == "hook_slots" and isinstance(item_data, list):
                for hook_item in item_data:
                    if hook_item and isinstance(hook_item, dict):
                        yield hook_item
            elif slot == "bait_slots" and isinstance(item_data, list):
                for bait_item in item_data:
                    if bait_item and isinstance(bait_item, dict):
                        yield bait_item
            elif isinstance(item_data, dict):
                yield item_data
            # 忽略 list 但不是 hook/bait_slots (兼容老数据)

    for entry in _iter_items():
        item_effects = entry.get("effects", {})
        for key, val in item_effects.items():
            if not isinstance(val, (int, float)):
                continue  # 跳过 dict (如 target_size_weights)
            # 判断是 flat 还是 pct - 用 COMMON_ENTRY_LIB
            from .entry_lib import COMMON_ENTRY_LIB
            entry_def = COMMON_ENTRY_LIB.get(key)
            if entry_def and entry_def.get("type") == "pct":
                # 百分比累加
                pct_sums[key] = pct_sums.get(key, 0) + val
            else:
                # flat 或基础属性 - 直接累加
                effects[key] = effects.get(key, 0) + val

    # 9/4晚: 应用 (1 + pct) 到 pct 字段对应效果 (简单形式: 把 pct 加到原字段)
    # pct 字段约定: 字段名后缀 _pct 表示百分比加成
    for k, pct in pct_sums.items():
        # pct 字段如 rarity_pct_bonus / exp_bonus / price_bonus / load_capacity
        # 直接返回百分比值, 让上层调用者按公式应用
        effects[k] = effects.get(k, 0) + pct

    return effects


def get_equipped_summary(user: dict) -> str:
    """获取已装备物品的简要描述"""
    equipped = user.get("equipped_items", {})
    if not equipped:
        return "无"
    
    lines = []
    for slot, emoji in SLOT_EMOJI.items():
        item = equipped.get(slot)
        if item:
            lines.append(f"{emoji}{item.get('name', '未知')}")
        else:
            lines.append(f"{emoji}空")
    
    return " | ".join(lines)


# ============================================================
# 物品效果应用
# ============================================================

def apply_item_effects(user: dict, item_id: str) -> tuple[bool, str]:
    """使用物品并应用效果
    
    Args:
        user: 用户数据
        item_id: 物品ID
    
    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    item = ITEMS.get(item_id)
    if not item:
        return False, "物品不存在"
    
    # 检查是否可消耗
    if not item.get("consumable", False):
        return False, "该物品无法直接使用"
    
    # 检查背包中是否有
    count = get_inventory_count(user, item_id)
    if count <= 0:
        return False, "背包中没有该物品"
    
    # 应用效果
    effects = item.get("effects", {})
    attrs = user.get("attributes", {})
    
    effect_names = {
        "satiety": "饱食",
        "mood": "心情",
        "health": "健康",
        "energy": "精力",
        "strength": "体力",
    }
    
    applied = []
    for key, value in effects.items():
        if key in attrs and isinstance(value, (int, float)) and value > 0:
            old_val = attrs[key]
            attrs[key] = min(100, attrs[key] + value)
            name = effect_names.get(key, key)
            applied.append(f"{name}+{value}")
    
    user["attributes"] = attrs
    
    # 消耗物品
    remove_from_inventory(user, item_id, 1)
    
    effect_str = ", ".join(applied) if applied else "无"
    return True, f"使用了 {item.get('name')}，效果: {effect_str}"


# ============================================================
# 格式化
# ============================================================

def format_item(item_id_or_entry, show_price: bool = True, show_slot: bool = False) -> str:
    """格式化物品显示信息

    9/4晚: 支持 entry dict 传入, 优先用 entry 的 rarity
    """
    if isinstance(item_id_or_entry, dict):
        entry = item_id_or_entry
        item_id = entry.get("id", "")
        item = ITEMS.get(item_id, {})
        name = entry.get("name") or item.get("name", item_id)
        # entry 的 rarity 优先 (附魔后 entry 有新 rarity)
        rarity = entry.get("rarity", item.get("rarity", "common"))
    else:
        item_id = item_id_or_entry
        item = ITEMS.get(item_id, {})
        name = item.get("name", "未知")
        rarity = item.get("rarity", "common")

    if not item:
        return "未知物品"

    emoji = RARITY_COLORS.get(rarity, "⚪")
    tier = item.get("tier", 1)

    # 9/4晚: 物品名加稀有度前缀 (普通不加)
    rarity_cn = RARITY_NAMES.get(rarity, "")
    if rarity_cn and rarity != "common":
        name = f"{rarity_cn}{name}"

    result = f"{emoji}{name}"
    
    if show_slot:
        slot = item.get("slot", "")
        slot_name = SLOTS.get(slot, slot)
        result += f"[{slot_name}]"
    
    result += f" T{tier}"
    
    if show_price:
        price = item.get("price", 0)
        result += f" (§e{price}金§r)"
    
    return result


def format_item_effects(effects: dict) -> str:
    """格式化效果描述"""
    effect_names = {
        "strength_bonus": "体力",
        "energy_bonus": "精力",
        "mood_bonus": "心情",
        "health_bonus": "健康",
        "satiety_bonus": "饱食",
        "work_income_bonus": "工作收入",
        "learn_exp_bonus": "学习经验",
        "entertain_mood_bonus": "娱乐心情",
        "sleep_strength_bonus": "睡眠体力",
        "sleep_energy_bonus": "睡眠精力",
        "passive_gold": "空闲金币/时",
        "passive_mood": "空闲心情/分",
        "work_time_reduce": "工作时长",
    }
    
    parts = []
    for key, value in effects.items():
        if value == 0:
            continue
        name = effect_names.get(key, key)
        if isinstance(value, (int, float)) and value < 1:
            parts.append(f"{name}+{int(value*100) if value >= 1 else value*100:.0f}%")
        elif key in ("passive_gold", "passive_mood"):
            parts.append(f"{name}+{value}")
        elif key == "work_time_reduce":
            parts.append(f"{name}-{value}%")
        else:
            parts.append(f"{name}+{value}")
    
    return " | ".join(parts) if parts else "无"


def can_buy_item(user_gold: int, item_id: str) -> tuple[bool, str]:
    """检查是否能购买物品"""
    item = ITEMS.get(item_id, {})
    if not item:
        return False, "物品不存在"
    
    price = item.get("price", 0)
    if user_gold < price:
        return False, f"金币不足，需要 {price} 金币"
    
    return True, ""
