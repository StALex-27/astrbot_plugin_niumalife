"""
商店命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.shop import SHOPS, get_shop_items, buy_item
from ...modules.item import ITEMS


def format_food_effects(effects: dict) -> str:
    """格式化食物/药品效果（简短）"""
    if not effects:
        return ""
    
    effect_names = {
        "satiety": "饱食",
        "mood": "心情",
        "health": "健康",
        "energy": "精力",
        "strength": "体力",
    }
    
    parts = []
    for key, value in effects.items():
        name = effect_names.get(key, key)
        if isinstance(value, (int, float)) and value > 0:
            parts.append(f"+{value}{name}")
    
    return f"({', '.join(parts)})" if parts else ""


async def run_shop_show_all_logic(user):
    """显示所有商店列表"""
    from ...src.commands.interactive import get_job_mgr, get_favor_mgr
    
    jmgr = get_job_mgr()
    fmgr = get_favor_mgr()
    
    lines = ["═══════════════════════════", "    「 商 店 首 页 」", "═══════════════════════════"]
    
    lines.append("\n🏪 基础商店")
    lines.append("  /商店 买 <物品名> 购买")
    for shop_id in ["小吃街", "药品店", "超市", "工具店"]:
        shop = SHOPS.get(shop_id, {})
        lines.append(f"  {shop.get('emoji', '🏪')} /商店 {shop_id}")
    
    lines.append("\n🏢 公司商店")
    summary = fmgr.get_all_companies_summary(user)
    for s in summary:
        emoji = s.get("emoji", "")
        name = s.get("name", s["company_id"])
        level = s["level"]
        lines.append(f"  {emoji} /商店 {s['company_id']} (Lv.{level})")
    
    lines.append("\n═══════════════════════════")
    lines.append("💰 金币: {}".format(int(user.get('gold', 0))))
    lines.append("═══════════════════════════")
    
    return "\n".join(lines)


async def run_shop_show_companies_list_logic(user):
    """显示公司商店列表"""
    from ...src.commands.interactive import get_job_mgr, get_favor_mgr
    
    jmgr = get_job_mgr()
    fmgr = get_favor_mgr()
    
    summary = fmgr.get_all_companies_summary(user)
    
    lines = ["═══════════════════════════", "    「 公 司 商 店 」", "═══════════════════════════"]
    
    for s in summary:
        emoji = s.get("emoji", "")
        name = s.get("name", s["company_id"])
        level_bar = "★" * min(s["level"], 10) + "☆" * max(0, 10 - s["level"])
        lines.append(
            f"\n{emoji} {name}"
            f"\n   ❤️ {s['favorability']} | {level_bar}"
            f"\n   ⭐ Lv.{s['level']} {s['level_name']}"
            f"\n   📍 /商店 {s['company_id']}"
        )
        
    lines.append("\n═══════════════════════════")
    
    return "\n".join(lines)


async def run_shop_show_company_logic(user, company_id):
    """显示特定公司商店"""
    from ...src.commands.interactive import get_job_mgr, get_favor_mgr, get_company_shop_mgr
    
    jmgr = get_job_mgr()
    company = jmgr.get_company_info(company_id)
    if not company:
        return f"❌ 未找到公司: {company_id}"
        
    fmgr = get_favor_mgr()
    favor = fmgr.get_company_favorability(user, company_id)
    level = fmgr.get_favor_level(favor)
    
    cshop = get_company_shop_mgr()
    items = cshop.get_company_shop_items(company_id, favor)
    
    lines = [
        "═══════════════════════════",
        f"    「 {company.get('emoji', '')} {company.get('name', company_id)} 商店 」",
        "═══════════════════════════",
        f"❤️ 好感度: {favor} (Lv.{level['level']} {level['name']})",
    ]
    
    if not items:
        lines.append("\n📦 暂无可购买商品")
        lines.append(f"\n❤️ 提升好感度到 Lv.{level['level']+1} 解锁更多商品")
    else:
        lines.append(f"\n📦 商品列表:")
        for item in items:
            price = item.get("price", 0)
            price_str = f"§e{price}金§r"
            item_type = item.get("type", "物品")
            rarity = item.get("rarity", "普通")
            rarity_emoji = {"普通": "⚪", "稀有": "🔵", "史诗": "🟣", "传说": "🟡"}.get(rarity, "⚪")
            lines.append(
                f"\n  {rarity_emoji} {item.get('name', '???')}"
                f"\n    💰 {price_str} | {item_type}"
            )
            
    lines.append("\n═══════════════════════════")
    lines.append("购买: /商店 买 <物品名> 或 /商店 买 <公司> <物品名>")
    
    return "\n".join(lines)


async def run_shop_logic(event: AstrMessageEvent, store, parser):
    """商店命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return
        
    _, args = parser.parse(event)
    
    # 无参数：显示商店列表
    if not args:
        yield event.plain_result(await run_shop_show_all_logic(user))
        return
        
    sub_cmd = args[0]
    
    from ...src.commands.interactive import get_job_mgr
    jmgr = get_job_mgr()
    company = jmgr.get_company_info(sub_cmd)
    if company:
        yield event.plain_result(await run_shop_show_company_logic(user, sub_cmd))
        return
    
    if sub_cmd in ["公司", "company"]:
        yield event.plain_result(await run_shop_show_companies_list_logic(user))
        return
    
    if sub_cmd == "列表" and len(args) > 1 and args[1] in ["公司", "company"]:
        yield event.plain_result(await run_shop_show_companies_list_logic(user))
        return
    
    # 基础商店处理
    if sub_cmd in SHOPS:
        shop_id = sub_cmd
        shop = SHOPS.get(shop_id)
        fixed, random_items = get_shop_items(store, shop_id)
        
        lines = ["═══════════════════════════", f"{shop.get('emoji', '🏪')} 【 {shop.get('name', shop_id)} 】", f"{shop.get('desc', '')}", "═══════════════════════════"]
        
        if fixed:
            lines.append("【 常驻商品 】")
            for item_id in fixed:
                item = ITEMS.get(item_id, {})
                price = item.get('price', 0)
                effects = item.get('effects', {})
                effect_str = format_food_effects(effects)
                lines.append(f"• {item.get('name', item_id)} §e{price}金§r {effect_str}")
        
        if random_items:
            lines.append("【 限时商品 】")
            for item_id in random_items:
                item = ITEMS.get(item_id, {})
                price = item.get('price', 0)
                effects = item.get('effects', {})
                effect_str = format_food_effects(effects)
                lines.append(f"★ {item.get('name', item_id)} §e{price}金§r {effect_str}")
        
        lines.append("═══════════════════════════")
        lines.append("购买: /商店 买 <物品名> [数量]")
        
        yield event.plain_result("\n".join(lines))
        return
    
    # 购买指令
    if sub_cmd == "买":
        if len(args) < 2:
            yield event.plain_result("📋 格式: /商店 买 <物品名> [数量]\n例: /商店 买 泡面 3")
            return
        
        item_name = args[1]
        quantity = int(args[2]) if len(args) > 2 else 1
        
        item_id = None
        for iid, item in ITEMS.items():
            if item.get('name') == item_name or iid == item_name:
                item_id = iid
                break
        
        if not item_id:
            yield event.plain_result(f"❌ 找不到物品: {item_name}")
            return
        
        price = ITEMS[item_id].get('price', 0) * quantity
        if user.get('gold', 0) < price:
            yield event.plain_result(f"❌ 金币不足！需要 {price} 金币，你只有 {int(user.get('gold', 0))} 金币")
            return
        
        success, msg = buy_item(user, item_id, quantity)
        if success:
            user['gold'] -= price
            await store.update_user(user_id, user)
            yield event.plain_result(msg)
        else:
            yield event.plain_result(f"❌ {msg}")
        return
    
    # 未知命令
    yield event.plain_result(await run_shop_show_all_logic(user))
