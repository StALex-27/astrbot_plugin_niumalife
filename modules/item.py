"""
物品系统模块 v3
支持背包堆叠、装备栏位、商店系统
"""
from .constants import ITEMS


# ============================================================
# 稀有度配置
# ============================================================

RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]

RARITY_COLORS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
}

RARITY_NAMES = {
    "common": "普通",
    "uncommon": "优秀",
    "rare": "稀有",
    "epic": "史诗",
    "legendary": "传说",
}

# 栏位配置
SLOTS = {
    "clothing": "服装",
    "head": "头部",
    "tool": "工具",
    "accessory": "饰品",
    "phone": "手机",
}

SLOT_EMOJI = {
    "clothing": "👔",
    "head": "🧢",
    "tool": "🎒",
    "accessory": "💍",
    "phone": "📱",
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

def get_equipped_items(user: dict) -> dict:
    """获取用户已装备的物品"""
    equipped = user.get("equipped_items", {})
    return equipped


def equip_item(user: dict, item_id: str) -> tuple[bool, str, dict]:
    """装备物品到对应栏位"""
    item_info = ITEMS.get(item_id)
    if not item_info:
        return False, "物品不存在", {}
    
    slot = item_info.get("slot")
    if not slot:
        return False, "该物品无法装备", {}
    
    # 检查背包中是否有该物品
    inventory = user.get("inventory", [])
    item_found = False
    item_index = -1
    qty = 0
    
    for i, inv_item in enumerate(inventory):
        if inv_item.get("id") == item_id:
            item_found = True
            item_index = i
            qty = inv_item.get("quantity", 1)
            break
    
    if not item_found:
        return False, "背包中没有该物品", {}
    
    # 获取当前装备
    equipped = user.get("equipped_items", {})
    current_equipped = equipped.get(slot)
    
    # 卸下当前装备（如果有）
    if current_equipped:
        # 放回背包
        if is_stackable(current_equipped.get("id", "")):
            add_to_inventory(user, current_equipped.get("id"), 1)
        else:
            inventory.append({
                "id": current_equipped.get("id"),
                "name": current_equipped.get("name")
            })
    
    # 装备新物品
    equipped[slot] = {
        "id": item_id,
        "name": item_info.get("name"),
        "effects": item_info.get("effects", {}),
    }
    
    # 从背包移除
    if item_index >= 0:
        if qty > 1:
            inventory[item_index]["quantity"] = qty - 1
        else:
            inventory.pop(item_index)
    
    user["equipped_items"] = equipped
    user["inventory"] = inventory
    
    return True, f"已装备 {item_info.get('name')}", item_info


def unequip_item(user: dict, slot: str) -> tuple[bool, str]:
    """卸下指定栏位的装备"""
    if slot not in SLOTS:
        return False, "无效的栏位"
    
    equipped = user.get("equipped_items", {})
    current = equipped.get(slot)
    
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
    """计算用户已装备物品的总效果"""
    effects = {
        # 属性加成
        "strength_bonus": 0,
        "energy_bonus": 0,
        "mood_bonus": 0,
        "health_bonus": 0,
        "satiety_bonus": 0,
        # 百分比加成
        "work_income_bonus": 0,
        "learn_exp_bonus": 0,
        "entertain_mood_bonus": 0,
        "sleep_strength_bonus": 0,
        "sleep_energy_bonus": 0,
        # 被动效果
        "passive_gold": 0,
        "passive_mood": 0,
        # 时间减少
        "work_time_reduce": 0,
    }
    
    equipped = user.get("equipped_items", {})
    if not equipped:
        return effects
    
    for slot, item_data in equipped.items():
        if not item_data:
            continue
        item_effects = item_data.get("effects", {})
        for effect_key, effect_value in item_effects.items():
            if effect_key in effects:
                effects[effect_key] += effect_value
    
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

def format_item(item_id: str, show_price: bool = True, show_slot: bool = False) -> str:
    """格式化物品显示信息"""
    item = ITEMS.get(item_id, {})
    if not item:
        return "未知物品"
    
    name = item.get("name", "未知")
    rarity = item.get("rarity", "common")
    emoji = RARITY_COLORS.get(rarity, "⚪")
    tier = item.get("tier", 1)
    
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
