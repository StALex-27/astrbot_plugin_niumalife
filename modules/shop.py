"""
商店系统模块
包含商店配置、商品管理、购买逻辑
"""
import random
from datetime import datetime, timezone
from typing import Optional

from .constants import ITEMS


# ============================================================
# 商店配置
# ============================================================

TICKETS_PER_HOUR = 60

SHOPS = {
    "基础商店": {
        "name": "基础商店",
        "emoji": "🏪",
        "desc": "日常所需，应有尽有",
        "fixed_items": [
            "泡面", "矿泉水", "面包", "薯片", "创可贴", "纸巾"
        ],
        "random_pool": ["肉包", "巧克力", "电池", "牙膏", "维生素"],
        "random_count": 3,
        "refresh_interval": "1h",  # 1小时刷新随机商品
    },
    "小吃街": {
        "name": "小吃街",
        "emoji": "🍜",
        "desc": "各地美食，吃货天堂",
        "fixed_items": [
            "关东煮", "奶茶", "咖啡", "炸鸡", "鸡蛋"
        ],
        "random_pool": [
            "披萨", "火锅", "沙拉", "水果", "肉包", "豪华便当"
        ],
        "random_count": 3,
        "refresh_interval": "3h",
    },
    "药品店": {
        "name": "药品店",
        "emoji": "💊",
        "desc": "健康保障，药品齐全",
        "fixed_items": [
            "创可贴", "止痛药", "维生素"
        ],
        "random_pool": [
            "感冒药", "胃药", "能量饮料", "安眠药"
        ],
        "random_count": 2,
        "refresh_interval": "6h",
    },
    "超市": {
        "name": "超市",
        "emoji": "🛒",
        "desc": "一站式购物，生活必备",
        "fixed_items": [
            "电池", "纸巾", "牙膏", "沐浴露"
        ],
        "random_pool": [
            "雨伞", "防晒霜", "零食礼包", "牛奶", "水果"
        ],
        "random_count": 3,
        "refresh_interval": "12h",
    },
    "工具店": {
        "name": "工具店",
        "emoji": "🔧",
        "desc": "装备升级，效率加倍",
        "fixed_items": [
            "帆布双肩包", "移动电源"
        ],
        "random_pool": [
            "降噪耳塞", "机械键盘", "雨伞", "防晒霜"
        ],
        "random_count": 2,
        "refresh_interval": "24h",
        "category": "tool",
    },
    "数码店": {
        "name": "数码店",
        "emoji": "📱",
        "desc": "科技前沿，数码潮流",
        "fixed_items": [
            "备用机", "红米Note12"
        ],
        "random_pool": [
            "小米14Ultra", "华为Mate60Pro", "降噪耳机"
        ],
        "random_count": 2,
        "refresh_interval": "24h",
        "category": "phone",
    },
    "服装店": {
        "name": "服装店",
        "emoji": "👔",
        "desc": "时尚穿搭，提升魅力",
        "fixed_items": [
            "格子衬衫", "棒球帽", "钥匙扣"
        ],
        "random_pool": [
            "纯色T恤", "品牌卫衣", "防蓝光眼镜"
        ],
        "random_count": 2,
        "refresh_interval": "12h",
        "category": "clothing",
    },
    "饰品店": {
        "name": "饰品店",
        "emoji": "💍",
        "desc": "精致饰品，品味之选",
        "fixed_items": [
            "钥匙扣", "品牌钱包"
        ],
        "random_pool": [
            "平安玉佩", "AppleWatch", "降噪耳机"
        ],
        "random_count": 2,
        "refresh_interval": "24h",
        "category": "accessory",
    },
}


# 随机商店的全局随机池（不在其他固定商店中的稀有物品）
GLOBAL_RANDOM_POOL = [
    "豪华便当", "自助餐券", "安眠药", "能量饮料",
    "零食礼包", "沙拉", "火锅", "披萨",
    "机械键盘", "商务休闲装", "智能眼镜",
    "AppleWatch", "iPhone16ProMax"
]


# ============================================================
# 商店刷新状态
# ============================================================

def parse_refresh_interval(interval: str) -> int:
    """解析刷新间隔（转换为分钟）
    
    Args:
        interval: 间隔字符串，如 "1h", "3h", "24h"
    
    Returns:
        int: 分钟数
    """
    interval = interval.lower().strip()
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    elif interval.endswith("d"):
        return int(interval[:-1]) * 60 * 24
    elif interval.endswith("m"):
        return int(interval[:-1])
    else:
        return int(interval)


def should_refresh(last_time: Optional[str], interval: str) -> bool:
    """检查是否应该刷新
    
    Args:
        last_time: 上次刷新时间 (ISO格式)
        interval: 刷新间隔
    
    Returns:
        bool: 是否应该刷新
    """
    if last_time is None:
        return True
    
    try:
        last = datetime.fromisoformat(last_time)
        now = datetime.now(timezone.utc)
        elapsed = (now - last).total_seconds() / 60
        return elapsed >= parse_refresh_interval(interval)
    except:
        return True


# ============================================================
# 商店状态管理
# ============================================================

def get_shop_state(plugin) -> dict:
    """获取商店状态（从KV存储）"""
    return plugin._shop_state or {}


def save_shop_state(plugin, state: dict):
    """保存商店状态"""
    plugin._shop_state = state


def refresh_shop_items(plugin, shop_id: str) -> list:
    """刷新商店的随机商品
    
    Args:
        plugin: 插件实例
        shop_id: 商店ID
    
    Returns:
        list: 刷新后的随机商品ID列表
    """
    shop = SHOPS.get(shop_id)
    if not shop:
        return []
    
    pool = shop.get("random_pool", [])
    count = shop.get("random_count", 3)
    
    if len(pool) <= count:
        return pool.copy()
    
    # 随机选择
    selected = random.sample(pool, count)
    
    # 更新状态
    state = get_shop_state(plugin)
    state[shop_id] = {
        "random_items": selected,
        "last_refresh": datetime.now(timezone.utc).isoformat()
    }
    save_shop_state(plugin, state)
    
    return selected


def get_shop_items(plugin, shop_id: str) -> tuple[list, list]:
    """获取商店商品
    
    Args:
        plugin: 插件实例
        shop_id: 商店ID
    
    Returns:
        tuple[list, list]: (固定商品, 随机商品)
    """
    shop = SHOPS.get(shop_id)
    if not shop:
        return [], []
    
    fixed = shop.get("fixed_items", [])
    
    # 检查随机商品是否需要刷新
    state = get_shop_state(plugin)
    shop_state = state.get(shop_id, {})
    random_items = shop_state.get("random_items", [])
    last_refresh = shop_state.get("last_refresh")
    
    interval = shop.get("refresh_interval", "1h")
    if should_refresh(last_refresh, interval) or not random_items:
        random_items = refresh_shop_items(plugin, shop_id)
    
    return fixed, random_items


def get_global_random_items(plugin, count: int = 3) -> list:
    """获取全局随机商品（用于基础商店的随机区）
    
    Args:
        plugin: 插件实例
        count: 商品数量
    
    Returns:
        list: 随机商品ID列表
    """
    state = get_shop_state(plugin)
    global_state = state.get("_global_random", {})
    last_refresh = global_state.get("last_refresh")
    
    if should_refresh(last_refresh, "1h"):
        selected = random.sample(GLOBAL_RANDOM_POOL, min(count, len(GLOBAL_RANDOM_POOL)))
        global_state = {
            "items": selected,
            "last_refresh": datetime.now(timezone.utc).isoformat()
        }
        state["_global_random"] = global_state
        save_shop_state(plugin, state)
        return selected
    
    return global_state.get("items", [])


# ============================================================
# 购买逻辑
# ============================================================

def is_item_in_shop(plugin, shop_id: str, item_id: str) -> bool:
    """检查物品是否在商店中（固定+随机）
    
    Args:
        plugin: 插件实例
        shop_id: 商店ID
        item_id: 物品ID
    
    Returns:
        bool: 物品是否在商店中
    """
    fixed, random_items = get_shop_items(plugin, shop_id)
    return item_id in fixed or item_id in random_items


def is_item_available_global(plugin, item_id: str) -> bool:
    """检查物品是否在任何商店中可购买
    
    Args:
        plugin: 插件实例
        item_id: 物品ID
    
    Returns:
        bool: 物品是否可购买
    """
    for shop_id in SHOPS.keys():
        if is_item_in_shop(plugin, shop_id, item_id):
            return True
    return False


def buy_item(
    plugin, user: dict, shop_id: str, item_id: str, quantity: int = 1
) -> tuple[bool, str]:
    """购买物品
    
    Args:
        plugin: 插件实例
        user: 用户数据
        shop_id: 商店ID
        item_id: 物品ID
        quantity: 数量
    
    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    shop = SHOPS.get(shop_id)
    if not shop:
        return False, "商店不存在"
    
    # 检查物品是否在商店中
    fixed, random_items = get_shop_items(plugin, shop_id)
    if item_id not in fixed and item_id not in random_items:
        return False, f"{shop['emoji']} {shop['name']} 没有该商品"
    
    item = ITEMS.get(item_id)
    if not item:
        return False, "物品不存在"
    
    # 检查金币
    price = item.get("price", 0) * quantity
    if user.get("gold", 0) < price:
        return False, f"金币不足，需要 {price} 金币"
    
    # 检查背包
    category = item.get("category", "")
    subcategory = item.get("subcategory", "")
    is_food = category == "food" or category == "medicine" or category == "daily"
    
    if is_food:
        # 食物/药品可以堆叠，检查是否有同名物品
        inventory = user.get("inventory", [])
        stack_found = False
        stack_idx = -1
        
        if item.get("stackable", False):
            for i, inv_item in enumerate(inventory):
                if inv_item.get("id") == item_id:
                    stack_found = True
                    stack_idx = i
                    break
        
        if stack_found and item.get("stackable"):
            # 堆叠
            inventory[stack_idx]["quantity"] = inventory[stack_idx].get("quantity", 1) + quantity
        else:
            # 新增
            inventory.append({
                "id": item_id,
                "name": item.get("name"),
                "quantity": quantity
            })
    else:
        # 非堆叠物品（装备等）
        for _ in range(quantity):
            inventory = user.get("inventory", [])
            
            # 检查装备栏位是否为空
            slot = item.get("slot")
            if slot:
                equipped = user.get("equipped_items", {})
                if slot not in equipped or not equipped[slot]:
                    # 自动装备
                    equipped[slot] = {
                        "id": item_id,
                        "name": item.get("name"),
                        "effects": item.get("effects", {})
                    }
                    user["equipped_items"] = equipped
                    # 不加入背包
                else:
                    # 栏位被占用，加入背包
                    inventory.append({
                        "id": item_id,
                        "name": item.get("name")
                    })
            else:
                inventory.append({
                    "id": item_id,
                    "name": item.get("name")
                })
    
    user["inventory"] = inventory
    user["gold"] = user.get("gold", 0) - price
    
    return True, f"购买成功！{'[已自动装备]' if slot and slot not in (user.get('equipped_items') or {}) else ''}"


# ============================================================
# 商店列表
# ============================================================

def get_all_shops() -> list:
    """获取所有商店列表"""
    return list(SHOPS.keys())


def format_shop_list(plugin) -> str:
    """格式化商店列表"""
    lines = ["━━━━━━━━━━━━━━", "【 商 店 列 表 】", "━━━━━━━━━━━━━━"]
    
    for shop_id, shop in SHOPS.items():
        fixed, random_items = get_shop_items(plugin, shop_id)
        total = len(fixed) + len(random_items)
        lines.append(f"{shop['emoji']} /商店 {shop_id}")
        lines.append(f"   {shop['desc']} ({total}件)")
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("指令: /商店 <商店名> 查看商品")
    lines.append("      /商店 买 <物品名> [数量] 购买")
    
    return "\n".join(lines)


def format_shop_items(plugin, shop_id: str) -> str:
    """格式化商店商品列表"""
    shop = SHOPS.get(shop_id)
    if not shop:
        return "商店不存在"
    
    fixed, random_items = get_shop_items(plugin, shop_id)
    
    lines = [
        "━━━━━━━━━━━━━━",
        f"{shop['emoji']} 【 {shop['name']} 】",
        f"{shop['desc']}",
        "━━━━━━━━━━━━━━",
    ]
    
    # 固定商品
    if fixed:
        lines.append("【 常驻商品 】")
        for item_id in fixed:
            item = ITEMS.get(item_id, {})
            price = item.get("price", 0)
            effects = format_item_effects_short(item.get("effects", {}))
            lines.append(f"• {item.get('name', item_id)} §e{price}金§r {effects}")
    
    # 随机商品
    if random_items:
        lines.append("【 限时商品 】")
        for item_id in random_items:
            item = ITEMS.get(item_id, {})
            price = item.get("price", 0)
            effects = format_item_effects_short(item.get("effects", {}))
            lines.append(f"★ {item.get('name', item_id)} §e{price}金§r {effects}")
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"购买: /商店 买 <物品名> [数量]")
    
    return "\n".join(lines)


def format_item_effects_short(effects: dict) -> str:
    """格式化物品效果（简短）"""
    if not effects:
        return ""
    
    parts = []
    effect_names = {
        "satiety": "饱食",
        "mood": "心情",
        "health": "健康",
        "energy": "精力",
        "strength": "体力",
    }
    
    for key, value in effects.items():
        name = effect_names.get(key, key)
        if isinstance(value, (int, float)) and value > 0:
            parts.append(f"+{value}{name}")
    
    return f"({', '.join(parts)})" if parts else ""
