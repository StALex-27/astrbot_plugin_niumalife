"""住所命令逻辑"""
from astrbot.api.event import AstrMessageEvent

from ...modules.constants import RESIDENCES
from ...modules.templates import CardType


async def run_residence_logic(event: AstrMessageEvent, store, parser, sender):
    """住所命令逻辑.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return

    _, args = parser.parse(event)

    residence_name = user.get("residence", "桥下")
    res_info = RESIDENCES.get(residence_name, RESIDENCES["桥下"])

    if not args:
        # 9/6: 改用 sender.send_card() (CardType.RESIDENCE 渲染模板)
        data = {
            "user_id": user_id,
            "residence_name": residence_name,
            "res_info": res_info,
            "strength_recovery": res_info.get('strength_recovery', 2),
            "energy_recovery": res_info.get('energy_recovery', 2),
            "sleep_bonus": res_info.get('sleep_bonus', 1.0),
        }
        fallback_text = (
            f"🏠 当前住所: {residence_name}\\n"
            f"━━━━━━━━━━━━━━\\n"
            f"💪 体力恢复: +{res_info.get('strength_recovery', 2)}/时\\n"
            f"⚡ 精力恢复: +{res_info.get('energy_recovery', 2)}/时\\n"
            f"😴 睡眠加成: x{res_info.get('sleep_bonus', 1.0)}\\n"
            f"━━━━━━━━━━━━━━\\n"
            f"回复: /住 租/买 名称\\n"
            f"例如: /住 租 公寓"
        )
        async for r in sender.send_card(
            event, CardType.RESIDENCE, data, fallback_text=fallback_text,
        ):
            yield r
        return

    action = args[0]
    target_name = args[1] if len(args) > 1 else None

    if action in ["租", "租房"] and target_name:
        target = RESIDENCES.get(target_name)
        if not target or target.get("type") == "永久":
            yield event.plain_result(f"📋 不存在该房产或不可租：{target_name}")
            return

        daily_rent = target.get("rent", 0)
        if user["gold"] < daily_rent:
            yield event.plain_result(f"📋 金币不足！租金 {daily_rent} 金币/天，你只有 {user['gold']} 金币")
            return

        user["residence"] = target_name
        user["gold"] -= daily_rent
        await store.update_user(user_id, user)
        yield event.plain_result(f"✅ 租房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{daily_rent}金币 (日租)\\n━━━━━━━━━━━━━━\\n🎉 欢迎入住！")

    elif action in ["买", "买房"] and target_name:
        target = RESIDENCES.get(target_name)
        if not target or target.get("type") == "租":
            yield event.plain_result(f"📋 不存在该房产或不可买：{target_name}")
            return

        price = target.get("price", 0)
        if user["gold"] < price:
            yield event.plain_result(f"📋 金币不足！售价 {price} 金币，你只有 {user['gold']} 金币")
            return

        user["residence"] = target_name
        user["gold"] -= price
        await store.update_user(user_id, user)
        yield event.plain_result(f"✅ 购房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{price}金币\\n━━━━━━━━━━━━━━\\n🎉 恭喜拥有房产！")

    else:
        lines = ["🏠 住所操作:", "━━━━━━━━━━━━━━", "• /住 - 查看当前住所", "• /住 租 名称 - 租房", "• /住 买 名称 - 买房", "━━━━━━━━━━━━━━", "可用房产:"]
        for k, v in list(RESIDENCES.items())[:5]:
            t = v.get('type', '')
            p = v.get('rent', v.get('price', 0))
            lines.append(f"• {k} ({t}-{p}金)")
        yield event.plain_result("\\n".join(lines))