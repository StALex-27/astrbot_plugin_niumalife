"""
背包命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.item import ITEMS, RARITY_COLORS, SLOTS, SLOT_EMOJI


async def run_backpack_logic(event: AstrMessageEvent, store):
    """背包命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return
    
    inventory = user.get("inventory", [])
    
    if not inventory:
        yield event.plain_result(f"🎒 背包是空的！\\n\\n通过签到或购买获取物品")
        return
    
    lines = ["━━━━━━━━━━━━━━", "【 背包 】", "━━━━━━━━━━━━━━"]
    for i, item in enumerate(inventory, 1):
        name = item.get('name', item.get('id', '未知'))
        qty = item.get('quantity', 1)
        if qty > 1:
            name = f"{name} x{qty}"
        lines.append(f"{i}. {name}")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("使用: /背包 使用 物品名")
    lines.append("      /装备 装备名 穿戴装备")
    
    yield event.plain_result("\n".join(lines))
