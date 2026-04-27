"""
技能/经验系统模块 v2
包含技能等级、经验值计算、前置检查、技能迁移等函数
三档经验曲线：fast(速成)/standard(标准)/mastery(精修)
"""

# 三档经验曲线（1-10级累计经验）
EXP_RATE_TABLE = {
    # 速成 T1：1→2=80, 2→3=160... 满级3600
    "fast": {
        1: 0, 2: 80, 3: 240, 4: 480, 5: 800,
        6: 1200, 7: 1680, 8: 2240, 9: 2880, 10: 3600,
    },
    # 标准 T2：1→2=120, 2→3=240... 满级5400
    "standard": {
        1: 0, 2: 120, 3: 360, 4: 720, 5: 1200,
        6: 1800, 7: 2520, 8: 3360, 9: 4320, 10: 5400,
    },
    # 精修 T3：1→2=180, 2→3=360... 满级8100
    "mastery": {
        1: 0, 2: 180, 3: 540, 4: 1080, 5: 1800,
        6: 2700, 7: 3780, 8: 5040, 9: 6480, 10: 8100,
    },
}

# 技能元数据（从 data/config/skills.json 加载）
_SKILLS_META: dict = None

def _load_skills_meta() -> dict:
    global _SKILLS_META
    if _SKILLS_META is not None:
        return _SKILLS_META
    from pathlib import Path
    import json
    meta_path = Path(__file__).parent.parent / "data" / "config" / "skills.json"
    with open(meta_path, encoding="utf-8") as f:
        raw = json.load(f)
    # 去掉_meta元字段
    _SKILLS_META = {k: v for k, v in raw.items() if k != "_meta"}
    return _SKILLS_META

def get_skills_meta() -> dict:
    return _load_skills_meta()

def get_skill_meta(skill_name: str) -> dict:
    return get_skills_meta().get(skill_name, {})

def get_skill_tier(skill_name: str) -> int:
    meta = get_skill_meta(skill_name)
    return meta.get("tier", 1)

def get_skill_exp_rate(skill_name: str) -> str:
    """获取技能对应的经验曲线类型"""
    meta = get_skill_meta(skill_name)
    return meta.get("exp_rate", "standard")

def get_skill_level(exp: int, exp_rate: str = "standard") -> int:
    """根据经验值获取技能等级
    
    Args:
        exp: 当前经验值
        exp_rate: 经验曲线类型 fast/standard/mastery
    
    Returns:
        int: 技能等级 (1-10)
    """
    table = EXP_RATE_TABLE.get(exp_rate, EXP_RATE_TABLE["standard"])
    level = 1
    for lvl, req_exp in table.items():
        if exp >= req_exp:
            level = lvl
        else:
            break
    return min(level, 10)

def get_user_skill_level(skill_name: str, user_data: dict) -> int:
    """获取用户某技能的实际等级（考虑曲线类型）
    
    Args:
        skill_name: 技能名称
        user_data: 用户数据
    
    Returns:
        int: 技能等级 (1-10)
    """
    exp = user_data.get("skill_exp", {}).get(skill_name, 0)
    exp_rate = get_skill_exp_rate(skill_name)
    return get_skill_level(exp, exp_rate)

def get_skill_exp(skill_name: str, user_data: dict) -> int:
    """获取用户某技能的经验值
    
    Args:
        skill_name: 技能名称
        user_data: 用户数据
    
    Returns:
        int: 经验值（如果没有则返回0）
    """
    skill_data = user_data.get("skill_exp", {})
    return skill_data.get(skill_name, 0)

def exp_to_next_level(current_exp: int, exp_rate: str = "standard") -> int:
    """计算到下一级还需要多少经验
    
    Args:
        current_exp: 当前经验值
        exp_rate: 经验曲线类型
    
    Returns:
        int: 到下一级还需的经验值，10级满则返回0
    """
    current_level = get_skill_level(current_exp, exp_rate)
    if current_level >= 10:
        return 0
    table = EXP_RATE_TABLE.get(exp_rate, EXP_RATE_TABLE["standard"])
    next_exp = table.get(current_level + 1, 0)
    return next_exp - current_exp

def check_course_prerequisites(course: dict, user: dict) -> tuple[bool, str]:
    """检查用户是否满足课程的前置条件
    
    Args:
        course: 课程配置字典
        user: 用户数据
    
    Returns:
        (是否满足, 错误消息)
    """
    prereqs = course.get("prerequisites", {})
    if not prereqs:
        return True, ""
    
    skill_exp = user.get("skill_exp", {})
    
    for skill_name, min_level in prereqs.items():
        # 前置技能统一用 standard 曲线计算等级
        user_exp = skill_exp.get(skill_name, 0)
        user_level = get_skill_level(user_exp, "standard")
        if user_level < min_level:
            return False, f"前置不满足：「{skill_name}」需达 Lv{min_level}（当前 Lv{user_level}）"
    
    return True, ""

def check_skill_learning_valid(course: dict, user: dict) -> tuple[bool, str]:
    """检查用户当前技能等级是否可以学习该课程
    
    Args:
        course: 课程配置字典
        user: 用户数据
    
    Returns:
        (是否满足, 错误消息)
    """
    skill_name = course.get("skill", "")
    min_lvl = course.get("min_skill_level", 0)
    max_lvl = course.get("max_skill_level", 10)
    
    user_level = get_user_skill_level(skill_name, user)
    
    if user_level > max_lvl:
        return False, f"「{skill_name}」已达 Lv{max_lvl}，无法继续学习此课程"
    
    if user_level < min_lvl:
        return False, f"「{skill_name}」需达 Lv{min_lvl} 才能学习此课程（当前 Lv{user_level}）"
    
    return True, ""

def check_course_available(course_id: str, course: dict, user: dict) -> tuple[bool, str]:
    """综合检查课程是否可学（前置+等级）
    
    Returns:
        (是否可学, 原因消息)
    """
    # 前置技能检查
    ok, msg = check_course_prerequisites(course, user)
    if not ok:
        return False, msg
    
    # 当前技能等级检查
    ok, msg = check_skill_learning_valid(course, user)
    if not ok:
        return False, msg
    
    return True, "可学习"

def migrate_skills(user_data: dict) -> dict:
    """迁移旧格式技能数据到新格式 v2
    
    旧格式: {"skills": {"苦力": 1}}  (值为等级)
    新格式: {"skills": {"苦力": 1}, "skill_exp": {"苦力": 累计经验}}
    
    同时将所有技能的经验曲线统一为各自的 exp_rate，
    旧经验值按比例压缩到新表。
    
    Args:
        user_data: 用户数据
    
    Returns:
        dict: 迁移后的用户数据
    """
    if "skill_exp" not in user_data:
        user_data["skill_exp"] = {}
    
    # 迁移旧格式
    skills = user_data.get("skills", {})
    for skill_name, level in skills.items():
        if skill_name not in user_data["skill_exp"]:
            # 旧表满级15级，经验对应等级
            # 旧EXP_TABLE: 0,100,300,600,1000,1500,2100,2800,3600,4500,5500,6600,7800,9100,10500
            old_table = {
                1: 0, 2: 100, 3: 300, 4: 600, 5: 1000,
                6: 1500, 7: 2100, 8: 2800, 9: 3600, 10: 4500,
                11: 5500, 12: 6600, 13: 7800, 14: 9100, 15: 10500,
            }
            old_exp = old_table.get(level, 0)
            # 获取新曲线类型
            exp_rate = get_skill_exp_rate(skill_name)
            new_table = EXP_RATE_TABLE.get(exp_rate, EXP_RATE_TABLE["standard"])
            # 找到旧经验对应到新表的大概位置
            new_exp = 0
            for lvl, req in new_table.items():
                if req <= old_exp * 2:  # 粗略换算
                    new_exp = req
            user_data["skill_exp"][skill_name] = new_exp
    
    return user_data
