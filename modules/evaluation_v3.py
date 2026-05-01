"""
打工系统 V2 - 六维评价系统
独立的评价计算模块，提供详细的评价分析和可视化
"""

import json
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class EvaluationScore:
    """单个维度评价分"""
    dimension: str
    value: float
    max_value: float = 100.0
    bonus: float = 0.0
    weight: float = 0.0
    
    @property
    def weighted_value(self) -> float:
        """加权后的值"""
        return self.value * self.weight
        
    @property
    def percentage(self) -> float:
        """百分比"""
        return (self.value / self.max_value * 100) if self.max_value > 0 else 0


@dataclass
class EvaluationResult:
    """完整评价结果"""
    final_score: float
    grade: str
    grade_name: str
    efficiency: EvaluationScore
    quality: EvaluationScore
    stress: EvaluationScore
    mood: EvaluationScore
    skill_match: EvaluationScore
    buff: EvaluationScore
    
    # 评价详情
    actual_hours: float = 0.0
    expected_hours: float = 0.0
    time_bonus: float = 0.0
    
    # 奖励信息
    base_reward: int = 0
    final_reward: int = 0
    reward_multiplier: float = 1.0
    bonus_gold: int = 0
    
    # 经验信息
    exp_gained: Dict[str, int] = field(default_factory=dict)
    
    # 好感度信息
    favor_change: int = 0
    
    def to_dict(self) -> dict:
        return {
            "final_score": self.final_score,
            "grade": self.grade,
            "grade_name": self.grade_name,
            "dimensions": {
                "efficiency": self._score_to_dict(self.efficiency),
                "quality": self._score_to_dict(self.quality),
                "stress": self._score_to_dict(self.stress),
                "mood": self._score_to_dict(self.mood),
                "skill_match": self._score_to_dict(self.skill_match),
                "buff": self._score_to_dict(self.buff),
            },
            "time": {
                "actual_hours": self.actual_hours,
                "expected_hours": self.expected_hours,
                "time_bonus": self.time_bonus,
            },
            "rewards": {
                "base": self.base_reward,
                "final": self.final_reward,
                "multiplier": self.reward_multiplier,
                "bonus_gold": self.bonus_gold,
            },
            "exp": self.exp_gained,
            "favor_change": self.favor_change,
        }
        
    def _score_to_dict(self, score: EvaluationScore) -> dict:
        return {
            "value": score.value,
            "max": score.max_value,
            "bonus": score.bonus,
            "weight": score.weight,
            "weighted": score.weighted_value,
        }


class EvaluationV3:
    """
    六维评价计算器
    
    评价维度：
    1. 效率 (efficiency) - 20%
    2. 质量 (quality) - 15%
    3. 压力 (stress) - 10%
    4. 心情 (mood) - 10%
    5. 技能匹配 (skill_match) - 25%
    6. Buff加成 (buff) - 20%
    """
    
    def __init__(self, config_dir: str = None):
        """初始化评价器"""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "data" / "config"
        self.config_dir = Path(config_dir)
        
        self._load_config()
        
    def _load_config(self):
        """加载评价配置"""
        with open(self.config_dir / "evaluation_rules.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            
        self.grades = config.get("evaluation_grades", {})
        self.weights = config.get("weight_config", {})
        self.stress_rules = config.get("stress_rules", {})
        self.mood_rules = config.get("mood_rules", {})
        self.skill_rules = config.get("skill_match_rules", {})
        self.buff_rules = config.get("buff_rules", {})
        
    def evaluate(self, user_data: dict, job_data: dict, 
                 actual_hours: float) -> EvaluationResult:
        """
        执行完整评价
        
        Args:
            user_data: 玩家数据
            job_data: 委托数据
            actual_hours: 实际用时（小时）
            
        Returns:
            EvaluationResult 评价结果
        """
        # 提取数据
        expected_hours = job_data.get("duration_hours", 1)
        difficulty = job_data.get("difficulty", "B")
        base_reward = job_data.get("base_reward", 100)
        consume = job_data.get("consume", {})
        skill_required = job_data.get("skill_required", {})
        exp_reward = job_data.get("exp_reward", {})
        
        # 提取玩家属性
        player_skills = user_data.get("skills", {})
        player_mood = user_data.get("mood", 50)
        player_stress = user_data.get("pressure_mind", 30)
        active_buffs = user_data.get("active_buffs", [])
        
        # 计算各维度
        eff = self._calc_efficiency(expected_hours, actual_hours)
        qual = self._calc_quality(consume)
        stress_b = self._calc_stress_bonus(player_stress)
        mood_b = self._calc_mood_bonus(player_mood)
        skill_b = self._calc_skill_bonus(player_skills, skill_required)
        buff_b = self._calc_buff_bonus(active_buffs, job_data.get("company_id"))
        
        # 创建评分对象
        efficiency_score = EvaluationScore(
            dimension="效率",
            value=eff,
            max_value=100,
            bonus=0,
            weight=self.weights.get("efficiency", {}).get("weight", 0.20)
        )
        
        quality_score = EvaluationScore(
            dimension="质量",
            value=qual,
            max_value=100,
            bonus=0,
            weight=self.weights.get("quality", {}).get("weight", 0.15)
        )
        
        stress_score = EvaluationScore(
            dimension="压力",
            value=50 + stress_b,
            max_value=100,
            bonus=stress_b,
            weight=self.weights.get("stress", {}).get("weight", 0.10)
        )
        
        mood_score = EvaluationScore(
            dimension="心情",
            value=50 + mood_b,
            max_value=100,
            bonus=mood_b,
            weight=self.weights.get("mood", {}).get("weight", 0.10)
        )
        
        skill_score = EvaluationScore(
            dimension="技能匹配",
            value=50 + skill_b,
            max_value=100,
            bonus=skill_b,
            weight=self.weights.get("skill_match", {}).get("weight", 0.25)
        )
        
        buff_score = EvaluationScore(
            dimension="Buff加成",
            value=50 + buff_b,
            max_value=100,
            bonus=buff_b,
            weight=self.weights.get("buff", {}).get("weight", 0.20)
        )
        
        # 计算总分
        total_weighted = (
            efficiency_score.weighted_value +
            quality_score.weighted_value +
            stress_score.weighted_value +
            mood_score.weighted_value +
            skill_score.weighted_value +
            buff_score.weighted_value
        )
        
        # 最终分数归一化到0-100
        final_score = max(0, min(100, total_weighted))
        
        # 确定等级
        grade, grade_name = self._determine_grade(final_score)
        grade_info = self.grades.get(grade, {})
        
        # 计算时间奖励
        time_bonus = self._calc_time_bonus(expected_hours, actual_hours)
        
        # 计算奖励
        reward_mult = grade_info.get("reward_multiplier", 1.0)
        final_reward = int(base_reward * reward_mult)
        bonus_gold = int(base_reward * grade_info.get("bonus_gold_percent", 0) / 100)
        
        return EvaluationResult(
            final_score=round(final_score, 1),
            grade=grade,
            grade_name=grade_name,
            efficiency=efficiency_score,
            quality=quality_score,
            stress=stress_score,
            mood=mood_score,
            skill_match=skill_score,
            buff=buff_score,
            actual_hours=actual_hours,
            expected_hours=expected_hours,
            time_bonus=time_bonus,
            base_reward=base_reward,
            final_reward=final_reward + bonus_gold,
            reward_multiplier=reward_mult,
            bonus_gold=bonus_gold,
            exp_gained=exp_reward,
            favor_change=grade_info.get("bonus_favorability", 0),
        )
        
    def _calc_efficiency(self, expected: float, actual: float) -> float:
        """
        计算效率分
        
        公式: min(100, (expected / actual) * 50)
        
        - 准时完成: 50分
        - 提前完成: >50分，上限100
        - 超时完成: <50分
        """
        if actual <= 0:
            return 100
        ratio = expected / actual
        # 0.5x速度 = 25分, 1x速度 = 50分, 2x速度 = 100分
        return min(100, ratio * 50)
        
    def _calc_quality(self, consume: dict) -> float:
        """
        计算质量分
        
        基于消耗比率：
        - 消耗低于预期: 高分
        - 消耗符合预期: 50分
        - 消耗高于预期: 低分
        """
        if not consume:
            return 75  # 无消耗数据，默认良好
            
        # 简化计算：假设预期消耗为consume中的值
        total_expected = sum(consume.values())
        
        # 实际消耗暂时用预期值，实际应用中应该比较start和end状态
        total_actual = total_expected
        
        if total_expected == 0:
            return 75
            
        ratio = total_actual / total_expected
        # ratio=1.0 -> 50分, ratio=0.5 -> 75分, ratio=2.0 -> 0分
        quality = max(0, min(100, (2.0 - ratio) * 50))
        return quality
        
    def _calc_stress_bonus(self, stress: float) -> float:
        """计算压力加成/惩罚"""
        thresholds = self.stress_rules.get("thresholds", [])
        
        for t in thresholds:
            if t["min"] <= stress <= t["max"]:
                return t["bonus"]
                
        return 0
        
    def _calc_mood_bonus(self, mood: float) -> float:
        """计算心情加成/惩罚"""
        thresholds = self.mood_rules.get("thresholds", [])
        
        for t in thresholds:
            if t["min"] <= mood <= t["max"]:
                return t["bonus"]
                
        return 0
        
    def _calc_skill_bonus(self, player_skills: dict, 
                          required: dict) -> float:
        """
        计算技能匹配加成
        
        规则：
        - 技能不足: -10 ~ 0
        - 技能刚好: 0
        - 技能略高: 0 ~ 5
        - 技能较高: 5 ~ 15
        - 技能远超: 15 ~ 25 (上限)
        """
        if not required:
            return 10  # 无要求，默认加分
            
        total_bonus = 0
        count = 0
        
        for skill, level in required.items():
            player_level = player_skills.get(skill, 0)
            diff = player_level - level
            
            if diff >= 0:
                # 技能满足或超过
                bonus = min(25, diff * 5)
            else:
                # 技能不足
                bonus = max(-10, diff * 5)
                
            total_bonus += bonus
            count += 1
            
        return total_bonus / count if count > 0 else 0
        
    def _calc_buff_bonus(self, buffs: list, company_id: str) -> float:
        """
        计算Buff加成
        
        同类型取最高值，不同类型可叠加
        范围: -20 ~ +30
        """
        if not buffs:
            return 0
            
        # 按类型收集最高值
        type_bonus: Dict[str, float] = {}
        
        for buff in buffs:
            buff_type = buff.get("type", "")
            value = buff.get("value", 0)
            
            # 检查是否适用于当前公司
            applicable = buff.get("applicable_jobs", [])
            if applicable and applicable != "all" and company_id not in applicable:
                continue
                
            # 同类型取最高
            if buff_type not in type_bonus or value > type_bonus[buff_type]:
                type_bonus[buff_type] = value
                
        # 累加不同类型的加成
        total = sum(type_bonus.values())
        
        # 限制范围
        return max(-20, min(30, total))
        
    def _calc_time_bonus(self, expected: float, actual: float) -> float:
        """计算提前完成的时间奖励（金币加成百分比）"""
        if actual <= 0 or expected <= 0:
            return 0
            
        ratio = expected / actual
        if ratio >= 1:
            # 提前完成: 最多+20%金币
            return min(20, (ratio - 1) * 100)
        return 0
        
    def _determine_grade(self, score: float) -> Tuple[str, str]:
        """根据分数确定等级和名称"""
        for grade, info in self.grades.items():
            if score >= info.get("min_score", 0):
                return grade, info.get("name", grade)
        return "F", "失败"
        
    def get_grade_info(self, grade: str) -> dict:
        """获取等级详细信息"""
        return self.grades.get(grade, {})
        
    def get_all_grades(self) -> List[dict]:
        """获取所有等级定义"""
        return [
            {"grade": g, **info}
            for g, info in self.grades.items()
        ]
        
    def format_evaluation_report(self, result: EvaluationResult) -> str:
        """生成评价报告文本"""
        lines = []
        
        # 标题
        lines.append("=" * 40)
        lines.append(f"    评 价 报 告")
        lines.append("=" * 40)
        
        # 总评
        grade_emoji = {
            "S": "🌟", "A": "✨", "B": "👍", 
            "C": "👌", "D": "😅", "F": "💀"
        }
        emoji = grade_emoji.get(result.grade, "❓")
        lines.append(f"\n  {emoji} 等级: {result.grade} ({result.grade_name})")
        lines.append(f"  📊 综合分: {result.final_score}")
        
        # 详细维度
        lines.append("\n─── 六维评价 ───")
        
        dim_data = [
            ("效率", result.efficiency, "%"),
            ("质量", result.quality, "%"),
            ("压力", result.stress, ""),
            ("心情", result.mood, ""),
            ("技能", result.skill_match, ""),
            ("Buff", result.buff, ""),
        ]
        
        for name, score, unit in dim_data:
            bar_len = int(score.percentage / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            bonus_str = f"+{score.bonus}" if score.bonus >= 0 else str(score.bonus)
            lines.append(
                f"  {name:4s}: [{bar}] {score.value:5.1f}{unit} "
                f"(加权{xscore.weight:.0%}, 加成{bonus_str})"
            )
            
        # 时间信息
        lines.append("\n─── 时间效率 ───")
        if result.actual_hours < result.expected_hours:
            saved = result.expected_hours - result.actual_hours
            lines.append(f"  ⏰ 提前 {saved:.1f} 小时完成")
        elif result.actual_hours > result.expected_hours:
            over = result.actual_hours - result.expected_hours
            lines.append(f"  ⏰ 超时 {over:.1f} 小时")
        else:
            lines.append(f"  ⏰ 准时完成")
            
        # 奖励信息
        lines.append("\n─── 获得奖励 ───")
        lines.append(f"  💰 金币: {result.final_reward}")
        if result.bonus_gold > 0:
            lines.append(f"     (含评价奖励 +{result.bonus_gold})")
            
        if result.exp_gained:
            exp_str = ", ".join([f"{k}+{v}" for k, v in result.exp_gained.items()])
            lines.append(f"  📈 经验: {exp_str}")
            
        if result.favor_change != 0:
            lines.append(f"  ❤️ 好感: {result.favor_change:+d}")
            
        lines.append("=" * 40)
        
        return "\n".join(lines)
        
    def explain_score(self, score: EvaluationScore) -> str:
        """解释单个维度的评分"""
        explanations = {
            "效率": self._explain_efficiency,
            "质量": self._explain_quality,
            "压力": self._explain_stress,
            "心情": self._explain_mood,
            "技能匹配": self._explain_skill,
            "Buff加成": self._explain_buff,
        }
        
        explain_fn = explanations.get(score.dimension, lambda s: "无解释")
        return explain_fn(score)
        
    def _explain_efficiency(self, score: EvaluationScore) -> str:
        base = score.value
        if base >= 90:
            return "效率极高，超额完成任务！"
        elif base >= 70:
            return "效率良好，比预期更快完成"
        elif base >= 50:
            return "效率正常，按时完成"
        elif base >= 30:
            return "效率较低，消耗了较多时间"
        else:
            return "效率很低，严重超时"
            
    def _explain_quality(self, score: EvaluationScore) -> str:
        base = score.value
        if base >= 80:
            return "质量优秀，资源利用极佳"
        elif base >= 60:
            return "质量良好，消耗合理"
        elif base >= 40:
            return "质量一般，消耗正常"
        else:
            return "质量较差，消耗过高"
            
    def _explain_stress(self, score: EvaluationScore) -> str:
        bonus = score.bonus
        if bonus >= 5:
            return "压力适中，状态良好"
        elif bonus >= 0:
            return "压力正常，保持专注"
        elif bonus >= -10:
            return "压力较大，影响表现"
        else:
            return "压力极大，严重影响效率"
            
    def _explain_mood(self, score: EvaluationScore) -> str:
        bonus = score.bonus
        if bonus >= 8:
            return "心情极佳，效率大幅提升"
        elif bonus >= 3:
            return "心情不错，干劲十足"
        elif bonus >= 0:
            return "心情一般"
        elif bonus >= -5:
            return "心情不佳，有些沮丧"
        else:
            return "心情很差，状态低迷"
            
    def _explain_skill(self, score: EvaluationScore) -> str:
        bonus = score.bonus
        if bonus >= 20:
            return "技能远超要求，游刃有余"
        elif bonus >= 10:
            return "技能充足，完成顺利"
        elif bonus >= 5:
            return "技能略高，轻松应对"
        elif bonus >= 0:
            return "技能刚好满足"
        elif bonus >= -5:
            return "技能略有不足"
        else:
            return "技能严重不足"
            
    def _explain_buff(self, score: EvaluationScore) -> str:
        bonus = score.bonus
        if bonus >= 20:
            return "强力Buff加持，表现大幅提升"
        elif bonus >= 10:
            return "有Buff加成，效果不错"
        elif bonus >= 0:
            return "有少量Buff加成"
        elif bonus >= -10:
            return "受到一些负面影响"
        else:
            return "负面效果明显"


# 全局实例
_evaluator = None

def get_evaluator(config_dir: str = None) -> EvaluationV3:
    """获取评价器单例"""
    global _evaluator
    if _evaluator is None:
        _evaluator = EvaluationV3(config_dir)
    return _evaluator


if __name__ == "__main__":
    # 测试代码
    evaluator = EvaluationV3()
    
    # 模拟数据
    user_data = {
        "skills": {"编程": 3, "数学": 2},
        "mood": 75,
        "pressure_mind": 35,
        "active_buffs": [
            {"type": "evaluation_bonus", "value": 5, "applicable_jobs": "all"},
            {"type": "income_bonus", "value": 10, "applicable_jobs": ["company_tech"]},
        ]
    }
    
    job_data = {
        "duration_hours": 3,
        "difficulty": "B",
        "base_reward": 500,
        "consume": {"energy": 30, "strength": 20},
        "skill_required": {"编程": 2, "数学": 1},
        "exp_reward": {"编程": 15, "数学": 10},
        "company_id": "company_tech",
    }
    
    # 模拟2小时完成（提前完成）
    result = evaluator.evaluate(user_data, job_data, actual_hours=2.0)
    
    print(evaluator.format_evaluation_report(result))
    
    print("\n\n各维度详细说明：")
    for score in [result.efficiency, result.quality, result.stress, 
                  result.mood, result.skill_match, result.buff]:
        print(f"  {score.dimension}: {evaluator.explain_score(score)}")
