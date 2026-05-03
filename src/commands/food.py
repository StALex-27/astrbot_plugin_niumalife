"""
娱乐和吃东西命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_ENTERTAIN
from ...modules.constants import ENTERTAINMENTS, FOODS, MAX_ATTRIBUTE


LOCAL_TZ = timezone(timedelta(hours=8))


def _format_entertainment_list() -> str:
    """格式化娱乐列表"""
    items = list(ENTERTAINMENTS.items())[:8]
    return "\n".join([f"{i}. 🎮 {n} {e.get('cost_per_hour', 0)}金/时" for i, (n, e) in enumerate(items, 1)])


def _format_food_list() -> str:
    """格式化食物列表"""
    items = list(FOODS.items())[:8]
    return "\n".join([f"• {n} {f['price']}金 (+{f.get('restore_satiety', 0)}饱食)" for n, f in items])


async def run_entertain_logic(event: AstrMessageEvent, store, parser, renderer):
    """娱乐命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return
    
    if user["status"] != UserStatus.FREE.value:
        yield event.plain_result(f"📋 你正在{user['status']}，无法娱乐")
        return
    
    _, args = parser.parse(event)
    
    ent_name = args[0] if len(args) >= 1 else None
    hours = int(args[1]) if len(args) >= 2 else None
    
    if not ent_name:
        yield event.plain_result(f"🎮 娱乐列表:\\n━━━━━━━━━━━━━━\\n{_format_entertainment_list()}\\n━━━━━━━━━━━━━━\\n回复: /娱乐 名称 小时数\\n例如: /娱乐 游戏 2")
        return
    
    entertainment = ENTERTAINMENTS.get(ent_name)
    if not entertainment:
        yield event.plain_result(f"📋 不存在该娱乐：{ent_name}")
        return
    
    if not hours:
        hours = 2
    
    total_cost = entertainment.get("cost_per_hour", 0) * hours
    if user["gold"] < total_cost:
        yield event.plain_result(f"📋 金币不足！需要 {total_cost} 金币，你只有 {user['gold']} 金币")
        return
    
    now = datetime.now(LOCAL_TZ)
    detail = ActionDetail.create(
        action_type=TICK_TYPE_ENTERTAIN,
        hours=hours,
        start_time=now,
        entertainment_name=ent_name,
        cost_per_hour=entertainment.get("cost_per_hour", 0),
        restore_mood=entertainment.get("restore_mood", 0),
        consume_strength=entertainment.get("consume_strength", 0),
        consume_energy=entertainment.get("consume_energy", 0)
    )
    
    user["status"] = UserStatus.ENTERTAINING.value
    user["current_action"] = TICK_TYPE_ENTERTAIN
    user["action_detail"] = detail
    await store.update_user(user_id, user)
    
    try:
        url = await renderer.render_entertain_start(
            user, event,
            ent_name=ent_name,
            ent_emoji=entertainment.get("emoji", "🎮"),
            hours=hours,
            gain_mood=entertainment.get('restore_mood', 0) * hours,
            consume_satiety=int(entertainment.get('consume_strength', 0) * hours)
        )
        yield event.image_result(url)
    except Exception:
        yield event.plain_result(f"✅ 开始娱乐:\\n━━━━━━━━━━━━━━\\n🎮 {ent_name} x {hours}小时\\n💰 花费: {total_cost}金币\\n━━━━━━━━━━━━━━\\n🎉 开始娱乐！")


async def run_eat_logic(event: AstrMessageEvent, store, parser, renderer):
    """吃东西命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return
    
    _, args = parser.parse(event)
    
    if len(args) < 1:
        yield event.plain_result(f"🍖 食物列表:\\n━━━━━━━━━━━━━━\\n{_format_food_list()}\\n━━━━━━━━━━━━━━\\n回复: /吃 食物名")
        return
    
    food_name = args[0]
    food = FOODS.get(food_name)
    
    if not food:
        yield event.plain_result(f"📋 不存在该食物：{food_name}")
        return
    
    if user["gold"] < food["price"]:
        yield event.plain_result(f"📋 金币不足！需要 {food['price']} 金币，你只有 {user['gold']} 金币")
        return
    
    user["gold"] -= food["price"]
    
    attrs = user["attributes"]
    attrs["strength"] = min(MAX_ATTRIBUTE, attrs["strength"] + food["restore_strength"])
    attrs["energy"] = min(MAX_ATTRIBUTE, attrs["energy"] + food["restore_energy"])
    attrs["mood"] = min(MAX_ATTRIBUTE, attrs["mood"] + food["restore_mood"])
    attrs["health"] = min(MAX_ATTRIBUTE, attrs["health"] + food["restore_health"])
    attrs["satiety"] = min(MAX_ATTRIBUTE, attrs["satiety"] + food["restore_satiety"])
    
    user["attributes"] = attrs
    await store.update_user(user_id, user)
    
    try:
        url = await renderer.render_eat(
            user, event,
            food_name=food_name,
            food_emoji=food.get("emoji", "🍖"),
            restore_health=food.get("restore_health", 0),
            restore_strength=food.get("restore_strength", 0),
            restore_energy=food.get("restore_energy", 0),
            restore_mood=food.get("restore_mood", 0)
        )
        yield event.image_result(url)
    except Exception:
        yield event.plain_result(f"✅ 食用成功:\\n━━━━━━━━━━━━━━\\n🍖 {food_name}\\n💰 -{food['price']}金币\\n━━━━━━━━━━━━━━\\n🎉 食用成功！")
