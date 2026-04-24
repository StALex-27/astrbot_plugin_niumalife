"""
技能/经验系统模块
包含技能等级、经验值计算、技能迁移等函数
"""

# 经验值表（每级所需经验）
EXP_TABLE = {
    1: 0,
    2: 100,
    3: 300,
    4: 600,
    5: 1000,
    6: 1500,
    7: 2100,
    8: 2800,
    9: 3600,
    10: 4500,
    11: 5500,
    12: 6600,
    13: 7800,
    14: 9100,
    15: 10500,
}

# 每小时经验获取（按等级）
EXP_PER_HOUR_BY_LEVEL = {
    1: 10,
    2: 12,
    3: 14,
    4: 16,
    5: 18,
    6: 20,
    7: 22,
    8: 24,
    9: 26,
    10: 28,
    11: 30,
    12: 32,
    13: 34,
    14: 36,
    15: 40,
}

# 难度倍率（影响经验获取速度）
DIFFICULTY_MULTIPLIER = {
    "入门": 1.0,
    "初级": 1.2,
    "中级": 1.5,
    "高级": 2.0,
    "专家": 3.0,
}


def get_skill_level(exp: int) -> int:
    """根据经验值获取技能等级
    
    Args:
        exp: 当前经验值
    
    Returns:
        int: 技能等级 (1-15)
    """
    level = 1
    for lvl, req_exp in EXP_TABLE.items():
        if exp >= req_exp:
            level = lvl
        else:
            break
    return min(level, 15)


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


def exp_to_next_level(current_exp: int) -> int:
    """计算到下一级还需要多少经验
    
    Args:
        current_exp: 当前经验值
    
    Returns:
        int: 到下一级还需的经验值
    """
    current_level = get_skill_level(current_exp)
    if current_level >= 15:
        return 0
    next_exp = EXP_TABLE.get(current_level + 1, 0)
    return next_exp - current_exp


def migrate_skills(user_data: dict) -> dict:
    """迁移旧格式技能数据到新格式
    
    旧格式: {"skills": {"苦力": 1}}  (值为等级)
    新格式: {"skills": {"苦力": 1}, "skill_exp": {"苦力": 100}}
    
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
            # 估算经验值：假设每级对应 100 * level 点经验
            est_exp = sum(EXP_TABLE.get(i, 0) for i in range(1, level + 1))
            user_data["skill_exp"][skill_name] = est_exp
    
    return user_data