"""
Debuff系统模块
处理低属性 debuff 的触发、检查、计算惩罚
"""
from datetime import datetime, timezone
from typing import Optional

from .constants import (
    DEBUFF_DEFINITIONS, DEBUFF_ATTR_THRESHOLD, DEBUFF_RECOVERY_THRESHOLD,
    MAX_ATTRIBUTE
)


# ============================================================
# Debuff 触发检测
# ============================================================

def check_and_update_debuffs(user: dict, now: datetime) -> list[str]:
    """
    检查用户属性，更新 debuff 计时器，触发/解除 debuff
    
    Args:
        user: 用户数据
        now: 当前时间
    
    Returns:
        list: 变化描述列表（用于通知用户）
    """
    changes = []
    attrs = user.get("attributes", {})
    timers = user.setdefault("debuff_timers", {})
    active_debuffs = user.setdefault("active_debuffs", [])
    
    # 遍历所有属性检查是否触发 debuff
    attr_debuff_map = {
        "strength": "weak",      # 虚弱
        "energy": "tired",       # 疲劳
        "satiety": "hungry",    # 饥饿
        "health": "sick",       # 疾病
    }
    
    # 心情单独检查（影响所有活动）
    if attrs.get("mood", 100) < DEBUFF_ATTR_THRESHOLD:
        if "depressed" not in active_debuffs:
            if not _has_immune_buff(user, "depressed"):
                if not _is_timer_active(timers, "mood"):
                    _start_timer(timers, "mood", now)
                elif _is_timer_expired(timers, "mood", now, minutes=10):
                    active_debuffs.append("depressed")
                    changes.append("😔 你感到抑郁，所有活动效率 -20%")
                    del timers["mood"]
    else:
        # 心情恢复，解除抑郁
        if "depressed" in active_debuffs:
            if attrs.get("mood", 0) >= DEBUFF_RECOVERY_THRESHOLD:
                active_debuffs.remove("depressed")
                changes.append("😊 心情恢复，抑郁状态解除")
    
    # 检查其他属性 debuff
    for attr_name, debuff_id in attr_debuff_map.items():
        value = attrs.get(attr_name, MAX_ATTRIBUTE)
        
        if value < DEBUFF_ATTR_THRESHOLD:
            # 属性低于阈值
            if debuff_id not in active_debuffs:
                # 未生效，检查免疫
                if not _has_immune_buff(user, debuff_id):
                    if not _is_timer_active(timers, attr_name):
                        _start_timer(timers, attr_name, now)
                    elif _is_timer_expired(timers, attr_name, now, minutes=10):
                        active_debuffs.append(debuff_id)
                        debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
                        if debuff_def:
                            changes.append(f"{debuff_def['emoji']} {debuff_def['desc']}")
                        del timers[attr_name]
        else:
            # 属性已恢复，解除 debuff
            if debuff_id in active_debuffs:
                if value >= DEBUFF_RECOVERY_THRESHOLD:
                    active_debuffs.remove(debuff_id)
                    debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
                    if debuff_def:
                        changes.append(f"{debuff_def['emoji']} {debuff_def['name']}状态解除")
    
    user["active_debuffs"] = active_debuffs
    user["debuff_timers"] = timers
    return changes


def _has_immune_buff(user: dict, debuff_id: str) -> bool:
    """检查用户是否有免疫该 debuff 的 buff"""
    active_buffs = user.get("checkin", {}).get("active_buffs", [])
    for buff in active_buffs:
        if buff.get("immune_debuff") == debuff_id:
            return True
    return False


def _is_timer_active(timers: dict, key: str) -> bool:
    return key in timers


def _start_timer(timers: dict, key: str, now: datetime):
    timers[key] = now.isoformat()


def _is_timer_expired(timers: dict, key: str, now: datetime, minutes: int = 10) -> bool:
    if key not in timers:
        return False
    start = datetime.fromisoformat(timers[key])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    elapsed = (now - start).total_seconds()
    return elapsed >= minutes * 60


# ============================================================
# Debuff 惩罚计算
# ============================================================

def calc_debuff_income_penalty(user: dict) -> float:
    """
    计算 debuff 导致的工作收入惩罚倍率
    
    Returns:
        float: 惩罚倍率（如 0.70 表示 -30%）
    """
    active_debuffs = user.get("active_debuffs", [])
    penalty = 0.0
    
    for debuff_id in active_debuffs:
        debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
        if not debuff_def:
            continue
        effect = debuff_def.get("effect", "")
        if effect == "income_penalty":
            penalty += debuff_def.get("value", 0.0)
        elif effect == "all_penalty":
            penalty += debuff_def.get("value", 0.0)
    
    return 1.0 - penalty


def calc_debuff_learn_penalty(user: dict) -> float:
    """计算 debuff 导致的学习效率惩罚倍率"""
    active_debuffs = user.get("active_debuffs", [])
    penalty = 0.0
    
    for debuff_id in active_debuffs:
        debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
        if not debuff_def:
            continue
        effect = debuff_def.get("effect", "")
        if effect == "learn_penalty":
            penalty += debuff_def.get("value", 0.0)
        elif effect == "all_penalty":
            penalty += debuff_def.get("value", 0.0)
    
    return 1.0 - penalty


def calc_debuff_recovery_penalty(user: dict) -> float:
    """计算 debuff 导致的被动恢复惩罚倍率"""
    active_debuffs = user.get("active_debuffs", [])
    penalty = 0.0
    
    for debuff_id in active_debuffs:
        debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
        if not debuff_def:
            continue
        effect = debuff_def.get("effect", "")
        if effect == "recovery_penalty":
            penalty += debuff_def.get("value", 0.0)
    
    return 1.0 - penalty


def apply_debuff_strength_drain(attrs: dict, user: dict, ticks: float = 1.0):
    """应用 debuff 的体力流失效果（饥饿等）"""
    active_debuffs = user.get("active_debuffs", [])
    
    for debuff_id in active_debuffs:
        debuff_def = DEBUFF_DEFINITIONS.get(debuff_id)
        if not debuff_def:
            continue
        effect = debuff_def.get("effect", "")
        if effect == "strength_drain":
            drain = debuff_def.get("value", 0) * ticks  # per tick
            attrs["strength"] = max(0, attrs.get("strength", 0) - drain)


# ============================================================
# 压力系统计算
# ============================================================

def get_pressure_penalty_for_job(user: dict, job_name: str, pressure_type: str) -> float:
    """
    计算特定工作类型因压力导致的效率惩罚
    
    Args:
        user: 用户数据
        job_name: 工作名称
        pressure_type: "body" 或 "mind"
    
    Returns:
        float: 惩罚倍率（0.70 表示 -30%）
    """
    from .constants import get_pressure_penalty
    
    pressure = user.get(f"{pressure_type}_pressure", 0)
    return 1.0 - get_pressure_penalty(pressure)


def decay_pressure(user: dict, pressure_type: str, amount: float):
    """衰减压力值"""
    current = user.get(f"{pressure_type}_pressure", 0)
    user[f"{pressure_type}_pressure"] = max(0, current - amount)


def accumulate_pressure(user: dict, pressure_type: str, amount: float):
    """累积压力值，上限 100"""
    current = user.get(f"{pressure_type}_pressure", 0)
    user[f"{pressure_type}_pressure"] = min(100, current + amount)


def is_exhausted(user: dict, pressure_type: str) -> bool:
    """检查是否因压力过高而力竭（无法进行该类型工作）"""
    pressure = user.get(f"{pressure_type}_pressure", 0)
    return pressure >= 90


def format_pressure(user: dict) -> str:
    """格式化压力显示"""
    body = user.get("body_pressure", 0)
    mind = user.get("mind_pressure", 0)
    
    def bar(p):
        filled = int(p / 10)
        return "█" * filled + "░" * (10 - filled)
    
    body_bar = bar(body)
    mind_bar = bar(mind)
    
    # 状态描述
    body_status = _pressure_status(body)
    mind_status = _pressure_status(mind)
    
    lines = [
        f"🏋️ 身体疲劳: {body_bar} {body:.0f}% {body_status}",
        f"🧠 精神压力: {mind_bar} {mind:.0f}% {mind_status}",
    ]
    return "\n".join(lines)


def _pressure_status(p: float) -> str:
    if p < 50:
        return ""
    elif p < 60:
        return "(效率-10%)"
    elif p < 70:
        return "(效率-15%)"
    elif p < 80:
        return "(效率-20%)"
    elif p < 90:
        return "(效率-25%)"
    else:
        return "(力竭!)"
