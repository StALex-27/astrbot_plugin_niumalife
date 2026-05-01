"""
打工系统 V2 - 核心业务逻辑模块
重构后的工作委托系统，包含完整的委托生命周期管理
"""

import json
import random
import uuid
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

from .job_pool_generator import JobPoolGenerator, get_generator
from .company_favorability import CompanyFavorability, get_favorability_manager


@dataclass
class Job:
    """委托数据结构"""
    job_id: str
    company_id: str
    template_id: str
    title: str
    description: str
    difficulty: str
    duration_hours: int
    base_reward: int
    skill_required: Dict[str, int] = field(default_factory=dict)
    consume: Dict[str, int] = field(default_factory=dict)
    exp_reward: Dict[str, int] = field(default_factory=dict)
    favorability_gain: int = 10
    difficulty_reward_multiplier: float = 1.0
    is_public: bool = True
    is_hidden: bool = False
    created_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        return cls(**data)


class JobManager:
    """
    打工系统 V2 核心管理器
    负责委托的生成、接受、完成、评价全生命周期
    """
    
    # 状态常量
    STATUS_AVAILABLE = "available"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    
    # 难度等级顺序
    DIFFICULTY_ORDER = ["D", "C", "B", "A", "S", "S+"]
    
    def __init__(self, config_dir: str = None, data_dir: str = None):
        """
        初始化打工系统管理器
        
        Args:
            config_dir: 配置文件目录
            data_dir: 数据存储目录
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "data" / "config"
        self.config_dir = Path(config_dir)
        
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        
        # 初始化子模块
        self.pool_generator = JobPoolGenerator(config_dir)
        self.favor_manager = CompanyFavorability(config_dir)
        
        # 加载配置
        self._load_configs()
        
    def _load_configs(self):
        """加载配置文件"""
        # 加载评价规则
        with open(self.config_dir / "evaluation_rules.json", "r", encoding="utf-8") as f:
            eval_data = json.load(f)
            self.eval_grades = eval_data.get("evaluation_grades", {})
            self.eval_weights = eval_data.get("weight_config", {})
            self.stress_rules = eval_data.get("stress_rules", {})
            self.mood_rules = eval_data.get("mood_rules", {})
            self.skill_rules = eval_data.get("skill_match_rules", {})
            self.buff_rules = eval_data.get("buff_rules", {})
            self.difficulty_config = eval_data.get("difficulty_config", {})
            
    # ==================== 委托池管理 ====================
    
    def generate_job_pool(self, user_data: dict, count: int = 8) -> List[Job]:
        """
        为玩家生成可接取的委托池
        
        Args:
            user_data: 玩家数据
            count: 生成数量，默认8个
            
        Returns:
            Job对象列表
        """
        job_dicts = self.pool_generator.generate_pool(user_data, count)
        return [Job.from_dict(j) for j in job_dicts]
        
    def get_company_jobs(self, user_data: dict, company_id: str, 
                         max_per_company: int = 2) -> List[Job]:
        """
        获取特定公司的推荐委托
        
        Args:
            user_data: 玩家数据
            company_id: 公司ID
            max_per_company: 最大数量
            
        Returns:
            Job对象列表
        """
        job_dicts = self.pool_generator.get_company_recommended_jobs(
            user_data, max_per_company
        ).get(company_id, [])
        return [Job.from_dict(j) for j in job_dicts]
        
    def get_player_current_jobs(self, user_data: dict) -> List[dict]:
        """
        获取玩家当前进行中的委托
        
        Args:
            user_data: 玩家数据
            
        Returns:
            进行中的委托列表
        """
        return user_data.get("jobs_in_progress", [])
        
    def get_company_info(self, company_id: str) -> Optional[dict]:
        """获取公司信息"""
        return self.pool_generator.companies.get(company_id)
        
    # ==================== 委托生命周期 ====================
    
    def accept_job(self, user_data: dict, job_data: dict) -> Tuple[bool, str]:
        """
        接受委托
        
        Args:
            user_data: 玩家数据（会被修改）
            job_data: 委托数据
            
        Returns:
            (是否成功, 消息)
        """
        # 检查是否已有进行中的委托
        in_progress = self.get_player_current_jobs(user_data)
        if len(in_progress) >= 3:
            return False, "进行中的委托已达上限（3个），请先完成或取消现有委托"
            
        # 检查属性是否足够
        job = Job.from_dict(job_data) if isinstance(job_data, dict) else job_data
        can_start, reason = self._check_job_requirements(user_data, job)
        if not can_start:
            return False, reason
            
        # 添加到进行中列表
        job_entry = {
            **job.to_dict(),
            "status": self.STATUS_IN_PROGRESS,
            "accepted_at": datetime.now().isoformat(),
            "expected_complete_at": (
                datetime.now() + timedelta(hours=job.duration_hours)
            ).isoformat(),
            "started_attributes": {
                "health": user_data.get("health", 100),
                "strength": user_data.get("strength", 100),
                "energy": user_data.get("energy", 100),
                "mood": user_data.get("mood", 100),
                "satiety": user_data.get("satiety", 100),
            }
        }
        
        if "jobs_in_progress" not in user_data:
            user_data["jobs_in_progress"] = []
        user_data["jobs_in_progress"].append(job_entry)
        
        return True, f"已接受委托：{job.title}"
        
    def _check_job_requirements(self, user_data: dict, job: Job) -> Tuple[bool, str]:
        """检查是否满足委托的要求"""
        # 检查属性
        attrs = {
            "health": user_data.get("health", 100),
            "strength": user_data.get("strength", 100),
            "energy": user_data.get("energy", 100),
            "mood": user_data.get("mood", 100),
            "satiety": user_data.get("satiety", 100),
        }
        
        # 简单检查：至少要有一定的属性
        for attr, value in attrs.items():
            if value < 20:
                return False, f"属性 {attr} 过低，无法开始工作"
                
        # 检查技能
        skills = user_data.get("skills", {})
        for skill, level in job.skill_required.items():
            if skills.get(skill, 0) < level:
                return False, f"技能不足：需要 {skill} Lv.{level}"
                
        # 检查好感度
        favor = user_data.get("company_favorability", {}).get(job.company_id, 0)
        if not self.favor_manager.can_accept_difficulty(favor, job.difficulty):
            avail_diffs = self.favor_manager.get_available_difficulties(favor)
            return False, f"好感度不足，当前可接难度：{', '.join(avail_diffs) if avail_diffs else '无'}"
            
        return True, "满足要求"
        
    def complete_job(self, user_data: dict, job_id: str, 
                     actual_hours: float = None) -> Tuple[bool, str, dict]:
        """
        完成委托，进入评价流程
        
        Args:
            user_data: 玩家数据
            job_id: 委托ID
            actual_hours: 实际用时（小时），不指定则按预期计算
            
        Returns:
            (是否成功, 消息, 评价结果)
        """
        # 找到进行中的委托
        in_progress = user_data.get("jobs_in_progress", [])
        job_entry = None
        job_index = None
        
        for i, j in enumerate(in_progress):
            if j.get("job_id") == job_id:
                job_entry = j
                job_index = i
                break
                
        if job_entry is None:
            return False, "未找到进行中的委托", {}
            
        # 计算实际用时
        job = Job.from_dict(job_entry)
        if actual_hours is None:
            # 从已接受时间计算
            accepted = datetime.fromisoformat(job_entry["accepted_at"])
            actual_hours = (datetime.now() - accepted).total_seconds() / 3600
            
        # 计算六维评价
        eval_result = self._calculate_evaluation(user_data, job, actual_hours)
        
        # 应用奖励和消耗
        reward_info = self._apply_job_result(user_data, job, eval_result)
        
        # 从进行中移除
        user_data["jobs_in_progress"].pop(job_index)
        
        # 更新历史
        if "job_history" not in user_data:
            user_data["job_history"] = []
        user_data["job_history"].append({
            **job_entry,
            "status": self.STATUS_COMPLETED,
            "completed_at": datetime.now().isoformat(),
            "actual_hours": actual_hours,
            "evaluation": eval_result,
        })
        
        # 限制历史记录数量
        if len(user_data["job_history"]) > 50:
            user_data["job_history"] = user_data["job_history"][-50:]
            
        return True, f"委托完成！评价：{eval_result['grade']}", {
            "evaluation": eval_result,
            "rewards": reward_info
        }
        
    def fail_job(self, user_data: dict, job_id: str, 
                 reason: str = "主动放弃") -> Tuple[bool, str]:
        """
        委托失败
        
        Args:
            user_data: 玩家数据
            job_id: 委托ID
            reason: 失败原因
            
        Returns:
            (是否成功, 消息)
        """
        in_progress = user_data.get("jobs_in_progress", [])
        job_entry = None
        job_index = None
        
        for i, j in enumerate(in_progress):
            if j.get("job_id") == job_id:
                job_entry = j
                job_index = i
                break
                
        if job_entry is None:
            return False, "未找到进行中的委托"
            
        # 触发好感度惩罚
        company_id = job_entry["company_id"]
        favor_change = self.favor_manager.on_job_fail(user_data, company_id)
        
        # 从进行中移除
        user_data["jobs_in_progress"].pop(job_index)
        
        # 记录历史
        if "job_history" not in user_data:
            user_data["job_history"] = []
        user_data["job_history"].append({
            **job_entry,
            "status": self.STATUS_FAILED,
            "failed_at": datetime.now().isoformat(),
            "fail_reason": reason,
            "favor_change": favor_change,
        })
        
        return True, f"委托失败，好感度 {favor_change:+d}"
        
    def cancel_job(self, user_data: dict, job_id: str) -> Tuple[bool, str]:
        """
        取消委托
        
        Args:
            user_data: 玩家数据
            job_id: 委托ID
            
        Returns:
            (是否成功, 消息)
        """
        in_progress = user_data.get("jobs_in_progress", [])
        job_entry = None
        job_index = None
        
        for i, j in enumerate(in_progress):
            if j.get("job_id") == job_id:
                job_entry = j
                job_index = i
                break
                
        if job_entry is None:
            return False, "未找到进行中的委托"
            
        # 触发好感度惩罚
        company_id = job_entry["company_id"]
        favor_change = self.favor_manager.on_job_cancel(user_data, company_id)
        
        # 从进行中移除
        user_data["jobs_in_progress"].pop(job_index)
        
        return True, f"已取消委托，好感度 {favor_change:+d}"
        
    # ==================== 评价系统 ====================
    
    def _calculate_evaluation(self, user_data: dict, job: Job, 
                             actual_hours: float) -> dict:
        """
        计算六维评价
        
        Args:
            user_data: 玩家数据
            job: 委托对象
            actual_hours: 实际用时
            
        Returns:
            评价结果dict
        """
        # 获取各维度数据
        efficiency = self._calc_efficiency(job.duration_hours, actual_hours)
        quality = self._calc_quality(user_data, job)
        stress_bonus = self._calc_stress_bonus(user_data)
        mood_bonus = self._calc_mood_bonus(user_data)
        skill_bonus = self._calc_skill_bonus(user_data, job)
        buff_bonus = self._calc_buff_bonus(user_data, job)
        
        # 加权计算总分
        weights = self.eval_weights
        raw_score = (
            efficiency * weights.get("efficiency", {}).get("weight", 0.20) +
            quality * weights.get("quality", {}).get("weight", 0.15) +
            (50 + stress_bonus) * weights.get("stress", {}).get("weight", 0.10) +
            (50 + mood_bonus) * weights.get("mood", {}).get("weight", 0.10) +
            (50 + skill_bonus) * weights.get("skill_match", {}).get("weight", 0.25) +
            (50 + buff_bonus) * weights.get("buff", {}).get("weight", 0.20)
        )
        
        # 确保范围
        final_score = max(0, min(100, raw_score))
        
        # 确定等级
        grade = self._determine_grade(final_score)
        
        return {
            "score": round(final_score, 1),
            "grade": grade,
            "efficiency": efficiency,
            "quality": quality,
            "stress_bonus": stress_bonus,
            "mood_bonus": mood_bonus,
            "skill_bonus": skill_bonus,
            "buff_bonus": buff_bonus,
        }
        
    def _calc_efficiency(self, expected_hours: float, actual_hours: float) -> float:
        """计算效率分：预定时间/实际时间，上限100"""
        if actual_hours <= 0:
            return 100
        ratio = expected_hours / actual_hours
        return min(100, ratio * 50 + 50)  # 提前完成加分，超时扣分
        
    def _calc_quality(self, user_data: dict, job: Job) -> float:
        """计算质量分：基于消耗比率"""
        # 获取实际消耗（从job的consume模板）
        job_consume = job.consume
        
        # 模拟预期消耗（简化计算）
        total_expected = sum(job_consume.values())
        
        # 从用户数据获取实际消耗（这里用开始和当前属性的差异）
        started = user_data.get("_last_job_start_attrs", {})
        if not started:
            return 50  # 无法计算，默认50
            
        # 简化：假设按job模板消耗
        actual_consume = total_expected
        
        # 质量 = 消耗越少越好
        if total_expected == 0:
            return 75
        ratio = actual_consume / total_expected
        quality = max(0, min(100, (2.0 - ratio) * 50))
        return quality
        
    def _calc_stress_bonus(self, user_data: dict) -> float:
        """计算压力加成"""
        stress = user_data.get("pressure_mind", 0)
        thresholds = self.stress_rules.get("thresholds", [])
        
        for t in thresholds:
            if t["min"] <= stress <= t["max"]:
                return t["bonus"]
        return 0
        
    def _calc_mood_bonus(self, user_data: dict) -> float:
        """计算心情加成"""
        mood = user_data.get("mood", 50)
        thresholds = self.mood_rules.get("thresholds", [])
        
        for t in thresholds:
            if t["min"] <= mood <= t["max"]:
                return t["bonus"]
        return 0
        
    def _calc_skill_bonus(self, user_data: dict, job: Job) -> float:
        """计算技能匹配加成"""
        skills = user_data.get("skills", {})
        required = job.skill_required
        
        if not required:
            return 10  # 无要求，默认加分
            
        total_bonus = 0
        count = 0
        
        for skill, level in required.items():
            player_level = skills.get(skill, 0)
            diff = player_level - level
            
            if diff >= 0:
                bonus = min(25, diff * 5)
            else:
                bonus = max(-10, diff * 5)
            total_bonus += bonus
            count += 1
            
        return total_bonus / count if count > 0 else 0
        
    def _calc_buff_bonus(self, user_data: dict, job: Job) -> float:
        """计算Buff加成"""
        # 获取玩家当前buff列表
        buffs = user_data.get("active_buffs", [])
        if not buffs:
            return 0
            
        total_bonus = 0
        applicable_types = ["evaluation_bonus", "reward_bonus", "income_bonus"]
        
        for buff in buffs:
            buff_type = buff.get("type", "")
            if buff_type in applicable_types:
                value = buff.get("value", 0)
                # 检查是否适用于当前公司
                applicable = buff.get("applicable_jobs", [])
                if applicable == "all" or job.company_id in applicable:
                    total_bonus += value
                    
        return max(-20, min(30, total_bonus))
        
    def _determine_grade(self, score: float) -> str:
        """根据分数确定等级"""
        for grade in ["S", "A", "B", "C", "D", "F"]:
            grade_info = self.eval_grades.get(grade, {})
            if score >= grade_info.get("min_score", 0):
                return grade
        return "F"
        
    # ==================== 奖励计算 ====================
    
    def _apply_job_result(self, user_data: dict, job: Job, 
                          eval_result: dict) -> dict:
        """
        应用工作结果：计算奖励、应用消耗
        """
        # 获取评价等级对应的奖励倍率
        grade = eval_result["grade"]
        grade_info = self.eval_grades.get(grade, {})
        reward_mult = grade_info.get("reward_multiplier", 1.0)
        
        # 基础奖励 * 难度倍率 * 评价倍率
        base = job.base_reward
        diff_mult = job.difficulty_reward_multiplier
        
        # 累加各类加成
        total_bonus = 1.0
        # (未来可以从buff、装备等来源累加)
        
        final_reward = int(base * diff_mult * total_bonus * reward_mult)
        
        # 应用奖励
        user_data["gold"] = user_data.get("gold", 0) + final_reward
        
        # 给予经验
        for skill, exp in job.exp_reward.items():
            if "skills_exp" not in user_data:
                user_data["skills_exp"] = {}
            user_data["skills_exp"][skill] = user_data["skills_exp"].get(skill, 0) + exp
            
        # 触发好感度变化
        favor_change = self.favor_manager.on_job_complete(
            user_data, job.company_id, job.difficulty, grade
        )
        
        # 应用消耗
        consume_mult = self.difficulty_config.get("consume_multiplier", {}).get(
            job.difficulty, 1.0
        )
        for attr, value in job.consume.items():
            user_data[attr] = max(0, user_data.get(attr, 100) - int(value * consume_mult))
            
        return {
            "gold": final_reward,
            "exp": job.exp_reward,
            "favor_change": favor_change,
            "consume": {k: int(v * consume_mult) for k, v in job.consume.items()},
        }
        
    # ==================== 辅助方法 ====================
    
    def get_job_display_info(self, job: Job) -> str:
        """获取委托的显示信息"""
        company = self.get_company_info(job.company_id)
        company_name = company.get("name", job.company_id) if company else job.company_id
        company_emoji = company.get("emoji", "") if company else ""
        
        info = f"""
{company_emoji} {company_name}
「{job.title}」
难度: {job.difficulty} | 预计: {job.duration_hours}小时
奖励: {job.base_reward} 金币
"""
        if job.skill_required:
            skill_str = ", ".join([f"{s}Lv.{l}" for s, l in job.skill_required.items()])
            info += f"技能: {skill_str}\n"
            
        if job.consume:
            consume_str = ", ".join([f"{s}-{v}" for s, v in job.consume.items()])
            info += f"消耗: {consume_str}\n"
            
        return info.strip()
        
    def format_job_status(self, user_data: dict) -> str:
        """格式化玩家当前打工状态"""
        in_progress = self.get_player_current_jobs(user_data)
        
        if not in_progress:
            return "当前没有进行中的委托"
            
        lines = ["进行中的委托："]
        for i, job in enumerate(in_progress, 1):
            accepted = datetime.fromisoformat(job["accepted_at"])
            expected = datetime.fromisoformat(job["expected_complete_at"])
            remaining = (expected - datetime.now()).total_seconds() / 3600
            
            lines.append(
                f"{i}. {job['title']} ({job['difficulty']}) - "
                f"预计剩余 {max(0, remaining):.1f} 小时"
            )
            
        return "\n".join(lines)
        
    def check_overdue_jobs(self, user_data: dict) -> List[dict]:
        """
        检查超时委托
        超时24小时仍未完成则自动失败
        """
        in_progress = user_data.get("jobs_in_progress", [])
        overdue = []
        
        for job in in_progress:
            expected = datetime.fromisoformat(job["expected_complete_at"])
            hours_overdue = (datetime.now() - expected).total_seconds() / 3600
            
            if hours_overdue >= 24:
                overdue.append({**job, "hours_overdue": hours_overdue})
                
        return overdue
        
    def process_overdue_jobs(self, user_data: dict) -> int:
        """
        处理超时委托
        返回处理数量
        """
        overdue = self.check_overdue_jobs(user_data)
        count = 0
        
        for job in overdue:
            self.fail_job(user_data, job["job_id"], "委托超时")
            count += 1
            
        return count


# 全局管理器实例
_manager = None

def get_job_manager(config_dir: str = None, data_dir: str = None) -> JobManager:
    """获取JobManager单例"""
    global _manager
    if _manager is None:
        _manager = JobManager(config_dir, data_dir)
    return _manager


if __name__ == "__main__":
    # 测试代码
    manager = JobManager()
    
    test_user = {
        "level": 5,
        "gold": 1000,
        "health": 80,
        "strength": 75,
        "energy": 70,
        "mood": 60,
        "satiety": 50,
        "pressure_mind": 30,
        "skills": {"编程": 3, "数学": 2, "计算机基础": 2},
        "company_favorability": {
            "company_tech": 250,
            "company_labor": 50,
            "company_business": 100
        }
    }
    
    print("=== 生成委托池 ===")
    pool = manager.generate_job_pool(test_user, count=5)
    for job in pool:
        print(f"\n{manager.get_job_display_info(job)}")
