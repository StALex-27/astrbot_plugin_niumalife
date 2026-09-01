"""
背包命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.item import ITEMS, RARITY_COLORS, SLOTS, SLOT_EMOJI
from ...modules.renderer import CardRenderer

_card_renderer = CardRenderer()


async def run_backpack_logic(event: AstrMessageEvent, store):
    """背包命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return
    
    inventory = user.get("inventory", [])
    
    if not inventory:
        card_url = await _card_renderer.render_backpack([], user, event)
        yield event.image_result(card_url)
        return
    
    items = []
    for i, item in enumerate(inventory, 1):
        name = item.get('name', item.get('id', '未知'))
        qty = item.get('quantity', 1)
        
        # 获取物品emoji
        item_info = ITEMS.get(item.get('id', ''), {})
        emoji = item_info.get('emoji', '📦')
        
        items.append({
            "name": name,
            "emoji": emoji,
            "quantity": qty,
        })
    
    card_url = await _card_renderer.render_backpack(items, user, event)
    yield event.image_result(card_url)
