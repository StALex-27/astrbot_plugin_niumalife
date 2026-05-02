"""
学习命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_LEARN
from ...modules.constants import MAX_ATTRIBUTE, INSTITUTIONS, COURSES
from ...modules.institutions import (
    select_institutions_for_user, get_recommended_courses,
    get_institution, get_courses_by_institution,
    get_all_institutions, search_courses_by_keyword,
    get_courses_by_skill, get_skill_progress
)
from ...modules.skills import check_course_available, get_skills_meta


LOCAL_TZ = timezone(timedelta(hours=8))


async def run_learn_logic(event: AstrMessageEvent, store, parser, renderer):
    """学习命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    if user["status"] != UserStatus.FREE:
        yield event.plain_result(f"📋 你正在{user['status']}，无法学习\n先用 /取消 取消当前动作")
        return

    _, args = parser.parse(event)

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
    await store.update_user(user_id, user)

    course_name_display = f"{course.get('institution','')}·{course.get('name','')}"
    try:
        url = await renderer.render_entertain_start(
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
