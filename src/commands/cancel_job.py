"""
取消委托命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...src.commands.interactive import get_job_mgr


async def run_cancel_job_logic(event: AstrMessageEvent, store, parser):
    """取消委托"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！")
        return

    _, args = parser.parse(event)
    jmgr = get_job_mgr()

    if not args:
        yield event.plain_result("请指定要取消的委托编号\n格式: /取消委托 <编号>")
        return

    try:
        idx = int(args[0]) - 1
    except ValueError:
        yield event.plain_result("编号必须是数字")
        return

    in_progress = jmgr.get_player_current_jobs(user)
    if idx < 0 or idx >= len(in_progress):
        yield event.plain_result(f"无效的委托编号，有效范围: 1-{len(in_progress)}")
        return

    job_id = in_progress[idx]["job_id"]
    success, msg = jmgr.cancel_job(user, job_id)

    if success:
        await store.update_user(user_id, user)

    yield event.plain_result(msg)
