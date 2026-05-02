"""
档案命令逻辑
"""
import random
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent


LOCAL_TZ = timezone(timedelta(hours=8))


def _format_profile_text(user: dict) -> str:
    """格式化档案文本（纯文本 fallback）"""
    from ...modules.constants import MAX_ATTRIBUTE, DEBUFF_DEFINITIONS
    
    attrs = user.get("attributes", {})
    checkin = user.get("checkin", {})
    last_luck = checkin.get("last_luck", 50)
    
    luck_emoji = "🎲"
    luck_name = "普通人"
    if last_luck >= 90:
        luck_emoji, luck_name = "🤑", "超级欧皇"
    elif last_luck >= 70:
        luck_emoji, luck_name = "😄", "欧皇"
    elif last_luck <= 10:
        luck_emoji, luck_name = "💀", "超级非酋"
    elif last_luck <= 30:
        luck_emoji, luck_name = "😣", "非酋"
    
    buffs = checkin.get("active_buffs", [])
    buff_text = f"({len(buffs)}个Buff)" if buffs else ""
    
    body_p = user.get("body_pressure", 0)
    mind_p = user.get("mind_pressure", 0)
    def pbar(p):
        filled = int(p / 10)
        return "█" * filled + "░" * (10 - filled)
    pressure_lines = f"🏋️ 身体: {pbar(body_p)}{body_p:.0f}%\n🧠 精神: {pbar(mind_p)}{mind_p:.0f}%"
    
    debuffs = user.get("active_debuffs", [])
    debuff_lines = ""
    if debuffs:
        debuff_names = []
        for d in debuffs:
            ddef = DEBUFF_DEFINITIONS.get(d, {})
            if ddef:
                debuff_names.append(f"{ddef.get('emoji', '')}{ddef.get('name', d)}")
        debuff_lines = "\n" + " ".join(debuff_names)
    
    return (
        f"━━━━━━━━━━━━━━\n"
        f"【 牛马档案 】\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {user.get('nickname', '未知')}\n"
        f"💰 {user.get('gold', 0)}金币\n"
        f"🏠 {user.get('residence', '桥下')}\n"
        f"📋 {user.get('status', '空闲')}{debuff_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"❤️ {attrs.get('health', 0)} 💪 {attrs.get('strength', 0)}\n"
        f"⚡ {attrs.get('energy', 0)} 😊 {attrs.get('mood', 0)}\n"
        f"🍖 {attrs.get('satiety', 0)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"【 压力 】\n{pressure_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔥 连续签到: {checkin.get('streak', 0)}天\n"
        f"{luck_emoji} {luck_name} {buff_text}\n"
        f"━━━━━━━━━━━━━━"
    )


async def run_profile_logic(event: AstrMessageEvent, store, renderer):
    """档案命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        try:
            url = await renderer.render_error("未注册", "你还没有签到过！\\n输入 /签到 自动注册并签到", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("📋 你还没有注册！\\n输入 /签到 自动注册并签到")
        return
    
    try:
        url = await renderer.render_profile(user, event)
        yield event.image_result(url)
    except Exception:
        yield event.plain_result(_format_profile_text(user))
