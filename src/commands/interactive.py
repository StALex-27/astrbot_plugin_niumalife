"""
交互式命令处理器
实现2次交互内完成操作的智能指令系统

核心指令 (12个):
- /档案 - 查看档案
- /打工 [委托名/编号/公司] - 打工系统（空闲显示委托池，工作显示进度）
- /学习 [课程名]     - 学习（机构推荐）
- /娱乐 [名称] [小时] - 娱乐
- /吃 [食物名] - 吃东西
- /签到 - 每日签到 (含自动注册)
- /住 [操作] - 住所管理
- /背包 - 背包
- /商店 [公司/物品] - 商店（集成公司商店）
- /股市 [操作] - 股市
- /取消 - 取消动作
- /帮助 - 帮助
"""

import random
from datetime import datetime, timezone, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from ...modules.constants import JOBS, FOODS, RESIDENCES, ENTERTAINMENTS, MAX_ATTRIBUTE
from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_WORK, TICK_TYPE_LEARN, TICK_TYPE_ENTERTAIN
from ...modules.checkin import get_luck_rating, get_streak_reward, roll_lucky_drop
from ...modules.item import (
    ITEMS, RARITY_COLORS, RARITY_NAMES, SLOTS, SLOT_EMOJI,
    get_equipped_items, equip_item, unequip_item, auto_equip_if_empty,
    calc_equipped_effects, format_item, format_item_effects, get_items_by_slot,
    get_inventory_count, apply_item_effects, get_all_inventory
)
from ...modules.shop import (
    SHOPS, get_all_shops, get_shop_items, get_global_random_items,
    format_shop_list, format_shop_items, buy_item, is_item_in_shop
)
from ...modules.skills import (
    check_course_available, get_user_skill_level, get_skills_meta
)
from ...modules.institutions import (
    INSTITUTIONS, COURSES,
    select_institutions_for_user, get_recommended_courses,
    get_institution, get_courses_by_institution,
    get_all_institutions, search_courses_by_keyword,
    get_courses_by_skill, format_course_line,
    get_skill_progress
)

# 打工系统V2模块
from ...modules.jobs import JobManager, Job
from ...modules.company_favorability import CompanyFavorability
from ...modules.company_shop import CompanyShop
from ...modules.evaluation_v3 import get_evaluator


LOCAL_TZ = timezone(timedelta(hours=8))

# 打工系统V2管理器单例
_job_manager = None
_favor_manager = None
_shop_manager = None

def get_job_mgr():
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager

def get_favor_mgr():
    global _favor_manager
    if _favor_manager is None:
        _favor_manager = CompanyFavorability()
    return _favor_manager

def get_company_shop_mgr():
    global _shop_manager
    if _shop_manager is None:
        _shop_manager = CompanyShop()
    return _shop_manager


def register_interactive_commands(plugin):
    """注册所有交互式命令"""
    
    # ========== 档案 ==========
    @filter.command("档案")
    async def profile(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            try:
                url = await plugin._renderer.render_error("未注册", "你还没有签到过！\\n输入 /签到 自动注册并签到", event)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result("📋 你还没有注册！\\n输入 /签到 自动注册并签到")
            return
        
        try:
            url = await plugin._renderer.render_profile(user, event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(_format_profile_text(user))
    
    # ========== 打工 ==========
    @filter.command("打工")
    async def work(event: AstrMessageEvent):
        """打工系统V2 - 统一的打工指令
        空闲状态: 无参数显示委托池，有参数处理子命令
        工作状态: 显示当前工作进度，提示完成或取消
        """
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 自动注册")
            return
        
        _, args = plugin._parser.parse(event)
        cmd = args[0] if args else None
        
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        
        # 工作状态：显示当前进度
        if user["status"] == UserStatus.WORKING:
            await _show_working_status(event, user, jmgr)
            return
        
        # 空闲状态
        # 无参数：显示委托池
        if not cmd:
            await _show_job_pool(event, user, jmgr, fmgr)
            return
        
        # 子命令处理
        if cmd == "公司":
            await _show_company_list(event, user, fmgr, jmgr)
            return
            
        if cmd in ["列表", "list"]:
            await _refresh_job_pool(event, user, jmgr)
            return
            
        # 检查是否是公司名
        company = jmgr.get_company_info(cmd)
        if company:
            await _show_company_detail(event, user, cmd, fmgr, jmgr)
            return
        
        # 尝试匹配委托（按编号或名称）
        await _accept_job(event, user, cmd, args, jmgr)
        
    async def _show_working_status(event, user, jmgr):
        """显示工作状态"""
        detail = user.get("action_detail", {})
        action_type = detail.get("action_type", "")
        
        lines = ["═══════════════════════════", "    「工作中」", "═══════════════════════════"]
        
        if action_type == TICK_TYPE_WORK:
            job_name = detail.get("data", {}).get("job_name", "工作中")
            planned = detail.get("planned_ticks", 0)
            
            # 实时计算进度
            now = datetime.now(LOCAL_TZ)
            elapsed_seconds = ActionDetail.get_elapsed_seconds(detail, now)
            elapsed_ticks = int(elapsed_seconds // 60)
            earned = detail.get("earned_gold", 0)
            remaining_hours = max(0, (planned - elapsed_ticks) / 60)
            progress = min(100, int(elapsed_ticks / planned * 100)) if planned > 0 else 0
            
            # 实时估算属性（基于上次结算的值）
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
        
        yield event.plain_result("\n".join(lines))
        
    async def _show_job_pool(event, user, jmgr, fmgr):
        """显示委托池"""
        # 获取或生成委托池
        if "job_pool" not in user or not user["job_pool"]:
            pool = jmgr.generate_job_pool(user, count=6)
            user["job_pool"] = [j.to_dict() for j in pool]
        
        pool = [Job.from_dict(j) for j in user.get("job_pool", [])]
        favor_data = user.get("company_favorability", {})
        
        # 按公司分组推荐委托
        recommended = jmgr.pool_generator.get_company_recommended_jobs(user, max_per_company=2)
        
        lines = ["═══════════════════════════", "    「 委 托 池 」", "═══════════════════════════"]
        
        # 公共委托
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
                    f"\n{i}. {diff_icon} {job.title} ({diff})"
                    f"\n   {emoji} 预计{job.duration_hours}h | 💰{job.base_reward}"
                    f"{skill_str}"
                )
        else:
            lines.append("\n📋 暂无公共委托")
        
        # 公司推荐委托
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
                    diff = job.difficulty
                    diff_icon = {"D": "🟢", "C": "🔵", "B": "🟡", "A": "🟠", "S": "🔴", "S+": "💜"}.get(diff, "⚪")
                    lines.append(
                        f"  • {diff_icon}{job.title} ({diff}) "
                        f"{job.duration_hours}h 💰{job.base_reward}"
                    )
        
        lines.append("\n═══════════════════════════")
        lines.append("📝 /打工 <委托名/编号> 接受委托")
        lines.append("📝 /打工 公司 查看公司列表")
        lines.append("📝 /打工 公司名 查看公司详情")
        
        yield event.plain_result("\n".join(lines))
        
    async def _refresh_job_pool(event, user, jmgr):
        """刷新委托池"""
        today = datetime.now(LOCAL_TZ).date()
        last_refresh = user.get("job_pool_refresh_date", "")
        
        if last_refresh == str(today):
            used = user.get("job_pool_refresh_today", 0)
            if used >= 3:
                yield event.plain_result("今日刷新次数已用完（3次），明天再来")
                return
            user["job_pool_refresh_today"] = used + 1
        else:
            user["job_pool_refresh_today"] = 1
            user["job_pool_refresh_date"] = str(today)
        
        pool = jmgr.generate_job_pool(user, count=6)
        user["job_pool"] = [j.to_dict() for j in pool]
        
        yield event.plain_result(
            f"✅ 委托池已刷新！\n今日剩余刷新次数: {3 - user['job_pool_refresh_today']}"
        )
        
    async def _show_company_list(event, user, fmgr, jmgr):
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
        
        yield event.plain_result("\n".join(lines))
        
    async def _show_company_detail(event, user, company_id, fmgr, jmgr):
        """显示公司详情"""
        company = jmgr.get_company_info(company_id)
        if not company:
            yield event.plain_result(f"❌ 未找到公司: {company_id}")
            return
            
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
        
        # 显示推荐委托
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
        
        yield event.plain_result("\n".join(lines))
        
    async def _accept_job(event, user, cmd, args, jmgr):
        """接受委托"""
        pool = [Job.from_dict(j) for j in user.get("job_pool", [])]
        
        job = None
        job_idx = None
        
        # 按编号查找
        try:
            idx = int(cmd) - 1
            if 0 <= idx < len(pool):
                job = pool[idx]
                job_idx = idx
        except ValueError:
            pass
            
        # 按名称查找
        if not job:
            for i, j in enumerate(pool):
                if cmd in j.title or cmd in j.description:
                    job = j
                    job_idx = i
                    break
                    
        if not job:
            yield event.plain_result(f"❌ 未找到委托: {cmd}\n可用 /打工 查看委托池")
            return
            
        # 检查进行中委托数量
        in_progress = jmgr.get_player_current_jobs(user)
        if len(in_progress) >= 3:
            yield event.plain_result("进行中的委托已达上限（3个），请先完成或取消现有委托")
            return
            
        # 接受委托
        success, msg = jmgr.accept_job(user, job)
        if not success:
            yield event.plain_result(f"❌ {msg}")
            return
        
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
        await plugin._store.update_user(user_id, user)
        
        company = jmgr.get_company_info(job.company_id)
        company_name = company.get("name", "") if company else ""
        
        yield event.plain_result(
            f"✅ 已接受委托！\n\n"
            f"📋 {job.title}\n"
            f"🏢 {company_name}\n"
            f"⏰ 预计完成: {job.duration_hours} 小时\n"
            f"💰 基础奖励: {job.base_reward} 金币\n\n"
            f"输入 /打工 查看当前进度"
        )
    
    # ========== 学习 ==========
    @filter.command("学习")
    async def learn(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)

        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return

        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法学习\n先用 /取消 取消当前动作")
            return

        _, args = plugin._parser.parse(event)

        # 无参数：显示机构推荐
        if not args or not args[0]:
            inst_ids = select_institutions_for_user(user, count=4)
            if not inst_ids:
                inst_ids = list(INSTITUTIONS.keys())[:4]
            user_skills = user.get("skills", {})
            lines = ["📚 选择就读机构", "━━━━━━━━━━━━━━"]
            for idx, inst_id in enumerate(inst_ids, 1):
                inst = get_institution(inst_id)
                emoji = inst.get("emoji", "🏫")
                name = inst.get("name", inst_id)
                courses = get_recommended_courses(inst_id, user, limit=4)
                if courses:
                    for c in courses:
                        skill_lv = user_skills.get(c.get("skill", ""), 0)
                        total_cost = c.get("cost", 0) * c.get("hours", 2)
                        tier_emoji = {1: "🔰", 2: "⬆️", 3: "⭐"}.get(c.get("tier", 1), "")
                        prereqs = c.get("prerequisites", {})
                        prereq_str = " [需:" + "/".join([f"{k}Lv{v}" for k, v in prereqs.items()]) + "]" if prereqs else ""
                        lines.append(f"{idx}. {emoji}{name}")
                        lines.append(f"    {tier_emoji}{c.get('name','')} | 💰{total_cost}金 | {c.get('skill')}Lv{skill_lv}{prereq_str}")
                else:
                    lines.append(f"{idx}. {emoji}{name} - 暂无可学习课程")
            lines.extend(["━━━━━━━━━━━━━━", "回复：课程名 开始学习", "例：/学习 编程入门", "或：/学习 查询  查看全部机构"])
            yield event.plain_result("\n".join(lines))
            return

        first_arg = args[0]

        # 查询模式
        if first_arg == "查询" or first_arg.startswith("查询#"):
            query = args[1][1:] if len(args) > 1 and args[1].startswith("#") else (args[1] if len(args) > 1 else "")
            insts = get_all_institutions()
            if not query:
                lines = ["🏫 教育机构一览", "━━━━━━━━━━━━━━"]
                for inst in insts:
                    emoji = inst.get("emoji", "🏫")
                    name = inst.get("name", "")
                    desc = inst.get("desc", "")
                    lines.append(f"{emoji} {name}：{desc}")
                lines.extend(["━━━━━━━━━━━━━━", "回复 /学习 查询#机构名  查看详情", "回复 /学习 查询#技能名  查看技能路径"])
                yield event.plain_result("\n".join(lines))
                return

            # 机构详情查询
            matched_inst = None
            for inst_id, inst in INSTITUTIONS.items():
                if query in inst_id or query in inst.get("name", ""):
                    matched_inst = inst_id
                    break

            if matched_inst:
                inst = get_institution(matched_inst)
                emoji = inst.get("emoji", "🏫")
                name = inst.get("name", matched_inst)
                desc = inst.get("desc", "")
                user_skills = user.get("skills", {})
                all_courses = get_courses_by_institution(matched_inst)
                lines = [f"{emoji} {name}", f"  {desc}", "━━━━━━━━━━━━━━"]
                for tier in [1, 2, 3]:
                    tier_courses = [c for c in all_courses if c.get("tier") == tier]
                    if not tier_courses:
                        continue
                    lines.append({1: "🔰 T1 基础", 2: "⬆️ T2 专业", 3: "⭐ T3 大师"}[tier])
                    for c in tier_courses:
                        skill_lv = user_skills.get(c.get("skill", ""), 0)
                        total_cost = c.get("cost", 0) * c.get("hours", 2)
                        prereqs = c.get("prerequisites", {})
                        prereq_str = " [需:" + "/".join([f"{k}Lv{v}" for k, v in prereqs.items()]) + "]" if prereqs else ""
                        lines.append(f"✅ {c.get('name','')} | 💰{total_cost}金 | {c.get('skill')}Lv{skill_lv}{prereq_str}")
                lines.extend(["━━━━━━━━━━━━━━", "回复课程名开始学习"])
                yield event.plain_result("\n".join(lines))
                return

            # 技能路径查询
            skills_meta = get_skills_meta()
            matched_skill = None
            for skill_name in skills_meta:
                if query in skill_name:
                    matched_skill = skill_name
                    break

            if matched_skill:
                courses = get_courses_by_skill(matched_skill, user)
                progress = get_skill_progress(user, matched_skill)
                lines = [f"📖 {matched_skill} 技能路径", f"  当前等级：Lv{progress['level']}", "━━━━━━━━━━━━━━"]
                current_tier = None
                for c in courses:
                    tier = c.get("tier", 1)
                    if tier != current_tier:
                        lines.append({1: "🔰 T1 基础", 2: "⬆️ T2 专业", 3: "⭐ T3 大师"}[tier])
                        current_tier = tier
                    ava = "✅" if c.get("available", False) else "🔒"
                    total_cost = c.get("cost", 0) * c.get("hours", 2)
                    prereqs = c.get("prerequisites", {})
                    prereq_str = " [需:" + "/".join([f"{k}Lv{v}" for k, v in prereqs.items()]) + "]" if prereqs else ""
                    lines.append(f"{ava} {c.get('institution','')}·{c.get('name','')} | 💰{total_cost}金{prereq_str}")
                lines.extend(["━━━━━━━━━━━━━━", "回复课程名开始学习"])
                yield event.plain_result("\n".join(lines))
                return

            # 关键词搜索
            results = search_courses_by_keyword(query, user)
            if not results:
                yield event.plain_result(f"📋 未找到与「{query}」相关的课程或机构")
                return
            lines = [f"🔍 「{query}」搜索结果（共{len(results)}门）", "━━━━━━━━━━━━━━"]
            for c in results[:15]:
                ava = "✅" if c.get("available", False) else "🔒"
                lines.append(f"{ava} {c.get('institution','')}·{c.get('name','')} | {c.get('skill','')} | 💰{c.get('cost',0)*c.get('hours',2)}金")
            if len(results) > 15:
                lines.append(f"...还有{len(results)-15}门")
            lines.extend(["━━━━━━━━━━━━━━", "回复课程名开始学习"])
            yield event.plain_result("\n".join(lines))
            return

        # 直接选择课程
        course_identifier = first_arg
        if course_identifier in COURSES:
            course_id = course_identifier
            course = COURSES[course_id]
        else:
            matches = [(cid, c) for cid, c in COURSES.items() if course_identifier in cid or course_identifier in c.get("name", "")]
            if not matches:
                yield event.plain_result(f"📋 未找到课程：{course_identifier}\n可输入 /学习 查询#技能名 查看课程")
                return
            if len(matches) == 1:
                course_id, course = matches[0]
            else:
                lines = [f"📋 找到多个匹配课程：", "━━━━━━━━━━━━━━"]
                for idx, (cid, c) in enumerate(matches[:10], 1):
                    ok, _ = check_course_available(cid, c, user)
                    ava = "✅" if ok else "🔒"
                    total_cost = c.get("cost", 0) * c.get("hours", 2)
                    lines.append(f"{idx}. {ava} {c.get('institution','')}·{c.get('name','')} | 💰{total_cost}金")
                lines.extend(["━━━━━━━━━━━━━━", "请输入完整课程名（带机构前缀）"])
                yield event.plain_result("\n".join(lines))
                return

        ok, reason = check_course_available(course_id, course, user)
        if not ok:
            yield event.plain_result(f"📋 {reason}")
            return

        hours = course.get("hours", 2)
        total_cost = course.get("cost", 0) * hours
        attrs = user["attributes"]
        if attrs.get("gold", 0) < total_cost:
            yield event.plain_result(f"📋 金币不足！需要 {total_cost} 金币，现有 {attrs.get('gold', 0):.0f} 金币")
            return
        if attrs["strength"] < course.get("consume_strength", 3) * hours * 0.5:
            yield event.plain_result("📋 体力不足，无法学习")
            return
        if attrs["energy"] < course.get("consume_energy", 8) * hours * 0.5:
            yield event.plain_result("📋 精力不足，无法学习")
            return

        attrs["gold"] = attrs.get("gold", 0) - total_cost
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TICK_TYPE_LEARN,
            hours=hours,
            start_time=now,
            course_name=course_id,
            exp_per_hour=course.get("exp_per_hour", 10),
            consume_strength=course.get("consume_strength", 3),
            consume_energy=course.get("consume_energy", 8),
            consume_mood=course.get("consume_mood", 5),
            cost=course.get("cost", 0)
        )
        user["status"] = UserStatus.LEARNING
        user["current_action"] = TICK_TYPE_LEARN
        user["action_detail"] = detail
        await plugin._store.update_user(user_id, user)

        course_name_display = f"{course.get('institution','')}·{course.get('name','')}"
        try:
            url = await plugin._renderer.render_entertain_start(
                user, event,
                ent_name=course_name_display,
                ent_emoji="📚",
                hours=hours,
                gain_mood=course.get('exp_per_hour', 10) * hours,
                consume_satiety=int(course.get('consume_strength', 3) * hours)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(
                f"✅ 开始学习：\n━━━━━━━━━━━━━━\n"
                f"📚 {course_name_display}\n"
                f"⏱️ 时长：{hours}小时\n"
                f"💰 学费：{total_cost}金币（已扣除）\n"
                f"📈 预计经验：{course.get('exp_per_hour', 10) * hours}\n"
                f"━━━━━━━━━━━━━━\n🎉 学习愉快！"
            )

    # ========== 娱乐 ==========
    @filter.command("娱乐")
    async def entertain(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法娱乐")
            return
        
        _, args = plugin._parser.parse(event)
        
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
        
        user["status"] = UserStatus.ENTERTAINING
        user["current_action"] = TICK_TYPE_ENTERTAIN
        user["action_detail"] = detail
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_entertain_start(
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
    
    # ========== 吃 ==========
    @filter.command("吃")
    async def eat(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
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
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_eat(
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
    
    # ========== 签到 (含自动注册) ==========
    @filter.command("签到")
    async def checkin(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        # 自动注册
        is_new_user = False
        if not user:
            nickname = event.get_sender_name()
            user = await plugin._store.create_user(user_id, nickname)
            is_new_user = True
        
        now = datetime.now(LOCAL_TZ)
        today_str = now.strftime("%Y-%m-%d")
        checkin_data = user.get("checkin", {})
        last_date = checkin_data.get("last_date")
        
        # 今日已签到
        if last_date == today_str:
            try:
                result = {"luck_value": checkin_data.get("last_luck", 50), "total_gold": 0, "drop_info": None}
                url = await plugin._renderer.render_checkin(user, event, result, already_checked=True)
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
                from modules.buff import create_buff
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
        await plugin._store.update_user(user_id, user)
        
        try:
            result = {
                "luck_value": luck_value,
                "total_gold": total_gold,
                "streak_bonus": streak_bonus,
                "drop_info": drop_info,
                "is_new_user": is_new_user,
            }
            url = await plugin._renderer.render_checkin(user, event, result, already_checked=False)
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
    
    # ========== 住 ==========
    @filter.command("住")
    async def residence_cmd(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
        residence_name = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence_name, RESIDENCES["桥下"])
        
        if not args:
            try:
                url = await plugin._renderer.render_residence(user, event, res_info)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result(
                    f"🏠 当前住所: {residence_name}\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"💪 体力恢复: +{res_info.get('strength_recovery', 2)}/时\\n"
                    f"⚡ 精力恢复: +{res_info.get('energy_recovery', 2)}/时\\n"
                    f"😴 睡眠加成: x{res_info.get('sleep_bonus', 1.0)}\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"回复: /住 租/买 名称\\n"
                    f"例如: /住 租 公寓"
                )
            return
        
        action = args[0]
        target_name = args[1] if len(args) > 1 else None
        
        if action in ["租", "租房"] and target_name:
            target = RESIDENCES.get(target_name)
            if not target or target.get("type") == "永久":
                yield event.plain_result(f"📋 不存在该房产或不可租：{target_name}")
                return
            
            daily_rent = target.get("rent", 0)
            if user["gold"] < daily_rent:
                yield event.plain_result(f"📋 金币不足！租金 {daily_rent} 金币/天，你只有 {user['gold']} 金币")
                return
            
            user["residence"] = target_name
            user["gold"] -= daily_rent
            await plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 租房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{daily_rent}金币 (日租)\\n━━━━━━━━━━━━━━\\n🎉 欢迎入住！")
        
        elif action in ["买", "买房"] and target_name:
            target = RESIDENCES.get(target_name)
            if not target or target.get("type") == "租":
                yield event.plain_result(f"📋 不存在该房产或不可买：{target_name}")
                return
            
            price = target.get("price", 0)
            if user["gold"] < price:
                yield event.plain_result(f"📋 金币不足！售价 {price} 金币，你只有 {user['gold']} 金币")
                return
            
            user["residence"] = target_name
            user["gold"] -= price
            await plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 购房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{price}金币\\n━━━━━━━━━━━━━━\\n🎉 恭喜拥有房产！")
        
        else:
            lines = ["🏠 住所操作:", "━━━━━━━━━━━━━━", "• /住 - 查看当前住所", "• /住 租 名称 - 租房", "• /住 买 名称 - 买房", "━━━━━━━━━━━━━━", "可用房产:"]
            for k, v in list(RESIDENCES.items())[:5]:
                t = v.get('type', '')
                p = v.get('rent', v.get('price', 0))
                lines.append(f"• {k} ({t}-{p}金)")
            yield event.plain_result("\n".join(lines))
    
    # ========== 装备 ==========
    @filter.command("装备")
    async def equip_cmd(event: AstrMessageEvent):
        """装备管理命令"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        inventory = user.get("inventory", [])
        
        # 无参数：显示装备状态
        if not args:
            equipped = get_equipped_items(user)
            effects = calc_equipped_effects(user)
            
            lines = ["━━━━━━━━━━━━━━", "【 装 备 】", "━━━━━━━━━━━━━━"]
            
            # 显示各栏位装备
            for slot, emoji in SLOT_EMOJI.items():
                slot_name = SLOTS.get(slot, slot)
                item = equipped.get(slot)
                if item:
                    lines.append(f"{emoji}{slot_name}: {item.get('name', '未知')}")
                else:
                    lines.append(f"{emoji}{slot_name}: 空")
            
            lines.append("━━━━━━━━━━━━━━")
            lines.append("【 套装效果 】")
            if effects:
                effect_text = format_item_effects(effects)
                lines.append(effect_text if effect_text else "无")
            else:
                lines.append("无")
            
            lines.append("━━━━━━━━━━━━━━")
            
            # 显示背包物品
            if inventory:
                lines.append("【 背包物品 】")
                for i, item in enumerate(inventory, 1):
                    item_id = item.get("id", "")
                    item_info = ITEMS.get(item_id, {})
                    rarity = item_info.get("rarity", "common")
                    emoji = RARITY_COLORS.get(rarity, "⚪")
                    slot = item_info.get("slot", "")
                    slot_name = SLOTS.get(slot, slot)
                    lines.append(f"{i}. {emoji}{item.get('name', item_id)} [{slot_name}]")
            else:
                lines.append("【 背包物品 】空")
            
            lines.append("━━━━━━━━━━━━━━")
            lines.append("【 指令说明 】")
            lines.append("/装备 背包序号 - 穿戴装备")
            lines.append("/装备 卸下 栏位 - 卸下装备")
            lines.append("例: /装备 1 或 /装备 卸下 服装")
            
            yield event.plain_result("\n".join(lines))
            return
        
        # 卸下装备
        if args[0] == "卸下" or args[0] == "unequip":
            if len(args) < 2:
                yield event.plain_result("📋 格式: /装备 卸下 栏位\n例: /装备 卸下 服装")
                return
            
            slot = args[1]
            # 映射中文栏位名到英文
            slot_map = {
                "服装": "clothing", "头部": "head", "工具": "tool",
                "饰品": "accessory", "手机": "phone"
            }
            slot = slot_map.get(slot, slot)
            
            if slot not in SLOTS:
                yield event.plain_result(f"📋 无效栏位，可选: 服装/头部/工具/饰品/手机")
                return
            
            success, msg = unequip_item(user, slot)
            if success:
                await plugin._store.update_user(user_id, user)
                yield event.plain_result(f"✅ {msg}")
            else:
                yield event.plain_result(f"⚠️ {msg}")
            return
        
        # 穿戴装备（通过序号或名称）
        # 尝试解析序号
        try:
            idx = int(args[0]) - 1
            if idx < 0 or idx >= len(inventory):
                yield event.plain_result(f"📋 背包序号无效，有效范围 1-{len(inventory)}")
                return
            item_id = inventory[idx].get("id")
        except ValueError:
            # 尝试通过名称匹配
            item_name = args[0]
            item_id = None
            for inv_item in inventory:
                inv_id = inv_item.get("id", "")
                item_info = ITEMS.get(inv_id, {})
                if item_info.get("name") == item_name or inv_id == item_name:
                    item_id = inv_id
                    break
            if not item_id:
                yield event.plain_result(f"📋 背包中没有该物品: {item_name}")
                return
        
        success, msg, item_info = equip_item(user, item_id)
        if success:
            await plugin._store.update_user(user_id, user)
            # 显示装备信息和效果
            effects = item_info.get("effects", {})
            effect_text = format_item_effects(effects) if effects else "无"
            yield event.plain_result(
                f"✅ {msg}\n\n效果: {effect_text}"
            )
        else:
            yield event.plain_result(f"⚠️ {msg}")
    
    # ========== 背包 ==========
    @filter.command("背包")
    async def backpack(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        inventory = user.get("inventory", [])
        
        if not inventory:
            yield event.plain_result(f"🎒 背包是空的！\\n\\n通过签到或购买获取物品")
            return
        
        lines = ["━━━━━━━━━━━━━━", "【 背包 】", "━━━━━━━━━━━━━━"]
        for i, item in enumerate(inventory, 1):
            name = item.get('name', item.get('id', '未知'))
            qty = item.get('quantity', 1)
            if qty > 1:
                name = f"{name} x{qty}"
            lines.append(f"{i}. {name}")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("使用: /背包 使用 物品名")
        lines.append("      /装备 装备名 穿戴装备")
        
        yield event.plain_result("\n".join(lines))
    
    # ========== 商店辅助函数 ==========
    async def _show_all_shops(event, user):
        """显示所有商店列表"""
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        
        lines = ["═══════════════════════════", "    「 商 店 首 页 」", "═══════════════════════════"]
        
        # 基础商店
        lines.append("\n🏪 基础商店")
        lines.append("  /商店 买 <物品名> 购买")
        for shop_id in ["小吃街", "药品店", "超市", "工具店"]:
            shop = SHOPS.get(shop_id, {})
            lines.append(f"  {shop.get('emoji', '🏪')} /商店 {shop_id}")
        
        # 公司商店
        lines.append("\n🏢 公司商店")
        summary = fmgr.get_all_companies_summary(user)
        for s in summary:
            emoji = s.get("emoji", "")
            name = s.get("name", s["company_id"])
            level = s["level"]
            lines.append(f"  {emoji} /商店 {s['company_id']} (Lv.{level})")
        
        lines.append("\n═══════════════════════════")
        lines.append("💰 金币: {}".format(int(user.get('gold', 0))))
        lines.append("═══════════════════════════")
        
        yield event.plain_result("\n".join(lines))
        
    async def _show_company_shops_list(event, user):
        """显示公司商店列表"""
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        
        summary = fmgr.get_all_companies_summary(user)
        
        lines = ["═══════════════════════════", "    「 公 司 商 店 」", "═══════════════════════════"]
        
        for s in summary:
            emoji = s.get("emoji", "")
            name = s.get("name", s["company_id"])
            level_bar = "★" * min(s["level"], 10) + "☆" * max(0, 10 - s["level"])
            lines.append(
                f"\n{emoji} {name}"
                f"\n   ❤️ {s['favorability']} | {level_bar}"
                f"\n   ⭐ Lv.{s['level']} {s['level_name']}"
                f"\n   📍 /商店 {s['company_id']}"
            )
            
        lines.append("\n═══════════════════════════")
        
        yield event.plain_result("\n".join(lines))
        
    async def _show_company_shop(event, user, company_id, jmgr):
        """显示特定公司商店"""
        company = jmgr.get_company_info(company_id)
        if not company:
            yield event.plain_result(f"❌ 未找到公司: {company_id}")
            return
            
        fmgr = get_favor_mgr()
        favor = fmgr.get_company_favorability(user, company_id)
        level = fmgr.get_favor_level(favor)
        
        cshop = get_company_shop_mgr()
        items = cshop.get_company_shop_items(company_id, favor)
        
        lines = [
            "═══════════════════════════",
            f"    「 {company.get('emoji', '')} {company.get('name', company_id)} 商店 」",
            "═══════════════════════════",
            f"❤️ 好感度: {favor} (Lv.{level['level']} {level['name']})",
        ]
        
        if not items:
            lines.append("\n📦 暂无可购买商品")
            lines.append(f"\n❤️ 提升好感度到 Lv.{level['level']+1} 解锁更多商品")
        else:
            lines.append(f"\n📦 商品列表:")
            for item in items:
                price = item.get("price", 0)
                price_str = f"§e{price}金§r"
                item_type = item.get("type", "物品")
                rarity = item.get("rarity", "普通")
                rarity_emoji = {"普通": "⚪", "稀有": "🔵", "史诗": "🟣", "传说": "🟡"}.get(rarity, "⚪")
                lines.append(
                    f"\n  {rarity_emoji} {item.get('name', '???')}"
                    f"\n    💰 {price_str} | {item_type}"
                )
                
        lines.append("\n═══════════════════════════")
        lines.append("购买: /商店 买 <物品名> 或 /商店 买 <公司> <物品名>")
        
        yield event.plain_result("\n".join(lines))
    
    # ========== 商店 ==========
    @filter.command("商店")
    async def shop_cmd(event: AstrMessageEvent):
        """商店命令 - 集成基础商店和公司商店"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return
            
        _, args = plugin._parser.parse(event)
        
        # 无参数：显示商店列表（包含公司商店入口）
        if not args:
            await _show_all_shops(event, user)
            return
            
        sub_cmd = args[0]
        
        # 检查是否是公司商店
        jmgr = get_job_mgr()
        company = jmgr.get_company_info(sub_cmd)
        if company:
            await _show_company_shop(event, user, sub_cmd, jmgr)
            return
        
        # 检查是否是公司商店子命令
        if sub_cmd in ["公司", "company"]:
            await _show_company_shops_list(event, user)
            return
        
        # 处理子命令: 公司 列表
        if sub_cmd == "列表" and len(args) > 1 and args[1] in ["公司", "company"]:
            await _show_company_shops_list(event, user)
            return
        
        # 基础商店处理
        # 查看特定商店
        if sub_cmd in SHOPS:
            shop_id = sub_cmd
            shop = SHOPS.get(shop_id)
            fixed, random_items = get_shop_items(plugin, shop_id)
            
            lines = ["═══════════════════════════", f"{shop.get('emoji', '🏪')} 【 {shop.get('name', shop_id)} 】", f"{shop.get('desc', '')}", "═══════════════════════════"]
            
            if fixed:
                lines.append("【 常驻商品 】")
                for item_id in fixed:
                    item = ITEMS.get(item_id, {})
                    price = item.get('price', 0)
                    effects = item.get('effects', {})
                    effect_str = format_food_effects(effects)
                    lines.append(f"• {item.get('name', item_id)} §e{price}金§r {effect_str}")
            
            if random_items:
                lines.append("【 限时商品 】")
                for item_id in random_items:
                    item = ITEMS.get(item_id, {})
                    price = item.get('price', 0)
                    effects = item.get('effects', {})
                    effect_str = format_food_effects(effects)
                    lines.append(f"★ {item.get('name', item_id)} §e{price}金§r {effect_str}")
            
            lines.append("═══════════════════════════")
            lines.append("购买: /商店 买 <物品名> [数量]")
            
            yield event.plain_result("\n".join(lines))
            return
        
        # 购买指令
        if sub_cmd == "买":
            if len(args) < 2:
                yield event.plain_result("📋 格式: /商店 买 <物品名> [数量]\n例: /商店 买 泡面 3")
                return
            
            item_name = args[1]
            quantity = int(args[2]) if len(args) > 2 else 1
            
            # 查找物品
            item_id = None
            for iid, item in ITEMS.items():
                if item.get('name') == item_name or iid == item_name:
                    item_id = iid
                    break
            
            if not item_id:
                yield event.plain_result(f"❌ 找不到物品: {item_name}")
                return
            
            price = ITEMS[item_id].get('price', 0) * quantity
            if user.get('gold', 0) < price:
                yield event.plain_result(f"❌ 金币不足！需要 {price} 金币，你只有 {int(user.get('gold', 0))} 金币")
                return
            
            success, msg = buy_item(user, item_id, quantity)
            if success:
                user['gold'] -= price
                await plugin._store.update_user(user_id, user)
                yield event.plain_result(msg)
            else:
                yield event.plain_result(f"❌ {msg}")
            return
        
        # 未知命令，显示商店首页
        await _show_all_shops(event, user)
    
    # ========== 股市 ==========
    @filter.command("股市")
    async def stock_cmd(event: AstrMessageEvent):
        from modules.stock import STOCKS, STOCK_CODE_TO_NAME, is_trading_hour
        from datetime import datetime, timezone, timedelta
        LOCAL_TZ = timezone(timedelta(hours=8))
        
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
        if not args:
            now = datetime.now(LOCAL_TZ)
            trading = is_trading_hour(now.hour)
            status = "📈 交易中" if trading else "⏸️ 休盘中"
            
            lines = ["═══════════════════════════", f"【 股市行情 】{status}", "═══════════════════════════"]
            lines.append(f"{'代码':<8} {'名称':<8} {'价格':>8}  {'涨跌幅':>8}")
            lines.append("-" * 42)
            
            stocks_data = []
            for name, info in STOCKS.items():
                code = info["code"]
                price_key = f"stock_price:{name}"
                open_key = f"stock_open:{name}"
                current_price = await plugin.get_kv_data(price_key, info["base_price"])
                open_price = await plugin.get_kv_data(open_key, info["base_price"])
                
                change = (current_price - open_price) / open_price * 100 if open_price > 0 else 0
                if change > 0:
                    change_str = f"🔺+{change:.2f}%"
                elif change < 0:
                    change_str = f"🔻{change:.2f}%"
                else:
                    change_str = f"➖ 0.00%"
                
                stocks_data.append((abs(change), name, code, current_price, change_str))
            
            stocks_data.sort(key=lambda x: x[0], reverse=True)
            
            for _, name, code, price, change_str in stocks_data:
                lines.append(f"{code:<8} {name:<8} ¥{price:>7.2f}  {change_str}")
            
            lines.append("═══════════════════════════")
            lines.append("操作: /股市 买/卖 代码 数量")
            yield event.plain_result("\n".join(lines))
            return
        
        action = args[0]
        code = args[1].upper() if len(args) > 1 else None
        amount = int(args[2]) if len(args) > 2 else 1
        
        if action == "买" and code:
            from modules.stock import trade_stock
            stock_name = STOCK_CODE_TO_NAME.get(code)
            if not stock_name:
                yield event.plain_result(f"📋 无效股票代码: {code}\n使用 /股市 查看代码")
                return
            price_key = f"stock_price:{stock_name}"
            current_price = await plugin.get_kv_data(price_key, STOCKS[stock_name]["base_price"])
            success, msg = trade_stock(user, stock_name, code, amount, current_price, "buy")
            if success:
                await plugin._store.update_user(user_id, user)
            yield event.plain_result(msg)
        elif action == "卖" and code:
            from modules.stock import trade_stock
            stock_name = STOCK_CODE_TO_NAME.get(code)
            if not stock_name:
                yield event.plain_result(f"📋 无效股票代码: {code}\n使用 /股市 查看代码")
                return
            price_key = f"stock_price:{stock_name}"
            current_price = await plugin.get_kv_data(price_key, STOCKS[stock_name]["base_price"])
            success, msg = trade_stock(user, stock_name, code, amount, current_price, "sell")
            if success:
                await plugin._store.update_user(user_id, user)
            yield event.plain_result(msg)
        elif action == "持股":
            from modules.stock import STOCKS
            holdings = user.get("stock_holdings", {})
            if not holdings:
                yield event.plain_result("📋 你目前没有持股")
            else:
                lines = ["═══════════════════════════", "【 我的持股 】", "═══════════════════════════"]
                total_profit = 0
                for name, info in holdings.items():
                    code = STOCKS[name]["code"]
                    price_key = f"stock_price:{name}"
                    open_key = f"stock_open:{name}"
                    current_price = await plugin.get_kv_data(price_key, STOCKS[name]["base_price"])
                    open_price = await plugin.get_kv_data(open_key, STOCKS[name]["base_price"])
                    cost = info["avg_price"] * info["amount"]
                    value = current_price * info["amount"]
                    profit = value - cost
                    profit_pct = profit / cost * 100 if cost > 0 else 0
                    change = (current_price - open_price) / open_price * 100 if open_price > 0 else 0
                    profit_str = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
                    change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
                    total_profit += profit
                    lines.append(f"{code} {name}: {info['amount']}股")
                    lines.append(f"  成本¥{info['avg_price']:.2f} | 现价¥{current_price:.2f} | 今日{change_str}")
                    lines.append(f"  盈亏: {profit_str}({profit_pct:+.1f}%)")
                lines.append("═══════════════════════════")
                total_str = f"+{total_profit:.0f}" if total_profit >= 0 else f"{total_profit:.0f}"
                lines.append(f"📊 总盈亏: {total_str}金币")
                yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result("📈 股市操作:\n═══════════════════════════\n• /股市 - 查看行情\n• /股市 买 代码 数量\n• /股市 卖 代码 数量\n• /股市 持股\n═══════════════════════════")


    # ========== 我的委托 ==========
    @filter.command("我的委托")
    async def my_jobs(event: AstrMessageEvent):
        """查看进行中的委托"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)

        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return

        jmgr = get_job_manager()
        in_progress = jmgr.get_player_current_jobs(user)

        if not in_progress:
            yield event.plain_result("当前没有进行中的委托\n输入 /打工 查看可接委托")
            return

        lines = ["═══════════════════════════", "    「 进 行 中 」", "═══════════════════════════"]

        for i, job_entry in enumerate(in_progress, 1):
            accepted = datetime.fromisoformat(job_entry["accepted_at"])
            expected = datetime.fromisoformat(job_entry["expected_complete_at"])
            remaining = (expected - datetime.now(LOCAL_TZ)).total_seconds() / 3600

            # 进度百分比
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

    # ========== 完成委托 ==========
    @filter.command("完成委托")
    async def complete_job_cmd(event: AstrMessageEvent):
        """完成委托并获取评价"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)

        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return

        _, args = plugin._parser.parse(event)
        jmgr = get_job_manager()

        if not args:
            # 显示完成确认
            in_progress = jmgr.get_player_current_jobs(user)
            if not in_progress:
                yield event.plain_result("当前没有进行中的委托")
                return
            if len(in_progress) == 1:
                # 只有一个委托，直接完成
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

        # 完成委托
        success, msg, result = jmgr.complete_job(user, job_id)

        if not success:
            yield event.plain_result(f"❌ {msg}")
            return

        # 保存更新
        await plugin._store.update_user(user_id, user)

        # 生成评价报告
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

    # ========== 取消委托 ==========
    @filter.command("取消委托")
    async def cancel_job_cmd(event: AstrMessageEvent):
        """取消委托"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)

        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return

        _, args = plugin._parser.parse(event)
        jmgr = get_job_manager()

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
            await plugin._store.update_user(user_id, user)

        yield event.plain_result(msg)

    # ========== 取消 ==========
    @filter.command("取消")
    async def cancel(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
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
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success(f"✅ 已取消 {old_status}，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(f"✅ 已取消 {old_status}，返回空闲状态")
    
    # ========== 帮助 ==========
    @filter.command("帮助")
    async def help_cmd(event: AstrMessageEvent):
        try:
            url = await plugin._renderer.render_help(event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("""
━━━━━━━━━━━━━━
【 牛马人生 - 指令帮助 】
━━━━━━━━━━━━━━

📌 基础
/签到 - 每日签到 (自动注册)
/档案 - 查看档案
/帮助 - 显示帮助

💼 工作
/打工 [工作名] [小时] - 开始工作
例如: /打工 外卖 4

📚 学习
/学习              - 显示推荐机构
/学习 查询      - 查看所有机构
/学习 查询#名称 - 查询机构/技能
/学习 课程名   - 开始学习
例如: /学习 编程 4

🎮 娱乐
/娱乐 [名称] [小时] - 开始娱乐
例如: /娱乐 游戏 2

🍖 生活
/吃 [食物名] - 吃东西
例: /吃 泡面

🏠 住所
/住 - 查看当前住所
/住 租/买 名称 - 租房/买房

📦 其他
/背包 - 查看背包
/股市 - 股市行情
/取消 - 取消当前动作

💡 提示: 0点-8点空闲时自动睡眠
━━━━━━━━━━━━━━
""")

    # ========== 设置 ==========
    @filter.command("设置")
    async def settings_cmd(event: AstrMessageEvent):
        """用户设置指令"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
            return
        
        # 提取群组ID（如果有）
        actual_group_id = event.get_group_id() if not event.is_private_chat() else ""
        
        # 更新用户所在群组
        if actual_group_id and actual_group_id not in user.get("groups", []):
            user.setdefault("groups", []).append(actual_group_id)
            await plugin._store.update_user(user_id, user)
        
        _, args = plugin._parser.parse(event)
        
        settings = user.setdefault("settings", {
            "sub_group_daily": False,
            "sub_personal_daily": False,
            "daily_report_hour": 23,
            "daily_report_minute": 0,
            "notification_enabled": True,
        })
        
        if not args:
            # 显示当前设置
            sub_group = "✅ 已开启" if settings.get("sub_group_daily") else "❌ 未开启"
            sub_personal = "✅ 已开启" if settings.get("sub_personal_daily") else "❌ 未开启"
            hour = settings.get("daily_report_hour", 23)
            minute = settings.get("daily_report_minute", 0)
            notif = "📳 开启" if settings.get("notification_enabled") else "🔕 关闭"
            
            lines = [
                "━━━━━━━━━━━━━━",
                "【 ⚙️ 个人设置 】",
                "━━━━━━━━━━━━━━",
                f"📰 群日报订阅: {sub_group}",
                f"📋 个人日报订阅: {sub_personal}",
                f"⏰ 日报时间: {hour:02d}:{minute:02d}",
                f"🔔 通知: {notif}",
                "━━━━━━━━━━━━━━",
                "━━━━━━━━━━━━━━",
                "📖 指令说明:",
                "/设置 订阅群日报 - 开启本群日报",
                "/设置 取消订阅群日报",
                "/设置 订阅个人日报 - 开启个人日报",
                "/设置 取消订阅个人日报",
                "/设置 日报时间 HH:MM - 自定义时间",
                "/设置 通知开/关",
                "━━━━━━━━━━━━━━",
            ]
            
            # 如果在群中，显示群设置
            if actual_group_id:
                group_config = await plugin._get_group_config(actual_group_id)
                group_enabled = "✅ 已开启" if group_config.get("enabled") else "❌ 未开启"
                lines.append(f"📢 本群日报: {group_enabled}")
                lines.append("/设置 开启本群日报 - 群管理操作")
            
            yield event.plain_result("\n".join(lines))
            return
        
        action = args[0]
        
        if action == "订阅群日报":
            if not actual_group_id:
                yield event.plain_result("📋 请在群聊中使用此指令！")
                return
            settings["sub_group_daily"] = True
            # 加入群订阅列表
            group_config = await plugin._get_group_config(actual_group_id)
            if actual_group_id not in group_config.get("subscribers", []):
                group_config.setdefault("subscribers", []).append(user_id)
            await plugin._save_group_config(actual_group_id, group_config)
            await plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 已订阅本群日报！\n📅 每日 {settings.get('daily_report_hour',23):02d}:{settings.get('daily_report_minute',0):02d} 接收")
        
        elif action == "取消订阅群日报":
            settings["sub_group_daily"] = False
            if actual_group_id:
                group_config = await plugin._get_group_config(actual_group_id)
                if user_id in group_config.get("subscribers", []):
                    group_config["subscribers"].remove(user_id)
                await plugin._save_group_config(actual_group_id, group_config)
            await plugin._store.update_user(user_id, user)
            yield event.plain_result("❌ 已取消订阅本群日报")
        
        elif action == "订阅个人日报":
            settings["sub_personal_daily"] = True
            await plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 已开启个人日报！\n📅 每日 {settings.get('daily_report_hour',23):02d}:{settings.get('daily_report_minute',0):02d} 私聊推送")
        
        elif action == "取消订阅个人日报":
            settings["sub_personal_daily"] = False
            await plugin._store.update_user(user_id, user)
            yield event.plain_result("❌ 已取消个人日报")
        
        elif action == "日报时间" and len(args) >= 2:
            try:
                time_parts = args[1].split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError()
                settings["daily_report_hour"] = hour
                settings["daily_report_minute"] = minute
                await plugin._store.update_user(user_id, user)
                yield event.plain_result(f"✅ 日报时间已调整为 {hour:02d}:{minute:02d}")
            except (ValueError, IndexError):
                yield event.plain_result("📋 格式错误！使用: /设置 日报时间 HH:MM\n例如: /设置 日报时间 21:00")
        
        elif action == "开启本群日报":
            if not actual_group_id:
                yield event.plain_result("📋 请在群聊中使用此指令！")
                return
            # 群管理操作：开启本群日报功能
            group_config = await plugin._get_group_config(actual_group_id)
            group_config["enabled"] = True
            await plugin._save_group_config(actual_group_id, group_config)
            yield event.plain_result("✅ 本群已开启日报功能\n📅 每日 23:00 自动生成并发送")
        
        elif action == "关闭本群日报":
            if not actual_group_id:
                yield event.plain_result("📋 请在群聊中使用此指令！")
                return
            group_config = await plugin._get_group_config(actual_group_id)
            group_config["enabled"] = False
            await plugin._save_group_config(actual_group_id, group_config)
            yield event.plain_result("❌ 本群已关闭日报功能")
        
        elif action == "通知开":
            settings["notification_enabled"] = True
            await plugin._store.update_user(user_id, user)
            yield event.plain_result("✅ 通知已开启")
        
        elif action == "通知关":
            settings["notification_enabled"] = False
            await plugin._store.update_user(user_id, user)
            yield event.plain_result("🔕 通知已关闭")
        
        else:
            yield event.plain_result("📋 无效设置指令！\n━━━━━━━━━━━━━━\n📖 /设置 订阅群日报\n📖 /设置 取消订阅群日报\n📖 /设置 订阅个人日报\n📖 /设置 取消订阅个人日报\n📖 /设置 日报时间 HH:MM\n━━━━━━━━━━━━━━")





# ========== 辅助函数 ==========

def _format_job_list() -> str:
    return "\n".join([f"{i}. {'💪' if j.get('type')=='体力' else '🧠'} {n} {j['hourly_wage']}金/时" for i, (n, j) in enumerate(JOBS.items(), 1)])


def _get_tier_emoji(tier: int) -> str:
    return {"1": "🔰", "2": "⬆️", "3": "⭐"}.get(str(tier), "")

def _format_course_list() -> str:
    lines = []
    skills_meta = get_skills_meta()
    for i, (course_id, c) in enumerate(COURSES.items(), 1):
        tier = c.get("tier", 1)
        emoji = _get_tier_emoji(tier)
        prereqs = c.get("prerequisites", {})
        prereq_str = ""
        if prereqs:
            prereq_str = " [需:" + "/".join([f"{k}Lv{v}" for k, v in prereqs.items()]) + "]"
        skill_name = c.get("skill", "")
        lines.append(f"{i}. {emoji}{skill_name}({c.get('name', '')}) {c.get('cost', 0)}金/时{prereq_str}")
    return "\n".join(lines[:50])


def _format_entertainment_list() -> str:
    items = list(ENTERTAINMENTS.items())[:8]
    return "\n".join([f"{i}. 🎮 {n} {e.get('cost_per_hour', 0)}金/时" for i, (n, e) in enumerate(items, 1)])


def _format_food_list() -> str:
    items = list(FOODS.items())[:8]
    return "\n".join([f"• {n} {f['price']}金 (+{f.get('restore_satiety', 0)}饱食)" for n, f in items])


def _format_profile_text(user: dict) -> str:
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
    
    # 压力显示
    body_p = user.get("body_pressure", 0)
    mind_p = user.get("mind_pressure", 0)
    def pbar(p):
        filled = int(p / 10)
        return "█" * filled + "░" * (10 - filled)
    pressure_lines = f"🏋️ 身体: {pbar(body_p)}{body_p:.0f}%\\n🧠 精神: {pbar(mind_p)}{mind_p:.0f}%"
    
    # Debuff 显示
    debuffs = user.get("active_debuffs", [])
    debuff_lines = ""
    if debuffs:
        from ...modules.constants import DEBUFF_DEFINITIONS
        debuff_names = []
        for d in debuffs:
            ddef = DEBUFF_DEFINITIONS.get(d, {})
            if ddef:
                debuff_names.append(f"{ddef.get('emoji', '')}{ddef.get('name', d)}")
        debuff_lines = "\\n" + " ".join(debuff_names)
    
    return (
        f"━━━━━━━━━━━━━━\\n"
        f"【 牛马档案 】\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"👤 {user.get('nickname', '未知')}\\n"
        f"💰 {user.get('gold', 0)}金币\\n"
        f"🏠 {user.get('residence', '桥下')}\\n"
        f"📋 {user.get('status', '空闲')}{debuff_lines}\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"❤️ {attrs.get('health', 0)} 💪 {attrs.get('strength', 0)}\\n"
        f"⚡ {attrs.get('energy', 0)} 😊 {attrs.get('mood', 0)}\\n"
        f"🍖 {attrs.get('satiety', 0)}\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"【 压力 】\\n{pressure_lines}\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"🔥 连续签到: {checkin.get('streak', 0)}天\\n"
        f"{luck_emoji} {luck_name} {buff_text}\\n"
        f"━━━━━━━━━━━━━━"
    )


def format_food_effects(effects: dict) -> str:
    """格式化食物/药品效果（简短）"""
    if not effects:
        return ""
    
    effect_names = {
        "satiety": "饱食",
        "mood": "心情",
        "health": "健康",
        "energy": "精力",
        "strength": "体力",
    }
    
    parts = []
    for key, value in effects.items():
        name = effect_names.get(key, key)
        if isinstance(value, (int, float)) and value > 0:
            parts.append(f"+{value}{name}")
    
    return f"({', '.join(parts)})" if parts else ""
