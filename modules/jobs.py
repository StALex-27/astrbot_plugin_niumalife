"""
工作系统模块
包含工作相关配置和工作收益计算
"""
from .constants import JOBS


def calc_work_income(job_name: str, hours: int, efficiency: float = 1.0) -> int:
    """计算工作收益
    
    Args:
        job_name: 工作名称
        hours: 工作小时数
        efficiency: 效率倍率 (0.0-1.0)
    
    Returns:
        int: 实际获得的金币
    """
    job = JOBS.get(job_name)
    if not job:
        return 0
    
    base_income = job["hourly_wage"] * hours
    return int(base_income * efficiency)


def calc_work_consumption(job_name: str, hours: int) -> dict:
    """计算工作消耗
    
    Args:
        job_name: 工作名称
        hours: 工作小时数
    
    Returns:
        dict: 各种属性的消耗量
    """
    job = JOBS.get(job_name)
    if not job:
        return {}
    
    return {
        "strength": job["consume_strength"] * hours,
        "energy": job["consume_energy"] * hours,
        "mood": job["consume_mood"] * hours,
        "health": job["consume_health"] * hours,
        "satiety": job["consume_satiety"] * hours * 0.5,
    }


def check_job_requirement(user_skills: dict, job_name: str) -> tuple[bool, str]:
    """检查是否满足工作要求
    
    Args:
        user_skills: 用户技能字典
        job_name: 工作名称
    
    Returns:
        tuple[bool, str]: (是否满足, 不满足原因)
    """
    job = JOBS.get(job_name)
    if not job:
        return False, f"不存在该工作：{job_name}"
    
    skill_required = job.get("skill_required", {})
    for skill, level in skill_required.items():
        if user_skills.get(skill, 0) < level:
            return False, f"技能不足，需要 {skill} Lv.{level}"
    
    return True, ""


def get_all_jobs_by_type() -> dict:
    """按类型分类所有工作
    
    Returns:
        dict: {类型: [工作列表]}
    """
    result = {"体力": [], "脑力": [], "技能": []}
    for job_name, job_info in JOBS.items():
        job_type = job_info.get("type", "体力")
        if job_type in result:
            result[job_type].append({
                "name": job_name,
                **job_info
            })
    return result