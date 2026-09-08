"""取消命令逻辑"""
from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.templates import CardType


async def run_cancel_logic(event: AstrMessageEvent, store, sender):
    """取消命令逻辑.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return

    if user["status"] == UserStatus.FREE:
        yield event.plain_result("📋 你当前没有进行任何动作")
        return

    old_status = user.get("status", "动作")
    user["status"] = UserStatus.FREE
    user["locked_until"] = None
    user["current_action"] = None
    user["action_detail"] = None
    await store.update_user(user_id, user)

    # 9/6: 改用 sender.send_card() (CardType.SUCCESS 渲染模板)
    async for r in sender.send_card(
        event, CardType.SUCCESS,
        {"message": f"✅ 已取消 {old_status}，返回空闲状态", "gold_delta": 0},
        fallback_text=f"✅ 已取消 {old_status}，返回空闲状态",
    ):
        yield r