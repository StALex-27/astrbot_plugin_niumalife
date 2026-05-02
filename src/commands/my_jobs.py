"""
我的委托命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...src.commands.interactive import get_job_mgr


LOCAL_TZ = timezone(timedelta(hours=8))


async def run_my_jobs_logic(event: AstrMessageEvent, store):
    """查看进行中的委托"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    jmgr = get_job_mgr()
    in_progress = jmgr.get_player_current_jobs(user)

    if not in_progress:
        yield event.plain_result("当前没有进行中的委托\n输入 /打工 查看可接委托")
        return

    lines = ["═══════════════════════════", "    「 进 行 中 」", "═══════════════════════════"]

    for i, job_entry in enumerate(in_progress, 1):
        accepted = datetime.fromisoformat(job_entry["accepted_at"])
        expected = datetime.fromisoformat(job_entry["expected_complete_at"])
        remaining = (expected - datetime.now(LOCAL_TZ)).total_seconds() / 3600

        total_seconds = (expected - accepted).total_seconds()
        elapsed = (datetime.now(LOCAL_TZ) - accepted).total_seconds()
        progress = min(100, int(elapsed / total_seconds * 100))

        progress_bar = "█" * (progress // 5) + "░" * (20 - progress // 5)

        lines.append(
            f"\n{i}. {job_entry['title']} ({job_entry['difficulty']})"
            f"\n   进度: [{progress_bar}] {progress}%"
            f"\n   预计剩余: {max(0, remaining):.1f} 小时"
        )

    lines.append("\n═══════════════════════════")
    lines.append("输入 /完成委托 <编号> 完成委托")
    lines.append("输入 /取消委托 <编号> 取消委托")

    yield event.plain_result("\n".join(lines))
