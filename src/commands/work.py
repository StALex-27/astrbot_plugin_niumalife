"""
打工命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_WORK
from ...modules.jobs import Job
from ...modules.company_favorability import CompanyFavorability
from ...modules.jobs import JobManager


LOCAL_TZ = timezone(timedelta(hours=8))


def get_job_mgr():
    """获取打工管理器单例"""
    from ...src.commands.interactive import get_job_mgr as _get
    return _get()


def get_favor_mgr():
    """获取好感度管理器单例"""
    from ...src.commands.interactive import get_favor_mgr as _get
    return _get()


async def run_work_show_status_logic(user):
    """显示工作状态"""
    detail = user.get("action_detail", {})
    action_type = detail.get("action_type", "")
    
    lines = ["═══════════════════════════", "    「工作中」", "═══════════════════════════"]
    
    if action_type == TICK_TYPE_WORK:
        job_name = detail.get("data", {}).get("job_name", "工作中")
        planned = detail.get("planned_ticks", 0)
        
        now = datetime.now(LOCAL_TZ)
        elapsed_seconds = ActionDetail.get_elapsed_seconds(detail, now)
        elapsed_ticks = int(elapsed_seconds // 60)
        earned = detail.get("earned_gold", 0)
        remaining_hours = max(0, (planned - elapsed_ticks) / 60)
        progress = min(100, int(elapsed_ticks / planned * 100)) if planned > 0 else 0
        
        attrs = user.get("attributes", {})
        
        lines.append(f"\n📋 当前: {job_name}")
        lines.append(f"⏰ 剩余: {remaining_hours:.1f} 小时")
        lines.append(f"💰 已赚: {earned} 金币")
        lines.append(f"\n进度: [{'█' * (progress // 5)}{'░' * (20 - progress // 5)}] {progress}%")
        lines.append(f"\n❤️ {int(attrs.get('health', 0))} 💪 {int(attrs.get('strength', 0))} ⚡ {int(attrs.get('energy', 0))}")
        lines.append(f"😊 {int(attrs.get('mood', 0))} 🍖 {int(attrs.get('satiety', 0))}")
    
    lines.append("\n═══════════════════════════")
    lines.append("⏳ 工作进行中，整点自动结算")
    lines.append("📝 使用 /取消 取消当前工作")
    lines.append("═══════════════════════════")
    return "\n".join(lines)


async def run_work_show_pool_logic(user, jmgr, fmgr):
    """显示委托池"""
    now = datetime.now(LOCAL_TZ)
    
    # 检查池是否过期（3小时）
    pool_age_hours = None
    if "job_pool_created_at" in user:
        try:
            created = datetime.fromisoformat(user["job_pool_created_at"])
            pool_age_hours = (now - created).total_seconds() / 3600
        except (ValueError, TypeError):
            pass
    
    should_refresh = (
        "job_pool" not in user 
        or not user["job_pool"] 
        or (pool_age_hours is not None and pool_age_hours >= 3)
    )
    
    if should_refresh:
        pool = jmgr.generate_job_pool(user, count=6)
        user["job_pool"] = [j.to_dict() for j in pool]
        user["job_pool_created_at"] = now.isoformat()
    
    pool = [Job.from_dict(j) for j in user.get("job_pool", [])]
    favor_data = user.get("company_favorability", {})
    
    recommended = jmgr.pool_generator.get_company_recommended_jobs(user, max_per_company=2)
    
    lines = ["═══════════════════════════", "    「 委 托 池 」", "═══════════════════════════"]
    
    if pool:
        lines.append("\n📋 公共委托")
        for i, job in enumerate(pool, 1):
            company = jmgr.get_company_info(job.company_id)
            emoji = company.get("emoji", "") if company else ""
            diff = job.difficulty
            diff_icon = {"D": "🟢", "C": "🔵", "B": "🟡", "A": "🟠", "S": "🔴", "S+": "💜"}.get(diff, "⚪")
            skill_str = ""
            if job.skill_required:
                skills = ", ".join([f"{s}Lv.{l}" for s, l in job.skill_required.items()])
                skill_str = f"\n   📋 {skills}"
            lines.append(
                f"\n{i}. [{job.job_id}] {diff_icon} {job.title} ({diff})"
                f"\n   {emoji} 预计{job.duration_hours}h | 💰{job.base_reward}"
                f"{skill_str}"
            )
    else:
        lines.append("\n📋 暂无公共委托")
    
    if recommended:
        lines.append("\n─────────── 公司推荐 ───────────")
        for cid, jobs in recommended.items():
            company = jmgr.get_company_info(cid)
            if not company:
                continue
            emoji = company.get("emoji", "")
            name = company.get("name", cid)
            favor = favor_data.get(cid, 0)
            level = fmgr.get_favor_level(favor)
            lines.append(f"\n{emoji} {name} (Lv.{level['level']} {level['name']})")
            for job in jobs[:2]:
                diff = job.get("difficulty", "D")
                diff_icon = {"D": "🟢", "C": "🔵", "B": "🟡", "A": "🟠", "S": "🔴", "S+": "💜"}.get(diff, "⚪")
                job_id = job.get("job_id", "???")
                lines.append(
                    f"  • [{job_id}] {diff_icon}{job.get('title', '未知委托')} ({diff}) "
                    f"{job.get('duration_hours', 1)}h 💰{job.get('base_reward', 0)}"
                )
    
    lines.append("\n═══════════════════════════")
    lines.append("📝 /打工 <委托名/编号> 接受委托")
    lines.append("📝 /打工 公司 查看公司列表")
    lines.append("📝 /打工 公司名 查看公司详情")
    
    return "\n".join(lines)


async def run_work_refresh_pool_logic(user, jmgr):
    """刷新委托池"""
    today = datetime.now(LOCAL_TZ).date()
    last_refresh = user.get("job_pool_refresh_date", "")
    
    if last_refresh == str(today):
        used = user.get("job_pool_refresh_today", 0)
        if used >= 3:
            return "今日刷新次数已用完（3次），明天再来"
        user["job_pool_refresh_today"] = used + 1
    else:
        user["job_pool_refresh_today"] = 1
        user["job_pool_refresh_date"] = str(today)
    
    pool = jmgr.generate_job_pool(user, count=6)
    user["job_pool"] = [j.to_dict() for j in pool]
    user["job_pool_created_at"] = datetime.now(LOCAL_TZ).isoformat()
    
    return (
        f"✅ 委托池已刷新！\n今日剩余刷新次数: {3 - user['job_pool_refresh_today']}"
    )


async def run_work_show_companies_logic(user, fmgr, jmgr):
    """显示公司列表"""
    summary = fmgr.get_all_companies_summary(user)
    
    lines = ["═══════════════════════════", "    「 公 司 一 览 」", "═══════════════════════════"]
    
    for s in summary:
        emoji = s.get("emoji", "")
        name = s.get("name", s["company_id"])
        level_bar = "★" * s["level"] + "☆" * (10 - s["level"])
        lines.append(
            f"\n{emoji} {name}"
            f"\n   ❤️ {s['favorability']} | {level_bar}"
            f"\n   ⭐ Lv.{s['level']} {s['level_name']}"
        )
        
    lines.append("\n═══════════════════════════")
    lines.append("📝 /打工 公司名 查看公司详情和委托")
    
    return "\n".join(lines)


async def run_work_show_company_detail_logic(user, company_id, fmgr, jmgr):
    """显示公司详情"""
    company = jmgr.get_company_info(company_id)
    if not company:
        return f"❌ 未找到公司: {company_id}"
        
    favor = fmgr.get_company_favorability(user, company_id)
    level = fmgr.get_favor_level(favor)
    
    lines = [
        "═══════════════════════════",
        f"    「 {company.get('emoji', '')} {company.get('name', company_id)} 」",
        "═══════════════════════════",
        f"\n🏢 行业: {company.get('industry', '未知')}",
        f"📊 档位: {company.get('difficulty_tier', 'T1')}",
        f"\n❤️ 好感度: {favor}",
        f"⭐ 等级: Lv.{level['level']} {level['name']}",
        f"\n🔓 已解锁:",
    ]
    
    for unlock in level.get("unlock", []):
        lines.append(f"   ✅ {unlock}")
        
    avail_diffs = fmgr.get_available_difficulties(favor)
    diff_str = " ".join([{"D": "🟢D", "C": "🔵C", "B": "🟡B", "A": "🟠A", "S": "🔴S", "S+": "💜S+"}.get(d, d) for d in avail_diffs])
    lines.append(f"\n📋 可接难度: {diff_str}")
    
    jobs = jmgr.get_company_jobs(user, company_id, max_per_company=3)
    if jobs:
        lines.append(f"\n📝 可接委托:")
        for job in jobs:
            diff = job.difficulty
            diff_icon = {"D": "🟢", "C": "🔵", "B": "🟡", "A": "🟠", "S": "🔴", "S+": "💜"}.get(diff, "⚪")
            skill_str = ""
            if job.skill_required:
                skill_str = f" [{', '.join([f'{s}Lv.{l}' for s,l in job.skill_required.items()])}]"
            lines.append(
                f"  • {diff_icon}{job.title} ({diff}){skill_str}\n"
                f"    ⏰{job.duration_hours}h 💰{job.base_reward}"
            )
    else:
        lines.append(f"\n📝 暂无可接委托（好感度不足）")
        
    lines.append("\n═══════════════════════════")
    lines.append("📝 /打工 <委托名> 接受委托")
    
    return "\n".join(lines)


async def run_work_accept_job_logic(user, cmd, args, jmgr, store):
    """接受委托"""
    pool = [Job.from_dict(j) for j in user.get("job_pool", [])]
    
    if not pool:
        return (
            "📋 委托池是空的！\n"
            "先输入 /打工 查看当前委托池\n"
            "委托池每3小时自动刷新，或输入 /打工 列表 手动刷新"
        )
    
    
    job = None
    job_idx = None
    
    # 按编号查找（1-based索引，如 /打工 1）
    try:
        idx = int(cmd) - 1
        if 0 <= idx < len(pool):
            job = pool[idx]
            job_idx = idx
    except ValueError:
        pass

    # 按job_id查找（如 /打工 L231）
    if not job:
        for i, j in enumerate(pool):
            if j.job_id == cmd:
                job = j
                job_idx = i
                break

    # 按名称查找（如 /打工 活动协助）
    if not job:
        for i, j in enumerate(pool):
            if cmd in j.title or cmd in j.description:
                job = j
                job_idx = i
                break
    
    if not job:
        return f"❌ 未找到委托: {cmd}\n可用 /打工 查看委托池"
        
    # 检查进行中委托数量
    in_progress = jmgr.get_player_current_jobs(user)
    if len(in_progress) >= 3:
        return "进行中的委托已达上限（3个），请先完成或取消现有委托"
        
    # 接受委托
    success, msg = jmgr.accept_job(user, job)
    if not success:
        return f"❌ {msg}"
    
    # 创建 action_detail 以启动 tick 系统
    now = datetime.now(LOCAL_TZ)
    detail = ActionDetail.create(
        action_type=TICK_TYPE_WORK,
        hours=job.duration_hours,
        start_time=now,
        job_name=job.title,
        job_company=job.company_id,
        base_reward=job.base_reward,
    )
    user["status"] = UserStatus.WORKING
    user["current_action"] = TICK_TYPE_WORK
    user["action_detail"] = detail
    
    # 从委托池移除
    if job_idx is not None:
        user["job_pool"].pop(job_idx)
    
    # 保存用户数据
    await store.update_user(str(user.get("user_id", "")), user)
    
    company = jmgr.get_company_info(job.company_id)
    company_name = company.get("name", "") if company else ""
    
    return (
        f"✅ 已接受委托！\n\n"
        f"📋 {job.title}\n"
        f"🏢 {company_name}\n"
        f"⏰ 预计完成: {job.duration_hours} 小时\n"
        f"💰 基础奖励: {job.base_reward} 金币\n\n"
        f"输入 /打工 查看当前进度"
    )


async def run_work_logic(event: AstrMessageEvent, store, parser, jmgr, fmgr):
    """打工命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 自动注册")
        return
    
    _, args = parser.parse(event)
    cmd = args[0] if args else None
    
    # 工作状态：显示当前进度
    if user["status"] == UserStatus.WORKING:
        yield event.plain_result(await run_work_show_status_logic(user))
        return
    
    # 空闲状态 - 无参数：显示委托池
    if not cmd:
        result = await run_work_show_pool_logic(user, jmgr, fmgr)
        yield event.plain_result(result)
        
        # 如果池刚刷新（刚创建或过期重建），保存用户数据
        if "job_pool_created_at" in user:
            await store.update_user(user_id, user)
        return
    
    # 子命令处理
    if cmd == "公司":
        yield event.plain_result(await run_work_show_companies_logic(user, fmgr, jmgr))
        return
        
    if cmd in ["列表", "list"]:
        result = await run_work_refresh_pool_logic(user, jmgr)
        await store.update_user(user_id, user)
        yield event.plain_result(result)
        return
        
    # 检查是否是公司名
    company = jmgr.get_company_info(cmd)
    if company:
        yield event.plain_result(await run_work_show_company_detail_logic(user, cmd, fmgr, jmgr))
        return
    
    # 尝试匹配委托（按编号或名称）
    yield event.plain_result(await run_work_accept_job_logic(user, cmd, args, jmgr, store))
