"""
完成委托命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...src.commands.interactive import get_job_mgr


async def run_complete_job_logic(event: AstrMessageEvent, store, parser):
    """完成委托并获取评价"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！")
        return

    _, args = parser.parse(event)
    jmgr = get_job_mgr()

    if not args:
        in_progress = jmgr.get_player_current_jobs(user)
        if not in_progress:
            yield event.plain_result("当前没有进行中的委托")
            return
        if len(in_progress) == 1:
            job_id = in_progress[0]["job_id"]
        else:
            yield event.plain_result("请指定要完成的委托编号\n格式: /完成委托 <编号>")
            return
    else:
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

    success, msg, result = jmgr.complete_job(user, job_id)

    if not success:
        yield event.plain_result(f"❌ {msg}")
        return

    await store.update_user(user_id, user)

    eval_result = result.get("evaluation", {})
    rewards = result.get("rewards", {})

    grade = eval_result.get("grade", "B")
    grade_name = {"S": "完美", "A": "优秀", "B": "良好", "C": "合格", "D": "较差", "F": "失败"}.get(grade, grade)

    lines = ["═══════════════════════════", "    「 委 托 完 成 」", "═══════════════════════════"]
    lines.append(f"\n  评价: {grade} ({grade_name})")
    lines.append(f"  综合分: {eval_result.get('score', 0)}")
    lines.append(f"\n  💰 获得金币: {rewards.get('gold', 0)}")

    if rewards.get("exp"):
        exp_str = ", ".join([f"{k}+{v}" for k, v in rewards.get("exp", {}).items()])
        lines.append(f"  📈 获得经验: {exp_str}")

    lines.append(f"  ❤️ 好感度: {rewards.get('favor_change', 0):+d}")

    lines.append("\n─── 六维评价 ───")
    lines.append(f"  效率: {eval_result.get('efficiency', 0)}")
    lines.append(f"  质量: {eval_result.get('quality', 0)}")
    lines.append(f"  压力: {eval_result.get('stress_bonus', 0):+d}")
    lines.append(f"  心情: {eval_result.get('mood_bonus', 0):+d}")
    lines.append(f"  技能: {eval_result.get('skill_bonus', 0):+d}")
    lines.append(f"  Buff: {eval_result.get('buff_bonus', 0):+d}")

    lines.append("\n═══════════════════════════")

    yield event.plain_result("\n".join(lines))
