"""
取消命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus


async def run_cancel_logic(event: AstrMessageEvent, store, renderer):
    """取消命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
        return
    
    if user["status"] == UserStatus.FREE.value:
        yield event.plain_result("📋 你当前没有进行任何动作")
        return
    
    old_status = user.get("status", "动作")
    user["status"] = UserStatus.FREE.value
    user["locked_until"] = None
    user["current_action"] = None
    user["action_detail"] = None
    await store.update_user(user_id, user)
    
    try:
        url = await renderer.render_success(f"✅ 已取消 {old_status}，返回空闲状态", event)
        yield event.image_result(url)
    except Exception:
        yield event.plain_result(f"✅ 已取消 {old_status}，返回空闲状态")
