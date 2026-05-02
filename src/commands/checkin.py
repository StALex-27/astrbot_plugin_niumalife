"""
签到命令逻辑
"""
import random
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.checkin import get_luck_rating, get_streak_reward, roll_lucky_drop
from ...modules.constants import MAX_ATTRIBUTE


LOCAL_TZ = timezone(timedelta(hours=8))


async def run_checkin_logic(event: AstrMessageEvent, store, renderer):
    """签到命令逻辑（含自动注册）"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    # 自动注册
    is_new_user = False
    if not user:
        nickname = event.get_sender_name()
        user = await store.create_user(user_id, nickname)
        is_new_user = True
    
    now = datetime.now(LOCAL_TZ)
    today_str = now.strftime("%Y-%m-%d")
    checkin_data = user.get("checkin", {})
    last_date = checkin_data.get("last_date")
    
    # 今日已签到
    if last_date == today_str:
        try:
            result = {"luck_value": checkin_data.get("last_luck", 50), "total_gold": 0, "drop_info": None}
            url = await renderer.render_checkin(user, event, result, already_checked=True)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(f"📋 你今天已经签到过了！\\n\\n🔥 连续签到：{checkin_data.get('streak', 0)} 天\\n🎲 今日欧气：{checkin_data.get('last_luck', 50)}\\n\\n明天再来签到吧~")
        return
    
    # 计算连续签到
    streak = checkin_data.get("streak", 0) if last_date else 0
    if last_date:
        try:
            last = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
            delta_days = (now - last).days
            streak = streak + 1 if delta_days == 1 else 1
        except:
            streak = 1
    else:
        streak = 1
    
    # 计算奖励
    luck_value = random.randint(1, 100)
    base_gold = luck_value
    streak_reward = get_streak_reward(streak)
    streak_bonus = streak_reward["gold"] if streak_reward else 0
    
    drop = roll_lucky_drop(streak)
    drop_gold = 0
    drop_info = None
    
    if drop:
        if drop["type"] == "gold":
            drop_gold = drop["amount"]
            drop_info = f"💰 {drop_gold}金币"
        elif drop["type"] == "buff":
            from ...modules.buff import create_buff
            buff_instance = create_buff(drop["buff_id"])
            if buff_instance:
                buffs = checkin_data.get("active_buffs", [])
                buffs.append(buff_instance)
                checkin_data["active_buffs"] = buffs
                drop_info = f"✨ {buff_instance['emoji']} {buff_instance['name']}"
        elif drop["type"] == "food":
            food_name, food_data = drop["food_data"]
            attrs = user["attributes"]
            attrs["satiety"] = min(MAX_ATTRIBUTE, attrs["satiety"] + food_data["restore_satiety"])
            drop_info = f"🍖 {food_name}"
        checkin_data["lucky_drops"] = checkin_data.get("lucky_drops", 0) + 1
    
    total_gold = base_gold + streak_bonus + drop_gold
    
    user["gold"] += total_gold
    luck_history = checkin_data.get("luck_history", [])
    luck_history.append(luck_value)
    if len(luck_history) > 30:
        luck_history = luck_history[-30:]
    
    user["checkin"] = {
        "last_date": today_str,
        "last_luck": luck_value,
        "streak": streak,
        "total_days": checkin_data.get("total_days", 0) + 1,
        "total_gold": checkin_data.get("total_gold", 0) + total_gold,
        "lucky_drops": checkin_data.get("lucky_drops", 0),
        "active_buffs": checkin_data.get("active_buffs", []),
        "luck_history": luck_history,
    }
    await store.update_user(user_id, user)
    
    try:
        result = {
            "luck_value": luck_value,
            "total_gold": total_gold,
            "streak_bonus": streak_bonus,
            "drop_info": drop_info,
            "is_new_user": is_new_user,
        }
        url = await renderer.render_checkin(user, event, result, already_checked=False)
        yield event.image_result(url)
    except Exception:
        rating = get_luck_rating(luck_value)
        msg = f"✅ 签到成功！\\n\\n"
        if is_new_user:
            msg += f"🎉 注册成功！\\n\\n"
        msg += f"{rating['emoji']} {rating['name']}\\n"
        msg += f"💰 +{total_gold}金币 (基础{luck_value}+连续{streak_bonus})\\n"
        msg += f"🔥 连续签到: {streak}天\\n"
        if drop_info:
            msg += f"🎁 {drop_info}\\n"
        yield event.plain_result(msg)
