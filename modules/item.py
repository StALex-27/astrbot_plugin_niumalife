"""
物品系统模块 v2
包含物品效果计算、装备栏位管理等
基于5栏位系统: clothing, head, tool, accessory, phone
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
# 装备栏位管理
# ============================================================

def get_equipped_items(user: dict) -> dict:
    """获取用户已装备的物品
    
    Args:
        user: 用户数据
    
    Returns:
        dict: {slot: item_data} 已装备的物品
    """
    equipped = user.get("equipped_items", {})
    return equipped


def equip_item(user: dict, item_id: str) -> tuple[bool, str, dict]:
    """装备物品到对应栏位
    
    Args:
        user: 用户数据
        item_id: 物品ID
    
    Returns:
        tuple[bool, str, dict]: (是否成功, 消息, 装备的物品数据)
    """
    item_info = ITEMS.get(item_id)
    if not item_info:
        return False, "物品不存在", {}
    
    slot = item_info.get("slot")
    if not slot:
        return False, "该物品无法装备", {}
    
    # 检查背包中是否有该物品
    inventory = user.get("inventory", [])
    item_found = None
    item_index = -1
    for i, inv_item in enumerate(inventory):
        if inv_item.get("id") == item_id:
            item_found = inv_item
            item_index = i
            break
    
    if item_found is None:
        return False, "背包中没有该物品", {}
    
    # 获取当前装备
    equipped = user.get("equipped_items", {})
    current_equipped = equipped.get(slot)
    
    # 卸下当前装备（如果有）
    if current_equipped:
        # 把当前装备放回背包
        inventory.append({
            "id": current_equipped.get("id"),
            "name": current_equipped.get("name"),
        })
    
    # 装备新物品
    equipped[slot] = {
        "id": item_id,
        "name": item_info.get("name"),
        "effects": item_info.get("effects", {}),
    }
    
    # 从背包移除
    if item_index >= 0:
        inventory.pop(item_index)
    
    user["equipped_items"] = equipped
    user["inventory"] = inventory
    
    return True, f"已装备 {item_info.get('name')}", item_info


def unequip_item(user: dict, slot: str) -> tuple[bool, str]:
    """卸下指定栏位的装备
    
    Args:
        user: 用户数据
        slot: 栏位名
    
    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    if slot not in SLOTS:
        return False, "无效的栏位"
    
    equipped = user.get("equipped_items", {})
    current = equipped.get(slot)
    
    if not current:
        return False, "该栏位没有装备"
    
    # 放入背包
    inventory = user.get("inventory", [])
    inventory.append({
        "id": current.get("id"),
        "name": current.get("name"),
    })
    
    # 清除装备
    del equipped[slot]
    user["equipped_items"] = equipped
    user["inventory"] = inventory
    
    return True, f"已卸下 {current.get('name')}"


def auto_equip_if_empty(user: dict, item_id: str) -> bool:
    """如果对应栏位为空，自动装备物品
    
    Args:
        user: 用户数据
        item_id: 物品ID
    
    Returns:
        bool: 是否自动装备了
    """
    item_info = ITEMS.get(item_id)
    if not item_info:
        return False
    
    slot = item_info.get("slot")
    if not slot:
        return False
    
    equipped = user.get("equipped_items", {})
    
    if slot not in equipped or equipped[slot] is None:
        # 自动装备
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
    
    Args:
        user: 用户数据
    
    Returns:
        dict: 累加后的效果值
    """
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
    """获取已装备物品的简要描述
    
    Args:
        user: 用户数据
    
    Returns:
        str: 格式化的装备描述
    """
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
# 物品查询
# ============================================================

def get_item_by_id(item_id: str) -> dict:
    """获取物品信息"""
    return ITEMS.get(item_id, {})


def get_items_by_slot(slot: str) -> list[dict]:
    """获取指定栏位的所有物品"""
    items = []
    for item_id, item_info in ITEMS.items():
        if item_info.get("slot") == slot:
            items.append({
                "id": item_id,
                **item_info
            })
    # 按 tier 排序
    items.sort(key=lambda x: x.get("tier", 1))
    return items


def get_items_by_rarity(rarity: str) -> list[dict]:
    """获取指定稀有度的所有物品"""
    items = []
    for item_id, item_info in ITEMS.items():
        if item_info.get("rarity") == rarity:
            items.append({
                "id": item_id,
                **item_info
            })
    return items


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
        if key.endswith("_bonus") and isinstance(value, (int, float)) and value < 1:
            # 百分比形式
            parts.append(f"{name}+{int(value*100) if value >= 1 else value*100:.0f}%")
        elif key == "passive_gold" or key == "passive_mood":
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
