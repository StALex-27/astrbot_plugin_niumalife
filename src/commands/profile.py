"""档案命令 / 档案 渲染"""
from astrbot.api.event import AstrMessageEvent


def _clamp(v, lo=0, hi=100):
    """9/5: 把数值限制到 [lo, hi]，避免显示 -7.93 这种怪值"""
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0


def _format_profile_text(user: dict) -> str:
    """纯文本格式档案（渲染失败时的降级）"""
    attrs = user.get("attributes", {}) or {}

    # debuff 列表
    debuff_lines = ""
    if user.get("debuffs"):
        from ...modules.constants import DEBUFF_DEFINITIONS
        debuff_names = []
        for d in user["debuffs"]:
            ddef = DEBUFF_DEFINITIONS.get(d, {})
            debuff_names.append(f"{ddef.get('emoji', '')}{ddef.get('name', d)}")
        debuff_lines = "\n" + " ".join(debuff_names)

    # 压力条
    pressure_lines = ""
    physical = user.get("physical_stress", 0)
    mental = user.get("mental_stress", 0)
    if physical or mental:
        bar_full = "█"
        bar_empty = "░"
        bar_len = 10
        ph_pct = min(100, max(0, int(physical)))
        mt_pct = min(100, max(0, int(mental)))
        ph_bar = bar_full * (ph_pct * bar_len // 100) + bar_empty * (bar_len - ph_pct * bar_len // 100)
        mt_bar = bar_full * (mt_pct * bar_len // 100) + bar_empty * (bar_len - mt_pct * bar_len // 100)
        pressure_lines = f"🏋️ 身体: {ph_bar}{ph_pct}%\n🧠 精神: {mt_bar}{mt_pct}%"

    # 9/5: clamp 数值到 [0, 100]
    health = _clamp(attrs.get("health", 0))
    strength = _clamp(attrs.get("strength", 0))
    energy = _clamp(attrs.get("energy", 0))
    mood = _clamp(attrs.get("mood", 0))
    satiety = _clamp(attrs.get("satiety", 0))

    return (
        f"━━━━━━━━━━━━━━\n"
        f"【 牛马档案 】\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {user.get('nickname', user.get('user_id', '?'))}\n"
        f"💰 {int(user.get('gold', 0))}金币\n"
        f"🏠 {user.get('residence', '桥下')}\n"
        f"📋 {user.get('status', '空闲')}{debuff_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"❤️ {health:.0f} 💪 {strength:.0f}\n"
        f"⚡ {energy:.0f} 😊 {mood:.0f}\n"
        f"🍖 {satiety:.0f}\n"
        f"━━━━━━━━━━━━━━\n"
        f"【 压力 】\n{pressure_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔥 连续签到: {user.get('streak_days', 0)}天\n"
        f"🎲 {user.get('title', '普通人')}\n"
        f"━━━━━━━━━━━━━━\n"
    )


async def run_profile_logic(event: AstrMessageEvent, store, sender):
    """档案命令逻辑.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    sender 内部统一: 渲染成功发图, 失败 fallback 文本, 异常捕获不冒泡。
    9/6+: ViewSpec 应用 - 用 view_for_profile_card(user) 一次拿齐 data。
    """
    from ..data.user_view import view_for_profile_card
    from ...modules.templates import CardType
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        async for r in sender.send_card(
            event, CardType.ERROR,
            {"title": "未注册", "message": "你还没有签到过！\n输入 /签到 自动注册并签到"},
            fallback_text="📋 你还没有注册！\n输入 /签到 自动注册并签到",
        ):
            yield r
        return

    # 9/6: ViewSpec 应用 - 用 view_for_profile_card(user) 一次拿齐 data
    # 不再让 render_profile 内部散落 user.get("attributes") 等嵌套
    async for r in sender.send_card(
        event, CardType.PROFILE,
        view_for_profile_card(user),
        fallback_text=_format_profile_text(user),
    ):
        yield r