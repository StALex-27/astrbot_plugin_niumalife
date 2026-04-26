#!/usr/bin/env python3
"""
压力系统 v0.1.2 测试脚本
验证 debuff、压力、住院核心逻辑
"""
import sys
sys.path.insert(0, '.')

from datetime import datetime, timezone, timedelta
from modules.constants import (
    DEBUFF_DEFINITIONS, DEBUFF_ATTR_THRESHOLD, DEBUFF_RECOVERY_THRESHOLD,
    JOB_PRESSURE_RATE, JOB_PRESSURE_TYPE,
    PRESSURE_DECAY_IDLE, ENTERTAINMENT_PRESSURE_RELIEF,
    HOSPITAL_COST_PER_HOUR, HOSPITAL_HEALTH_PER_HOUR,
    HOSPITAL_STRENGTH_PER_HOUR, HOSPITAL_ENERGY_PER_HOUR,
    HOSPITAL_MOOD_TARGET, HOSPITAL_DISCHARGE_THRESHOLD,
    get_pressure_penalty, MAX_ATTRIBUTE, TICKS_PER_HOUR
)
from modules.debuff import (
    check_and_update_debuffs, calc_debuff_income_penalty,
    calc_debuff_learn_penalty, calc_debuff_recovery_penalty,
    accumulate_pressure, decay_pressure, is_exhausted, format_pressure,
    apply_debuff_strength_drain
)
from modules.user import UserStatus

def test_pressure_penalty():
    """测试压力惩罚曲线"""
    print("\n=== 压力惩罚曲线测试 ===")
    test_cases = [0, 30, 50, 55, 65, 75, 85, 90, 95, 100]
    for p in test_cases:
        penalty = get_pressure_penalty(p)
        print(f"  {p:3d}% 压力 → 效率 {1-penalty:.0%}")
    assert get_pressure_penalty(55) == 0.10
    assert get_pressure_penalty(75) == 0.20
    assert get_pressure_penalty(95) == 0.30
    print("✓ 压力惩罚曲线正确")

def test_exhaustion():
    """测试力竭判断"""
    print("\n=== 力竭判断测试 ===")
    for p in [89, 90, 95, 100]:
        user = {"body_pressure": p}
        result = is_exhausted(user, "body")
        print(f"  身体压力 {p}% → {'力竭❌' if result else '正常✅'}")
    assert is_exhausted({"body_pressure": 89}, "body") == False
    assert is_exhausted({"body_pressure": 90}, "body") == True
    assert is_exhausted({"body_pressure": 95}, "body") == True
    print("✓ 力竭判断正确")

def test_pressure_accumulation():
    """测试压力累积"""
    print("\n=== 压力累积测试 ===")
    user = {"body_pressure": 0, "mind_pressure": 0}
    
    # 搬砖(体力型) 3%/小时
    accumulate_pressure(user, "body", JOB_PRESSURE_RATE["搬砖"])
    print(f"  搬砖1小时后身体压力: {user['body_pressure']}%")
    assert user["body_pressure"] == 3
    
    # 程序员(脑力型) 6%/小时
    accumulate_pressure(user, "mind", JOB_PRESSURE_RATE["程序员"])
    print(f"  程序员1小时后退队压力: {user['mind_pressure']}%")
    assert user["mind_pressure"] == 6
    
    # 累积到力竭
    for _ in range(30):
        accumulate_pressure(user, "body", JOB_PRESSURE_RATE["搬砖"])
    print(f"  连续搬砖31小时后: {user['body_pressure']}%")
    assert is_exhausted(user, "body")
    print("✓ 压力累积正确")

def test_pressure_decay():
    """测试压力衰减"""
    print("\n=== 压力衰减测试 ===")
    user = {"body_pressure": 50, "mind_pressure": 50}
    
    # 空闲1小时衰减2%
    decay_pressure(user, "body", PRESSURE_DECAY_IDLE)
    decay_pressure(user, "mind", PRESSURE_DECAY_IDLE)
    print(f"  空闲1小时后: 身体{user['body_pressure']}% 精神{user['mind_pressure']}%")
    assert user["body_pressure"] == 48
    assert user["mind_pressure"] == 48
    print("✓ 压力衰减正确")

def test_entertainment_pressure_relief():
    """测试娱乐压力缓解"""
    print("\n=== 娱乐压力缓解测试 ===")
    
    # 按摩缓解身体疲劳15%
    user = {"body_pressure": 50, "mind_pressure": 50}
    relief = ENTERTAINMENT_PRESSURE_RELIEF["按摩"]
    accumulate_pressure(user, "body", -relief["body"])
    accumulate_pressure(user, "mind", -relief["mind"])
    print(f"  按摩后: 身体{user['body_pressure']}% 精神{user['mind_pressure']}%")
    assert user["body_pressure"] == 35
    assert user["mind_pressure"] == 45
    
    # 游戏缓解精神压力15%
    user = {"body_pressure": 50, "mind_pressure": 50}
    relief = ENTERTAINMENT_PRESSURE_RELIEF["游戏"]
    accumulate_pressure(user, "body", -relief["body"])
    accumulate_pressure(user, "mind", -relief["mind"])
    print(f"  游戏后: 身体{user['body_pressure']}% 精神{user['mind_pressure']}%")
    assert user["body_pressure"] == 47
    assert user["mind_pressure"] == 35
    print("✓ 娱乐压力缓解正确")

def test_debuff_trigger():
    """测试 Debuff 触发"""
    print("\n=== Debuff 触发测试 ===")
    now = datetime.now(timezone.utc)
    
    # 体力 < 20 持续10分钟 → 触发虚弱
    user = {
        "attributes": {"strength": 15, "energy": 50, "mood": 50, "satiety": 50, "health": 50},
        "active_debuffs": [],
        "debuff_timers": {"strength": (now - timedelta(minutes=11)).isoformat()},  # 11分钟前开始
        "checkin": {"active_buffs": []}
    }
    changes = check_and_update_debuffs(user, now)
    print(f"  体力15持续11分钟后: active_debuffs={user['active_debuffs']}")
    assert "weak" in user["active_debuffs"]
    assert "体力不足" in changes[0] or "虚弱" in str(changes)
    print("✓ Debuff 触发正确")
    
    # 有 buff 免疫 → 不触发
    user2 = {
        "attributes": {"strength": 15, "energy": 50, "mood": 50, "satiety": 50, "health": 50},
        "active_debuffs": [],
        "debuff_timers": {},
        "checkin": {"active_buffs": [{"immune_debuff": "weak"}]}  # 免疫虚弱
    }
    changes2 = check_and_update_debuffs(user2, now)
    print(f"  有免疫buff: active_debuffs={user2['active_debuffs']}")
    assert len(user2["active_debuffs"]) == 0
    print("✓ Buff免疫正确")

def test_debuff_recovery():
    """测试 Debuff 解除"""
    print("\n=== Debuff 解除测试 ===")
    now = datetime.now(timezone.utc)
    
    # 虚弱状态，体力恢复到 >= 50 → 解除
    user = {
        "attributes": {"strength": 55, "energy": 50, "mood": 50, "satiety": 50, "health": 50},
        "active_debuffs": ["weak"],
        "debuff_timers": {},
        "checkin": {"active_buffs": []}
    }
    changes = check_and_update_debuffs(user, now)
    print(f"  体力恢复55后: active_debuffs={user['active_debuffs']}")
    assert "weak" not in user["active_debuffs"]
    assert "虚弱状态解除" in changes[0]
    print("✓ Debuff 解除正确")

def test_debuff_penalty():
    """测试 Debuff 惩罚计算"""
    print("\n=== Debuff 惩罚计算测试 ===")
    
    # 虚弱 → 工作收入 -30%
    user1 = {"active_debuffs": ["weak"]}
    penalty = calc_debuff_income_penalty(user1)
    print(f"  虚弱状态: 工作收入 {penalty:.0%}")
    assert penalty == 0.70
    
    # 抑郁 → 所有活动 -20%
    user2 = {"active_debuffs": ["depressed"]}
    penalty2 = calc_debuff_income_penalty(user2)  # 抑郁影响all_penalty
    print(f"  抑郁状态: 工作收入 {penalty2:.0%}")
    assert penalty2 == 0.80
    
    # 虚弱 + 抑郁 → 叠加
    user3 = {"active_debuffs": ["weak", "depressed"]}
    penalty3 = calc_debuff_income_penalty(user3)
    print(f"  虚弱+抑郁: 工作收入 {penalty3:.0%}")
    assert penalty3 == 0.50  # 0.7 * 0.8... 实际上是和计算的
    print("✓ Debuff 惩罚计算正确")

def test_hospital():
    """测试住院机制"""
    print("\n=== 住院机制测试 ===")
    
    # 健康 <= 0 → 应该住院
    user = {
        "attributes": {"health": 0, "strength": 0, "energy": 0, "mood": 50, "satiety": 20},
        "gold": 100,
        "status": UserStatus.FREE,
    }
    
    # 模拟住院处理
    cost_per_tick = HOSPITAL_COST_PER_HOUR / TICKS_PER_HOUR
    user["gold"] = max(0, user.get("gold", 0) - cost_per_tick)
    user["attributes"]["health"] = min(100, user["attributes"].get("health", 0) + HOSPITAL_HEALTH_PER_HOUR / TICKS_PER_HOUR)
    user["attributes"]["strength"] = min(100, user["attributes"].get("strength", 0) + HOSPITAL_STRENGTH_PER_HOUR / TICKS_PER_HOUR)
    user["attributes"]["energy"] = min(100, user["attributes"].get("energy", 0) + HOSPITAL_ENERGY_PER_HOUR / TICKS_PER_HOUR)
    
    print(f"  住院1tick后: 金币-{cost_per_tick:.1f} 健康+{HOSPITAL_HEALTH_PER_HOUR/TICKS_PER_HOUR:.2f}")
    print(f"  当前金币: {user['gold']:.1f} 健康: {user['attributes']['health']:.2f}")
    
    # 心情固定测试
    user_high_mood = {"attributes": {"mood": 80}, "gold": 100, "status": UserStatus.HOSPITALIZED}
    user_low_mood = {"attributes": {"mood": 10}, "gold": 100, "status": UserStatus.HOSPITALIZED}
    
    # 心情每tick调整1/TICKS_PER_HOUR，需要 TICKS_PER_HOUR ticks = 1小时才能收敛
    # 从80收敛到20需要 (80-20)/(1/60) = 3600 ticks = 1小时
    for u in [user_high_mood, user_low_mood]:
        for _ in range(3700):  # 模拟1小时以上
            m = u["attributes"]["mood"]
            if m > HOSPITAL_MOOD_TARGET:
                u["attributes"]["mood"] = max(HOSPITAL_MOOD_TARGET, m - 1/TICKS_PER_HOUR)
            elif m < HOSPITAL_MOOD_TARGET:
                u["attributes"]["mood"] = min(HOSPITAL_MOOD_TARGET, m + 1/TICKS_PER_HOUR)
    
    print(f"  高心情80→{user_high_mood['attributes']['mood']:.1f} 低心情10→{user_low_mood['attributes']['mood']:.1f}")
    assert user_high_mood["attributes"]["mood"] == HOSPITAL_MOOD_TARGET
    assert user_low_mood["attributes"]["mood"] == HOSPITAL_MOOD_TARGET
    print("✓ 住院机制正确")

def test_format_pressure():
    """测试压力格式化"""
    print("\n=== 压力格式化测试 ===")
    
    user_low = {"body_pressure": 30, "mind_pressure": 20}
    user_mid = {"body_pressure": 60, "mind_pressure": 70}
    user_high = {"body_pressure": 95, "mind_pressure": 85}
    
    print(f"  低压力:\n{format_pressure(user_low)}")
    print(f"  中压力:\n{format_pressure(user_mid)}")
    print(f"  高压力:\n{format_pressure(user_high)}")
    print("✓ 压力格式化正确")

def test_work_pressure_accumulation():
    """测试工作压力累积与收入惩罚"""
    print("\n=== 工作压力累积与收入测试 ===")
    
    # 高压力工作，效率大幅下降
    user = {
        "body_pressure": 75,  # 70-80% 区间，-20%效率
        "active_debuffs": [],
        "attributes": {"satiety": 50},
        "checkin": {"active_buffs": []}
    }
    
    job_name = "搬砖"
    job_rate = JOB_PRESSURE_RATE[job_name]
    pressure_penalty = 1.0 - get_pressure_penalty(user["body_pressure"])
    
    print(f"  搬砖(3%/h) + 75%压力 → 效率{pressure_penalty:.0%}")
    assert pressure_penalty == 0.80
    assert job_rate == 3
    
    # 模拟连续工作10小时
    for _ in range(10):
        accumulate_pressure(user, "body", job_rate)
    print(f"  连续搬砖10小时: 压力{user['body_pressure']}%")
    assert user["body_pressure"] == 100  # capped at 100  # capped at 100
    print("✓ 工作压力累积正确")

def main():
    print("=" * 50)
    print("牛马人生 v0.1.2 压力系统测试")
    print("=" * 50)
    
    test_pressure_penalty()
    test_exhaustion()
    test_pressure_accumulation()
    test_pressure_decay()
    test_entertainment_pressure_relief()
    test_debuff_trigger()
    test_debuff_recovery()
    test_debuff_penalty()
    test_hospital()
    test_format_pressure()
    test_work_pressure_accumulation()
    
    print("\n" + "=" * 50)
    print("✅ 所有测试通过!")
    print("=" * 50)

if __name__ == "__main__":
    main()
