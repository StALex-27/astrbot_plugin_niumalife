"""
装备命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.item import (
    ITEMS, RARITY_COLORS, RARITY_NAMES, SLOTS, SLOT_EMOJI,
    get_equipped_items, equip_item, unequip_item,
    calc_equipped_effects, format_item_effects
)


async def run_equip_logic(event: AstrMessageEvent, store, parser):
    """装备管理命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return
    
    _, args = parser.parse(event)
    inventory = user.get("inventory", [])
    
    # 无参数：显示装备状态
    if not args:
        equipped = get_equipped_items(user)
        effects = calc_equipped_effects(user)
        
        lines = ["━━━━━━━━━━━━━━", "【 装 备 】", "━━━━━━━━━━━━━━"]
        
        for slot, emoji in SLOT_EMOJI.items():
            slot_name = SLOTS.get(slot, slot)
            item = equipped.get(slot)
            if item:
                lines.append(f"{emoji}{slot_name}: {item.get('name', '未知')}")
            else:
                lines.append(f"{emoji}{slot_name}: 空")
        
        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 套装效果 】")
        if effects:
            effect_text = format_item_effects(effects)
            lines.append(effect_text if effect_text else "无")
        else:
            lines.append("无")
        
        lines.append("━━━━━━━━━━━━━━")
        
        if inventory:
            lines.append("【 背包物品 】")
            for i, item in enumerate(inventory, 1):
                item_id = item.get("id", "")
                item_info = ITEMS.get(item_id, {})
                rarity = item_info.get("rarity", "common")
                emoji = RARITY_COLORS.get(rarity, "⚪")
                slot = item_info.get("slot", "")
                slot_name = SLOTS.get(slot, slot)
                lines.append(f"{i}. {emoji}{item.get('name', item_id)} [{slot_name}]")
        else:
            lines.append("【 背包物品 】空")
        
        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 指令说明 】")
        lines.append("/装备 背包序号 - 穿戴装备")
        lines.append("/装备 卸下 栏位 - 卸下装备")
        lines.append("例: /装备 1 或 /装备 卸下 服装")
        
        yield event.plain_result("\n".join(lines))
        return
    
    # 卸下装备
    if args[0] == "卸下" or args[0] == "unequip":
        if len(args) < 2:
            yield event.plain_result("📋 格式: /装备 卸下 栏位\n例: /装备 卸下 服装")
            return
        
        slot = args[1]
        slot_map = {
            "服装": "clothing", "头部": "head", "工具": "tool",
            "饰品": "accessory", "手机": "phone"
        }
        slot = slot_map.get(slot, slot)
        
        if slot not in SLOTS:
            yield event.plain_result(f"📋 无效栏位，可选: 服装/头部/工具/饰品/手机")
            return
        
        success, msg = unequip_item(user, slot)
        if success:
            await store.update_user(user_id, user)
            yield event.plain_result(f"✅ {msg}")
        else:
            yield event.plain_result(f"⚠️ {msg}")
        return
    
    # 穿戴装备
    try:
        idx = int(args[0]) - 1
        if idx < 0 or idx >= len(inventory):
            yield event.plain_result(f"📋 背包序号无效，有效范围 1-{len(inventory)}")
            return
        item_id = inventory[idx].get("id")
    except ValueError:
        item_name = args[0]
        item_id = None
        for inv_item in inventory:
            inv_id = inv_item.get("id", "")
            item_info = ITEMS.get(inv_id, {})
            if item_info.get("name") == item_name or inv_id == item_name:
                item_id = inv_id
                break
        if not item_id:
            yield event.plain_result(f"📋 背包中没有该物品: {item_name}")
            return
    
    success, msg, item_info = equip_item(user, item_id)
    if success:
        await store.update_user(user_id, user)
        effects = item_info.get("effects", {})
        effect_text = format_item_effects(effects) if effects else "无"
        yield event.plain_result(f"✅ {msg}\n\n效果: {effect_text}")
    else:
        yield event.plain_result(f"⚠️ {msg}")
