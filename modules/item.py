"""
物品系统模块
包含物品效果计算、装备效果等
"""
from .constants import ITEMS, RARITY_COLORS, RARITY_EMOJI


# 从 constants 导入稀有度配置
RARITY_COLORS = {
    "common": "§7",
    "uncommon": "§a",
    "rare": "§9",
    "epic": "§5",
    "legendary": "§6",
}

RARITY_EMOJI = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
}


def calc_equipped_effects(inventory: list[dict]) -> dict:
    """计算已装备物品的总效果
    
    Args:
        inventory: 用户背包列表
    
    Returns:
        dict: 累加后的效果值
    """
    effects = {
        "strength_bonus": 0,
        "energy_bonus": 0,
        "mood_bonus": 0,
        "health_bonus": 0,
        "satiety_bonus": 0,
        "work_income_bonus": 0,
        "exp_bonus": 0,
    }
    
    for item in inventory:
        if item.get("equipped", False):
            item_id = item.get("id", "")
            item_info = ITEMS.get(item_id, {})
            item_effects = item_info.get("effect", {})
            
            for effect_key, effect_value in item_effects.items():
                if effect_key in effects:
                    effects[effect_key] += effect_value
    
    return effects


def get_item_rarity(item_id: str) -> str:
    """获取物品稀有度
    
    Args:
        item_id: 物品ID
    
    Returns:
        str: 稀有度等级
    """
    item_info = ITEMS.get(item_id, {})
    return item_info.get("rarity", "common")


def format_item(item_id: str, show_price: bool = True) -> str:
    """格式化物品显示信息
    
    Args:
        item_id: 物品ID
        show_price: 是否显示价格
    
    Returns:
        str: 格式化后的物品字符串
    """
    item = ITEMS.get(item_id, {})
    if not item:
        return "未知物品"
    
    name = item.get("name", "未知")
    rarity = item.get("rarity", "common")
    emoji = RARITY_EMOJI.get(rarity, "⚪")
    
    result = f"{emoji} {name}"
    
    if show_price:
        price = item.get("price", 0)
        result += f" (§e{price}金§r)"
    
    return result


def can_buy_item(user_gold: int, item_id: str) -> tuple[bool, str]:
    """检查是否能购买物品
    
    Args:
        user_gold: 用户金币
        item_id: 物品ID
    
    Returns:
        tuple[bool, str]: (是否能购买, 原因)
    """
    item = ITEMS.get(item_id, {})
    if not item:
        return False, "物品不存在"
    
    price = item.get("price", 0)
    if user_gold < price:
        return False, f"金币不足，需要 {price} 金币"
    
    return True, ""