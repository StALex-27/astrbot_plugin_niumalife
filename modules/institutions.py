"""
教育机构系统模块
基于机构的学习推荐和查询
"""
import json
import random
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).parent.parent / "data" / "config"

def load_institutions() -> dict:
    with open(CONFIG_DIR / "institutions.json", encoding="utf-8") as f:
        return json.load(f)

def load_courses() -> dict:
    with open(CONFIG_DIR / "courses.json", encoding="utf-8") as f:
        return json.load(f)

INSTITUTIONS = load_institutions()
COURSES = load_courses()


def get_institution(inst_id: str) -> Optional[dict]:
    return INSTITUTIONS.get(inst_id)


def get_courses_by_institution(inst_id: str) -> list[dict]:
    """获取某机构的所有课程"""
    result = []
    for cid, course in COURSES.items():
        if course.get("institution") == inst_id:
            result.append({"id": cid, **course})
    return result


def filter_available_courses(courses: list, user: dict) -> list[dict]:
    """过滤出用户当前可学习的课程"""
    from .skills import check_course_available
    
    available = []
    for c in courses:
        ok, _ = check_course_available(c["id"], c, user)
        if ok:
            available.append(c)
    return available


def get_recommended_courses(inst_id: str, user: dict, limit: int = 5) -> list[dict]:
    """获取某机构对用户的推荐课程（最多limit门）"""
    inst_courses = get_courses_by_institution(inst_id)
    available = filter_available_courses(inst_courses, user)
    
    if not available:
        return []
    
    # 按价值排序（优先推荐玩家当前等级附近的课程）
    def value_score(c):
        user_lv = user.get("skills", {}).get(c["skill"], 0)
        # 目标等级与当前等级接近的优先
        dist = abs(c["can_learn_to"] - user_lv - 1)
        # tier高的优先
        tier_score = c["tier"] * 10
        return tier_score - dist
    
    available.sort(key=value_score, reverse=True)
    return available[:limit]


def select_institutions_for_user(user: dict, count: int = 4) -> list[str]:
    """根据用户技能状况选择推荐机构（最多count所）"""
    user_skills = user.get("skills", {})
    max_tier_seen = 1
    for skill_name, level in user_skills.items():
        if level > 0:
            from .skills import get_skill_tier
            tier = get_skill_tier(skill_name)
            if tier > max_tier_seen:
                max_tier_seen = tier
    
    # 构建候选列表
    candidates = []
    for inst_id, inst in INSTITUTIONS.items():
        tiers = inst.get("tier_coverage", [])
        if max_tier_seen == 1:
            # T1玩家：优先推基础机构，补充1-2所专业机构
            if 1 in tiers:
                candidates.append((inst_id, "foundation"))
            elif 2 in tiers:
                candidates.append((inst_id, "professional_t2"))
        elif max_tier_seen == 2:
            # T2玩家：推专业机构
            if 2 in tiers:
                candidates.append((inst_id, "professional"))
        else:
            # T3玩家：加入专精堂
            if inst.get("category") == "elite":
                candidates.append((inst_id, "elite"))
            elif 2 in tiers:
                candidates.append((inst_id, "professional"))
    
    # 去重（同名机构只保留一次）
    seen = set()
    unique = []
    for inst_id, _ in candidates:
        if inst_id not in seen:
            seen.add(inst_id)
            unique.append(inst_id)
    
    # 随机打乱后选取
    random.shuffle(unique)
    
    # 优先确保基础机构在前（熟悉感）
    foundation = [i for i in unique if INSTITUTIONS[i].get("category") == "foundation"]
    professional = [i for i in unique if INSTITUTIONS[i].get("category") == "professional"]
    elite = [i for i in unique if INSTITUTIONS[i].get("category") == "elite"]
    
    result = (foundation + professional + elite)[:count]
    return result


def get_all_institutions() -> list[dict]:
    """获取所有机构列表"""
    return [{"id": k, **v} for k, v in INSTITUTIONS.items()]


def search_courses_by_keyword(keyword: str, user: dict = None) -> list[dict]:
    """按关键词搜索课程（机构名、技能名、课程名）"""
    kw = keyword.lower()
    results = []
    for cid, course in COURSES.items():
        if (kw in cid.lower() or kw in course.get("skill", "").lower() or 
            kw in course.get("name", "").lower() or 
            kw in course.get("institution", "").lower()):
            item = {"id": cid, **course}
            if user:
                from .skills import check_course_available
                ok, _ = check_course_available(cid, course, user)
                item["available"] = ok
            results.append(item)
    return results


def get_courses_by_skill(skill_name: str, user: dict = None) -> list[dict]:
    """获取某技能的所有课程（按tier和机构分组）"""
    results = []
    for cid, course in COURSES.items():
        if course.get("skill") == skill_name:
            item = {"id": cid, **course}
            if user:
                from .skills import check_course_available
                ok, reason = check_course_available(cid, course, user)
                item["available"] = ok
                item["reason"] = reason
            results.append(item)
    
    # 按tier和institution排序
    results.sort(key=lambda x: (x["tier"], x.get("institution", "")))
    return results


def format_course_line(c: dict, show_inst: bool = False) -> str:
    """格式化单门课程的显示行"""
    tier_emoji = {1: "🔰", 2: "⬆️", 3: "⭐"}.get(c.get("tier", 1), "")
    total_cost = c.get("cost", 0) * c.get("hours", 2)
    prereqs = c.get("prerequisites", {})
    prereq_str = ""
    if prereqs:
        prereq_str = " [需:" + "/".join([f"{k}Lv{v}" for k, v in prereqs.items()]) + "]"
    
    inst_part = f" [{c.get('institution','')}]" if show_inst else ""
    return f"  {tier_emoji} {c.get('name','')}{inst_part} | 💰{total_cost}金{prereq_str}"


def format_institution_card(inst_id: str, courses: list, user_lv: dict) -> str:
    """格式化单个机构的推荐卡片"""
    inst = INSTITUTIONS.get(inst_id, {})
    emoji = inst.get("emoji", "🏫")
    name = inst.get("name", inst_id)
    desc = inst.get("desc", "")
    
    lines = [f"{emoji} {name}", f"  {desc}"]
    if courses:
        lines.append("  ─── 推荐课程 ───")
        for c in courses:
            skill_lv = user_lv.get(c.get("skill", ""), 0)
            lines.append(format_course_line(c) + f" (当前{c.get('skill')}Lv{skill_lv})")
    else:
        lines.append("  暂无可学习课程")
    
    return "\n".join(lines)


def get_skill_progress(user: dict, skill_name: str) -> dict:
    """获取用户在某技能上的进度信息"""
    from .skills import get_user_skill_level, exp_to_next_level, get_skill_exp_rate
    exp = user.get("skill_exp", {}).get(skill_name, 0)
    level = get_user_skill_level(skill_name, user)
    rate = get_skill_exp_rate(skill_name)
    next_exp = exp_to_next_level(exp, rate) if level < 10 else 0
    
    return {
        "skill": skill_name,
        "level": level,
        "exp": exp,
        "exp_to_next": next_exp,
        "exp_rate": rate
    }
