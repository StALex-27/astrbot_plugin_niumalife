"""
Tick结算系统模块 v2
统一处理工作/睡眠/学习/娱乐等状态的定时结算
基于 tick (分钟) 精度，支持时间触发器

主要改动:
- 使用 tick (分钟) 而非 hour (小时) 作为结算单位
- 新增统一时间触发系统 (每小时/每日/Cron)
- 支持停机恢复和精确计时
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import asyncio
import math

from astrbot.api import logger
from astrbot.api.star import StarTools
from astrbot.core.message.message_event_result import MessageChain

from .constants import (
    TICKS_PER_HOUR, COURSES, JOBS, JOB_PRESSURE_TYPE, JOB_PRESSURE_RATE,
    get_pressure_penalty, RESIDENCES, MAX_ATTRIBUTE, ENTERTAINMENTS,
    ENTERTAINMENT_PRESSURE_RELIEF,
)
from .item import calc_equipped_effects
from .user import UserStatus, update_daily_stat, update_lifetime_stat
from .buff import (
    calc_income_multi, calc_cost_multi, calc_exp_multi, get_fixed_bonus,
    BuffManager, BuffLimit,
)
from .debuff import calc_debuff_income_penalty, accumulate_pressure, is_exhausted
from .skills import get_skill_level, get_user_skill_level, get_skill_exp_rate, check_course_available, exp_to_next_level
from .stock import STOCKS, update_stock_price, is_trading_hour, init_stock_trend


# ============================================================
# 常量
# ============================================================

TICK_TYPE_WORK = "工作"
TICK_TYPE_LEARN = "学习"
TICK_TYPE_ENTERTAIN = "娱乐"
TICK_TYPE_FISHING = "钓鱼"


# ============================================================
# 时间触发器状态键
# ============================================================

TICK_STATE_KEY = "__tick_state__"


# ============================================================
# ActionDetail - 基于 Tick 的动作详情
# ============================================================

class ActionDetail:
    """统一的ActionDetail结构 - 基于 Tick"""
    
    @staticmethod
    def create(
        action_type: str,
        hours: int,
        start_time: datetime,
        **kwargs
    ) -> dict:
        """创建ActionDetail
        
        Args:
            action_type: 动作类型 (TICK_TYPE_WORK等)
            hours: 计划时长（小时）
            start_time: 开始时间
            **kwargs: 额外参数
        
        Returns:
            dict: 动作详情字典
        """
        planned_ticks = hours * TICKS_PER_HOUR
        detail = {
            "action_type": action_type,
            "start_time": start_time.isoformat(),
            "planned_ticks": planned_ticks,
            "completed_ticks": 0,
            "last_tick": start_time.isoformat(),  # 上次结算时间
            "last_hourly_settle": None,  # 上次整点结算时间（格式：HH:MM）
            "earned_gold": 0,  # 已获得金币（累计）
            "earned_exp": 0,   # 已获得经验（累计）
            "data": kwargs,
        }
        return detail
    
    @staticmethod
    def get_elapsed_seconds(detail: dict, now: datetime) -> float:
        """获取自开始以来的总秒数"""
        start = datetime.fromisoformat(detail["start_time"])
        if start.tzinfo is None:
            pass  # start_time 存的是本地时间
        if now.tzinfo is None:
            pass  # now 已是本地时间，不做 UTC 转换
        return (now - start).total_seconds()
    
    @staticmethod
    def get_elapsed_ticks(detail: dict, now: datetime) -> int:
        """获取自开始以来的总 tick 数"""
        seconds = ActionDetail.get_elapsed_seconds(detail, now)
        return int(seconds // 60)
    
    @staticmethod
    def get_ticks_since_last_tick(detail: dict, now: datetime) -> float:
        """获取自上次tick以来的精确 tick 数（可有小数）"""
        last_tick = datetime.fromisoformat(detail.get("last_tick", detail["start_time"]))
        if last_tick.tzinfo is None:
            pass  # last_tick 存的是本地时间
        if now.tzinfo is None:
            pass  # now 已是本地时间，不做 UTC 转换
        return (now - last_tick).total_seconds() / 60.0
    
    @staticmethod
    def is_expired(detail: dict, now: datetime) -> bool:
        """检查是否已过期（完成）"""
        elapsed = ActionDetail.get_elapsed_ticks(detail, now)
        return elapsed >= detail["planned_ticks"]
    
    @staticmethod
    def update_tick(detail: dict, now: datetime):
        """更新结算时间"""
        detail["last_tick"] = now.isoformat()


# ============================================================
# TickProcessor 基类
# ============================================================

class TickProcessor:
    """Tick处理器基类"""
    
    def __init__(self, plugin):
        self.plugin = plugin
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """
        处理一个 tick
        返回 True 表示动作完成，False 表示继续
        
        Args:
            user_id: 用户ID
            user: 用户数据
            detail: 动作详情
            now: 当前时间
        
        Returns:
            bool: 是否完成
        """
        raise NotImplementedError
    
    def get_action_type(self) -> str:
        raise NotImplementedError


# ============================================================
# WorkTickProcessor - 工作处理器
# ============================================================

class WorkTickProcessor(TickProcessor):
    """工作Tick处理器 - 整点结算属性版本"""
    
    def get_action_type(self) -> str:
        return TICK_TYPE_WORK
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理工作tick - 整点结算属性
        
        Args:
            user_id: 用户ID
            user: 用户数据
            detail: 动作详情
            now: 当前时间
        
        Returns:
            bool: 是否完成
        """
        
        action_type = detail.get("action_type")
        if action_type != TICK_TYPE_WORK:
            return False
        
        # 获取工作数据
        data = detail.get("data", {})
        job_name = data.get("job_name")
        job_company = data.get("job_company")
        base_reward = data.get("base_reward", 0)
        planned = detail["planned_ticks"]
        
        # 尝试从 JOBS 获取消耗配置（如果能匹配到）
        job = JOBS.get(job_name) if job_name else None
        if job:
            consume_strength = job.get("consume_strength", 10)
            consume_energy = job.get("consume_energy", 10)
            consume_mood = job.get("consume_mood", 5)
            consume_health = job.get("consume_health", 2)
            consume_satiety = job.get("consume_satiety", 10)
            hourly_wage = job.get("hourly_wage", base_reward / (planned / 60) if planned > 0 else base_reward)
            pressure_type = JOB_PRESSURE_TYPE.get(job_name, "body")
            pressure_rate = JOB_PRESSURE_RATE.get(job_name, 3)
        else:
            # 新系统：使用默认消耗或从 company 配置获取
            consume_strength = 10
            consume_energy = 10
            consume_mood = 5
            consume_health = 2
            consume_satiety = 10
            # 根据总奖励和工期计算时薪
            hours = planned / 60 if planned > 0 else 1
            hourly_wage = base_reward / hours if hours > 0 else base_reward
            pressure_type = "mind"  # 默认脑力
            pressure_rate = 5  # 默认压力积累
            job_name = data.get("job_name", "工作")
        
        # 检查是否力竭
        if is_exhausted(user, pressure_type):
            # 力竭状态，直接取消工作，同时清理 jobs_in_progress
            job_id = data.get("job_id") or job_name
            jobs_in_progress = user.get("jobs_in_progress", [])
            for i, j in enumerate(jobs_in_progress):
                if j.get("job_id") == job_id or j.get("title") == job_name:
                    jobs_in_progress.pop(i)
                    break
            user["jobs_in_progress"] = jobs_in_progress
            return True
        
        # ========== 整点结算属性 ==========
        # 检查是否到达整点，且尚未结算
        if now.minute == 0:
            current_hour_str = f"{now.hour:02d}:00"
            last_settle = detail.get("last_hourly_settle")
            
            if last_settle != current_hour_str:
                # 执行整点结算
                await self._settle_hourly(
                    user, user_id, detail, 
                    consume_strength, consume_energy, consume_mood, consume_health, consume_satiety,
                    hourly_wage, pressure_type, pressure_rate, now
                )
                detail["last_hourly_settle"] = current_hour_str
        
        # ========== 检查工作是否完成（每分钟检查）==========
        # 计算实际经过的时间
        elapsed_seconds = ActionDetail.get_elapsed_seconds(detail, now)
        elapsed_ticks = int(elapsed_seconds // 60)
        
        if elapsed_ticks >= planned:
            # 工作完成，执行最终结算
            return await self._complete_work(
                user, user_id, detail,
                consume_strength, consume_energy, consume_mood, consume_health, consume_satiety,
                hourly_wage, pressure_type, pressure_rate, now
            )
        
        # 更新进度（但不结算属性）
        detail["completed_ticks"] = elapsed_ticks
        detail["last_tick"] = now.isoformat()
        user["action_detail"] = detail
        await self.plugin._store.update_user(user_id, user)
        
        return False
    
    async def _settle_hourly(
        self, user: dict, user_id: str, detail: dict,
        consume_strength: float, consume_energy: float, consume_mood: float,
        consume_health: float, consume_satiety: float,
        hourly_wage: float, pressure_type: str, pressure_rate: float, now: datetime
    ):
        """执行整点结算
        
        Args:
            user: 用户数据
            user_id: 用户ID
            detail: 动作详情
            consume_strength: 体力消耗（每小时）
            consume_energy: 精力消耗（每小时）
            consume_mood: 心情消耗（每小时）
            consume_health: 健康消耗（每小时）
            consume_satiety: 饱食消耗（每小时）
            hourly_wage: 时薪
            pressure_type: 压力类型
            pressure_rate: 压力积累率（每小时）
            now: 当前时间
        """
        last_tick_str = detail.get("last_tick", detail["start_time"])
        last_tick = datetime.fromisoformat(last_tick_str)
        if last_tick.tzinfo is None:
            pass  # last_tick 存的是本地时间
        if now.tzinfo is None:
            pass  # now 已是本地时间，不做 UTC 转换
        
        # 计算距离上次结算的小时数
        hours_since_last = (now - last_tick).total_seconds() / 3600.0
        
        if hours_since_last <= 0:
            return  # 避免重复结算
        
        # 获取装备效果和buff
        effects = calc_equipped_effects(user)
        work_income_bonus = effects.get("work_income_bonus", 0) / 100.0
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        income_multi = calc_income_multi(active_buffs)
        cost_multi = calc_cost_multi(active_buffs)
        fixed_bonus = get_fixed_bonus(active_buffs)
        debuff_penalty = calc_debuff_income_penalty(user)
        
        # 获取当前压力惩罚
        pressure = user.get(f"{pressure_type}_pressure", 0)
        pressure_penalty = 1.0 - get_pressure_penalty(pressure)
        
        attrs = user["attributes"]
        
        # 计算效率
        efficiency = pressure_penalty * debuff_penalty
        if attrs["satiety"] < 20:
            efficiency *= 0.7
        
        # 结算属性消耗
        attrs["strength"] = max(0, attrs["strength"] - consume_strength * hours_since_last * cost_multi)
        attrs["energy"] = max(0, attrs["energy"] - consume_energy * hours_since_last * cost_multi)
        attrs["mood"] = max(0, attrs["mood"] - consume_mood * hours_since_last)
        attrs["health"] = max(0, attrs["health"] - consume_health * hours_since_last)
        attrs["satiety"] = max(0, attrs["satiety"] - consume_satiety * 0.5 * hours_since_last)
        
        # 累积压力
        accumulate_pressure(user, pressure_type, pressure_rate * hours_since_last)
        
        # 更新状态
        user["attributes"] = attrs
        detail["last_tick"] = now.isoformat()
        user["action_detail"] = detail
        await self.plugin._store.update_user(user_id, user)
        
        self.plugin.logger.info(
            f"整点结算: {user['nickname']} 工作 {job_name} "
            f"结算 {hours_since_last:.2f} 小时"
        )
    
    async def _complete_work(
        self, user: dict, user_id: str, detail: dict,
        consume_strength: float, consume_energy: float, consume_mood: float,
        consume_health: float, consume_satiety: float,
        hourly_wage: float, pressure_type: str, pressure_rate: float, now: datetime
    ) -> bool:
        """完成工作，执行最终结算
        
        Args:
            user: 用户数据
            user_id: 用户ID
            detail: 动作详情
            consume_strength: 体力消耗（每小时）
            consume_energy: 精力消耗（每小时）
            consume_mood: 心情消耗（每小时）
            consume_health: 健康消耗（每小时）
            consume_satiety: 饱食消耗（每小时）
            hourly_wage: 时薪
            pressure_type: 压力类型
            pressure_rate: 压力积累率（每小时）
            now: 当前时间
        
        Returns:
            bool: 始终返回 True
        """
        data = detail.get("data", {})
        job_name = data.get("job_name", "工作")
        planned = detail["planned_ticks"]
        hours = planned / TICKS_PER_HOUR  # 计划总时长（小时）
        
        # 如果上次结算后还有剩余时间，先结算剩余属性（不含金币）
        last_tick_str = detail.get("last_tick", detail["start_time"])
        last_tick = datetime.fromisoformat(last_tick_str)
        if last_tick.tzinfo is None:
            pass  # last_tick 存的是本地时间
        if now.tzinfo is None:
            pass  # now 已是本地时间，不做 UTC 转换
        
        remaining_hours = (now - last_tick).total_seconds() / 3600.0
        
        # 计算 cost_multi（供 remaining_hours 结算使用）
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        cost_multi = calc_cost_multi(active_buffs)
        
        if remaining_hours > 0:
            attrs = user["attributes"]
            # 结算属性（无金币，整点不发金币）
            attrs["strength"] = max(0, attrs["strength"] - consume_strength * remaining_hours * cost_multi)
            attrs["energy"] = max(0, attrs["energy"] - consume_energy * remaining_hours * cost_multi)
            attrs["mood"] = max(0, attrs["mood"] - consume_mood * remaining_hours)
            attrs["health"] = max(0, attrs["health"] - consume_health * remaining_hours)
            attrs["satiety"] = max(0, attrs["satiety"] - consume_satiety * 0.5 * remaining_hours)
            # 累积压力
            accumulate_pressure(user, pressure_type, pressure_rate * remaining_hours)
            user["attributes"] = attrs
        
        # ========== 工作完成，结算全部金币（按计划总时长）==========
        effects = calc_equipped_effects(user)
        work_income_bonus = effects.get("work_income_bonus", 0) / 100.0
        income_multi = calc_income_multi(active_buffs)
        fixed_bonus = get_fixed_bonus(active_buffs)
        debuff_penalty = calc_debuff_income_penalty(user)
        pressure = user.get(f"{pressure_type}_pressure", 0)
        pressure_penalty = 1.0 - get_pressure_penalty(pressure)
        attrs = user.get("attributes", {})
        
        efficiency = pressure_penalty * debuff_penalty
        if attrs.get("satiety", 100) < 20:
            efficiency *= 0.7
        
        # 按计划总时长计算金币（不是 remaining_hours）
        gold_earned = int(hourly_wage * hours * efficiency * income_multi * (1 + work_income_bonus))
        gold_earned += int(fixed_bonus * hours)
        detail["earned_gold"] = gold_earned
        user["gold"] = user.get("gold", 0) + gold_earned
        
        # 记录
        user.setdefault("records", []).append({
            "type": "工作",
            "detail": f"完成了{job_name}{hours}小时",
            "gold_change": detail["earned_gold"],
            "time": now.isoformat(),
        })
        
        # ========== 记录统计数据 ==========
        gold_earned = detail["earned_gold"]
        update_daily_stat(user, "gold_work", gold_earned)
        update_daily_stat(user, "work_hours", hours)
        update_daily_stat(user, "work_count", 1)
        update_lifetime_stat(user, "total_gold_earned", gold_earned)
        update_lifetime_stat(user, "total_work_hours", hours)
        update_lifetime_stat(user, "total_work_count", 1)
        # ========== 统计记录完成 ==========
        
        # 消耗 job_count 类型的 buff
        checkin = user.get("checkin", {})
        buffs = checkin.get("active_buffs", [])
        remaining_buffs = []
        for buff in buffs:
            if BuffManager.is_expired(buff):
                continue
            if buff.get("limit") == BuffLimit.JOB_COUNT:
                if not BuffManager.consume_buff(buff):
                    continue
            remaining_buffs.append(buff)
        checkin["active_buffs"] = remaining_buffs
        user["checkin"] = checkin
        
        user["attributes"] = attrs if remaining_hours > 0 else user.get("attributes", {})

        # 清理 jobs_in_progress 中的对应记录
        job_id = data.get("job_id") or job_name
        jobs_in_progress = user.get("jobs_in_progress", [])
        for i, j in enumerate(jobs_in_progress):
            if j.get("job_id") == job_id or j.get("title") == job_name:
                jobs_in_progress.pop(i)
                break
        user["jobs_in_progress"] = jobs_in_progress

        await self.plugin._store.update_user(user_id, user)
        
        # 发送工作完成通知
        try:
            messenger = self.plugin._messenger
            await messenger.notify_work_complete(
                user_id,
                job_name=job_name,
                earned_gold=gold_earned,
                session_key=detail.get("data", {}).get("session_key", ""),  # 9/6: Pattern 10
            )
        except Exception as e:
            self.plugin.logger.error(f"工作完成通知发送失败: {e}")
        
        return True

# ============================================================

        return True


# ============================================================
# LearnTickProcessor - 学习处理器
# ============================================================

class LearnTickProcessor(TickProcessor):
    """学习Tick处理器"""
    
    def get_action_type(self) -> str:
        return TICK_TYPE_LEARN
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理学习tick"""
        
        action_type = detail.get("action_type")
        if action_type != TICK_TYPE_LEARN:
            return False
        
        course_name = detail.get("data", {}).get("course_name")
        course = COURSES.get(course_name)
        if not course:
            self.plugin.logger.warning(f"Tick学习: 课程不存在 [{course_name}]，跳过结算")
            return True
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 记录写入前状态，用于判断是否需要写入
        old_exp = detail.get("earned_exp", 0)
        old_attrs = dict(user.get("attributes", {}))
        
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        exp_multi = calc_exp_multi(active_buffs)
        
        # 装备效果加成
        effects = calc_equipped_effects(user)
        learn_exp_bonus = effects.get("learn_exp_bonus", 0) / 100.0
        
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            
            # 每分钟消耗（按比例）
            attrs["strength"] = max(0, attrs["strength"] - course.get("consume_strength", 3) / TICKS_PER_HOUR)
            attrs["energy"] = max(0, attrs["energy"] - course.get("consume_energy", 8) / TICKS_PER_HOUR)
            attrs["mood"] = max(0, attrs["mood"] - course.get("consume_mood", 5) / TICKS_PER_HOUR)
            attrs["satiety"] = max(0, attrs["satiety"] - course.get("consume_satiety", 5) / TICKS_PER_HOUR)
            
            # 每分钟获得经验
            exp_per_tick = course.get("exp_per_hour", 10) / TICKS_PER_HOUR * exp_multi * (1 + learn_exp_bonus)
            exp_gained = int(exp_per_tick)
            detail["earned_exp"] += exp_gained
            
            user["attributes"] = attrs
        
        # 状态变化时写入（而非每分钟都写）
        # 判断条件：经验变化 或 属性变化
        new_attrs = user.get("attributes", {})
        attrs_changed = any(
            old_attrs.get(k, 0) != new_attrs.get(k, 0)
            for k in ["strength", "energy", "mood", "satiety"]
        )
        if detail.get("earned_exp", 0) != old_exp or attrs_changed:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        if completed >= planned:
            hours = planned / TICKS_PER_HOUR
            
            # 获取课程对应的技能名称
            course_skill = course.get("skill")
            
            # 累加经验到用户技能经验池
            if course_skill and detail["earned_exp"] > 0:
                user.setdefault("skill_exp", {})
                user["skill_exp"][course_skill] = user["skill_exp"].get(course_skill, 0) + detail["earned_exp"]
                
                # 根据总经验和技能对应的曲线类型计算技能等级
                exp_rate = get_skill_exp_rate(course_skill)
                user.setdefault("skills", {})
                user["skills"][course_skill] = get_skill_level(user["skill_exp"][course_skill], exp_rate)
                
                self.plugin.logger.info(
                    f"用户 {user['nickname']} 完成{course_name}学习，"
                    f"获得{detail['earned_exp']}经验，"
                    f"{course_skill}技能提升至 Lv.{user['skills'][course_skill]}"
                )
            
            user.setdefault("records", []).append({
                "type": "学习",
                "detail": f"完成了{course_name}{hours}小时",
                "gold_change": 0,
                "time": now.isoformat(),
            })
            
            # ========== 记录统计数据 ==========
            update_daily_stat(user, "learn_hours", hours)
            update_lifetime_stat(user, "total_learn_hours", hours)
            # ========== 统计记录完成 ==========
            
            # 发送学习完成通知
            try:
                messenger = self.plugin._messenger
                await messenger.notify_learn_complete(
                    user_id,
                    skill_name=course_name,
                    earned_exp=detail.get("earned_exp", 0),
                    session_key=detail.get("data", {}).get("session_key", ""),  # 9/6: Pattern 10
                )
            except Exception as e:
                self.plugin.logger.error(f"学习完成通知发送失败: {e}")
            
            return True
        
        return False


# ============================================================
# EntertainTickProcessor - 娱乐处理器
# ============================================================

class EntertainTickProcessor(TickProcessor):
    """娱乐Tick处理器"""
    
    def get_action_type(self) -> str:
        return TICK_TYPE_ENTERTAIN
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理娱乐tick"""
        
        action_type = detail.get("action_type")
        if action_type != TICK_TYPE_ENTERTAIN:
            return False
        
        entertainment_name = detail.get("data", {}).get("entertainment_name")
        entertainment = ENTERTAINMENTS.get(entertainment_name)
        if not entertainment:
            return True
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 记录写入前状态，用于判断是否需要写入
        old_gold = user.get("gold", 0)
        old_attrs = dict(user.get("attributes", {}))
        
        # 装备效果加成
        effects = calc_equipped_effects(user)
        entertain_mood_bonus = effects.get("entertain_mood_bonus", 0) / 100.0
        
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            
            # 每分钟消耗金币
            cost_per_tick = entertainment.get("cost_per_hour", 10) / TICKS_PER_HOUR
            user["gold"] = max(0, user["gold"] - cost_per_tick)
            
            # 每分钟恢复/消耗
            attrs["mood"] = min(100, attrs["mood"] + entertainment.get("restore_mood", 15) / TICKS_PER_HOUR * (1 + entertain_mood_bonus))
            attrs["strength"] = max(0, attrs["strength"] - entertainment.get("consume_strength", 5) / TICKS_PER_HOUR)
            attrs["energy"] = max(0, attrs["energy"] - entertainment.get("consume_energy", 3) / TICKS_PER_HOUR)
            
            user["attributes"] = attrs
        
        # 娱乐结束时累积压力缓解（按娱乐类型）
        if completed >= planned:
            relief = ENTERTAINMENT_PRESSURE_RELIEF.get(entertainment_name, {"body": 0, "mind": 0})
            if relief.get("body", 0) > 0:
                accumulate_pressure(user, "body", -relief["body"])
            if relief.get("mind", 0) > 0:
                accumulate_pressure(user, "mind", -relief["mind"])
            hours = planned / TICKS_PER_HOUR
            gold_cost = entertainment.get("cost_per_hour", 10) * planned / TICKS_PER_HOUR
            user.setdefault("records", []).append({
                "type": "娱乐",
                "detail": f"完成了{entertainment_name}{hours}小时",
                "gold_change": -gold_cost,
                "time": now.isoformat(),
            })
            
            # ========== 记录统计数据 ==========
            update_daily_stat(user, "gold_spent", gold_cost)
            update_daily_stat(user, "entertain_count", 1)
            update_lifetime_stat(user, "total_gold_spent", gold_cost)
            update_lifetime_stat(user, "total_entertain_count", 1)
            # ========== 统计记录完成 ==========
            
            # 发送娱乐完成通知
            try:
                messenger = self.plugin._messenger
                mood_gain = int(entertainment.get("restore_mood", 15) * hours)
                await messenger.notify_entertain_complete(
                    user_id,
                    ent_name=entertainment_name,
                    mood_gain=mood_gain,
                    session_key=detail.get("data", {}).get("session_key", ""),  # 9/6: Pattern 10
                )
            except Exception as e:
                self.plugin.logger.error(f"娱乐完成通知发送失败: {e}")
            
            return True
        
        # 状态变化时写入（而非每分钟都写）
        # 判断条件：金币变化 或 属性变化
        new_attrs = user.get("attributes", {})
        attrs_changed = any(
            old_attrs.get(k, 0) != new_attrs.get(k, 0)
            for k in ["mood", "strength", "energy"]
        )
        if user.get("gold", 0) != old_gold or attrs_changed:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)

        return False


class FishingTickProcessor(TickProcessor):
    """钓鱼Tick处理器

    每个 tick 调用 roll_catch 概率判中鱼（PER_TICK_CATCH_BASE = 5%）。
    中鱼后：写 fish_caught/records/biggest_catch + 加技能经验 + 发卡片通知 + 自动结束。
    若超过 planned_ticks 仍未中鱼，自动结束（竿子收线）。
    """
    def get_action_type(self) -> str:
        return TICK_TYPE_FISHING

    async def process(self, user_id, user, detail, now):
        if detail.get("action_type") != TICK_TYPE_FISHING:
            return False

        from ..src.fishing.fishing_manager import (
            roll_catch, apply_catch, check_fish_title, get_fishing_skill_level,
        )
        from ..modules.constants import ITEMS

        data = detail.get("data", {})
        spot_id = data.get("spot_id", "")
        rod_id = data.get("rod_id", "竹竿")
        # 9/4晚: 多槽鱼钩 (优先 hook_slots, 兼容 hook_id)
        hook_ids = data.get("hook_slots", [])
        if not hook_ids:
            legacy_hook = data.get("hook_id", "")
            hook_ids = [legacy_hook] if legacy_hook else []
        # 9/4晚: 多槽饵料 (bait_slots 列表, 默认1个)
        bait_ids = data.get("bait_slots", data.get("bait_ids", []))
        if isinstance(bait_ids, str):
            # 兼容旧数据: 单 bait_id → 包成列表
            bait_ids = [bait_ids] if bait_ids else []
        if not bait_ids:
            # 兜底用 data.get("bait_id", "")
            legacy = data.get("bait_id", "")
            bait_ids = [legacy] if legacy else []
        # 9/3晚: 鱼轮 (钓鱼经验加成 + rare_bonus + duration_reduce)
        reel_id = data.get("reel_id", "")
        # 9/3: 渔具其他槽
        line_id = data.get("line_id", "")
        float_id = data.get("float_id", "")

        # 9/5: 从 user.equipped_items 取 entry effects (含附魔词条)
        equipped_items = user.get("equipped_items", {})

        def _entry_effects(slot_key: str) -> dict:
            """从 equipped_items 拿 slot 的 entry effects, 找不到 fallback ITEMS.base

            9/7: 兼容老 slot 名 (line→fishing_line, hook→fishing_hook, float→fishing_float,
                 reel→fishing_reel, bait→fishing_bait). 也兼容单槽字段 (hook) vs 多槽列表 (hook_slots)
            """
            # 9/7 兼容映射 (老 key → 新 key)
            _SLOT_LEGACY = {
                "line": "fishing_line",
                "hook": "fishing_hook",
                "float": "fishing_float",
                "reel": "fishing_reel",
                "bait": "fishing_bait",
                "lure": "fishing_lure",
                "rod": "fishing_rod",
            }
            _LIST_LEGACY = {
                "hook_slots": "fishing_hook",   # 多槽 fallback 单槽
                "bait_slots": "fishing_bait",   # 多槽 fallback 单槽
            }
            # 多槽优先 (hook_slots/bait_slots)
            e = equipped_items.get(slot_key)
            # 列表类 key: fallback 单槽 (老数据 hook/bait 单字段)
            if not e and slot_key in _LIST_LEGACY:
                e = equipped_items.get(_LIST_LEGACY[slot_key])
            # 单槽 key: 兼容老 slot 名
            if not e and slot_key in _SLOT_LEGACY:
                e = equipped_items.get(_SLOT_LEGACY[slot_key])
            # 新 slot 名查老 key (比如 _entry_effects("fishing_hook") 读老数据 equipped_items["hook"])
            if not e:
                for old_key, new_key in _SLOT_LEGACY.items():
                    if new_key == slot_key:
                        e = equipped_items.get(old_key)
                        if e:
                            break
            if isinstance(e, dict) and e.get("id"):
                eff = e.get("effects") or ITEMS.get(e.get("id", ""), {}).get("effects", {})
                return eff
            return {}

        def _entry_effects_list(slot_key: str) -> list[dict]:
            """拿列表槽位 (hook_slots/bait_slots) 所有 entry effects

            9/7: 兼容老单槽字段 (hook/bait) → 转为单元素列表
            """
            slots = equipped_items.get(slot_key, [])
            if not slots:
                # 兼容老单槽字段
                _SINGLE_LEGACY = {
                    "hook_slots": "fishing_hook",
                    "bait_slots": "fishing_bait",
                    "fishing_hook": "hook",       # 查老 key "hook"
                    "fishing_bait": "bait",       # 查老 key "bait"
                }
                fallback_key = _SINGLE_LEGACY.get(slot_key)
                if fallback_key:
                    single = equipped_items.get(fallback_key)
                    if isinstance(single, dict) and single.get("id"):
                        slots = [single]
            if not isinstance(slots, list):
                return []
            out = []
            for s in slots:
                if isinstance(s, dict) and s.get("id"):
                    eff = s.get("effects") or ITEMS.get(s.get("id", ""), {}).get("effects", {})
                    out.append(eff)
            return out

        rod = _entry_effects("fishing_rod")
        # 9/4晚: 多钩/多饵 - 合并所有 hook effects (size_weights 取累加)
        hook_effects_list = _entry_effects_list("hook_slots")
        hook_effects = {}
        for eff in hook_effects_list:
            for k, v in eff.items():
                if k == "target_size_weights" and isinstance(v, dict):
                    hook_effects.setdefault(k, {})
                    for sc, w in v.items():
                        hook_effects[k][sc] = hook_effects[k].get(sc, 0) + w
                else:
                    hook_effects[k] = hook_effects.get(k, 0) + v if isinstance(v, (int, float)) else v
        # 9/4晚: 多槽饵料 - 从 entry effects 取
        bait_effects_list = _entry_effects_list("bait_slots")
        consume_targets = []  # [(bait_id, is_consumable)]
        bait_ids = data.get("bait_slots", data.get("bait_ids", []))
        if isinstance(bait_ids, str):
            bait_ids = [bait_ids] if bait_ids else []
        if not bait_ids:
            legacy = data.get("bait_id", "")
            bait_ids = [legacy] if legacy else []
        # 从 entry.consumable 判定 (而非 ITEMS.consumable)
        bait_slots_data = equipped_items.get("bait_slots", [])
        for bs in (bait_slots_data if isinstance(bait_slots_data, list) else []):
            if not isinstance(bs, dict):
                continue
            bid = bs.get("id", "")
            if bid:
                # consumable 来自 entry (entry 保存了购买时的 consumable)
                consume_targets.append((bid, bool(bs.get("consumable", bs.get("effects", {}).get("consumable", False)))))
        # 9/7 命名统一: 用 fishing_ 前缀的 slot 名
        line = _entry_effects("fishing_line")
        float_eff = _entry_effects("fishing_float")
        reel = _entry_effects("fishing_reel")

        # 1. 尝试中鱼 (多 hook effects 合并, 多饵 effects list)
        catch = roll_catch(user, spot_id, rod, bait_effects_list, line_effects=line, hook_effects=hook_effects, float_effects=float_eff, reel_effects=reel)

        if catch:
            # 9/4晚: 中鱼后扣 bait_slot 内 quantity (消耗饵), 拟饵不扣
            self._consume_one_bait(user, consume_targets, bait_slots_data)

        if catch:
            # 9/3深夜: 断线事件 - 不算鱼, 丢失鱼线/鱼钩/鱼饵(1个)/鱼漂, 通知玩家
            if catch.get("_line_break"):
                lost = self._lose_gear_on_line_break(user)
                await self._notify_line_break(user_id, catch, detail, lost_gear=lost)
                await self.plugin._store.update_user(user_id, user)
                return False
            # 9/6: 断竿事件 - 丢失鱼竿/鱼轮/鱼线/鱼钩/鱼漂/鱼饵(1个), 通知玩家
            if catch.get("_rod_break"):
                lost = self._lose_gear_on_rod_break(user)
                await self._notify_rod_break(user_id, catch, detail, lost_gear=lost)
                await self.plugin._store.update_user(user_id, user)
                return False
            # 写入用户数据 (apply_catch 内部已加 skill_exp, 写 _last_levelup)
            apply_catch(user, catch, now.isoformat(), reel_effects=reel, all_effects=None)
            # 读 apply_catch 算出的升级信息
            levelup_info = user.get("fishing", {}).pop("_last_levelup", None) or {
                "from": 0, "to": get_fishing_skill_level(user),
                "exp_gain": 0, "total_exp": user.get("skill_exp", {}).get("钓鱼", 0),
            }
            # 同步 skills["钓鱼"] = level (兼容性, 老 UI 读这个字段)
            user.setdefault("skills", {})["钓鱼"] = levelup_info["to"]
            # 检查称号
            new_title = check_fish_title(user)
            user["fishing"]["last_catch"] = {
                "fish": catch["fish_id"],
                "weight": catch["weight"],
                "size_label": catch["size_label"],
                "length_cm": catch.get("length_cm"),
                "estimated_price": catch["estimated_price"],
                "spot": spot_id,
                "time": now.isoformat(),
                "title_unlocked": new_title,
                "exp_gain": levelup_info["exp_gain"],
                "level_up": levelup_info["from"] != levelup_info["to"],
                "skill_level": levelup_info["to"],
                "total_exp": levelup_info["total_exp"],
            }

            # 通知用户（私聊 + 群 @）
            try:
                await self._notify_catch(user_id, user, catch, new_title, detail, levelup_info)
            except Exception as e:
                self.plugin.logger.error(f"钓鱼结果通知失败: {e}")

            # 自动结束钓鱼动作
            user["status"] = "空闲"
            user["current_action"] = None
            user["action_detail"] = None
            await self.plugin._store.update_user(user_id, user)
            return True

        # 2. 检查是否超过最长时间（没中鱼也得收竿）
        elapsed = ActionDetail.get_elapsed_ticks(detail, now)
        planned = detail["planned_ticks"]
        if elapsed >= planned:
            try:
                await self._notify_empty(user_id, user, spot_id)
            except Exception as e:
                self.plugin.logger.error(f"钓鱼空竿通知失败: {e}")
            user["status"] = "空闲"
            user["current_action"] = None
            user["action_detail"] = None
            await self.plugin._store.update_user(user_id, user)
            return True

        # 3. 每 tick 更新进度（轻量：不调 store 写盘）
        detail["completed_ticks"] = elapsed
        ActionDetail.update_tick(detail, now)
        user["action_detail"] = detail
        return False

    async def _notify_catch(self, user_id, user, catch, new_title, detail, levelup_info=None):
        """把中鱼通知扔进 plugin 的通知队列（方案G）。

        consumer task 会通过缓存的最近 event.send() 发消息，
        完全不构造 MessageSession —— 走 AstrBot 内部路径，
        无需 platform_id，无需 MessageSession.from_str。

        9/8: 标题文本加入鱼名 + 重量 + 尺寸, 让用户从通知标题也能看出鱼况
        """
        try:
            from ..src.fishing.fishing_manager import format_weight, format_length_compact
            fish = catch["fish"]
            nickname = user.get("nickname", "钓手")
            fish_name = fish.get("name", "鱼")
            emoji = fish.get("emoji", "🐟")
            weight_str = format_weight(catch.get("weight", 0))
            length_str = format_length_compact(catch.get("length_cm"))

            # 9/8: 标题文本含鱼名 + 重量 + 尺寸 (例: "🎣 上钩！草鱼 1.50kg 35cm")
            text = f"🎣 上钩！{emoji} {fish_name} {weight_str} {length_str}"

            # 尝试渲染卡片
            image_url = None
            try:
                renderer = getattr(self.plugin, "_renderer", None)
                if renderer:
                    image_url = await renderer.render_fishing_catch(user, catch, new_title, exp_gain=(levelup_info or {}).get("exp_gain", 0))
            except Exception as e:
                self.plugin.logger.warning(f"钓鱼卡片渲染失败（降级纯文本）: {type(e).__name__}: {e}")

            # at() 签名：.at(name, qq)
            try:
                qq = int(user_id) if user_id.isdigit() else user_id
            except (ValueError, AttributeError):
                qq = user_id

            # 构造 chain, 扔进队列. consumer 会用 event.send() 发.
            from astrbot.core.message.message_event_result import MessageChain
            chain = MessageChain().at(name=nickname, qq=qq).message(text)
            if image_url:
                import logging
                logging.getLogger("astrbot_plugin_niumalife").warning(f"[FISH_NOTIFY] image_url={image_url!r}")
                # 判断是本地路径还是 URL: 本地用 file_image, 远程用 url_image
                if image_url.startswith(("http://", "https://")):
                    chain = chain.url_image(image_url)
                else:
                    chain = chain.file_image(image_url)

            q = getattr(self.plugin, "_notify_queue", None)
            if q is None:
                self.plugin.logger.error("plugin._notify_queue 未初始化")
                return
            # 9/6: 优先用完整 session_key (新); 回退到 start_group_id (旧数据)
            action_detail = user.get("action_detail", {})
            action_data = action_detail.get("data", {})
            session_key = action_data.get("session_key", "")
            if not session_key:
                start_group_id = action_data.get("start_group_id", "")
                session_key = start_group_id  # 旧数据: 裸 group_id, consumer 走 suffix 匹配
            # put_nowait 同步入队，consumer 异步消费
            q.put_nowait((user_id, chain, session_key))
        except Exception as e:
            self.plugin.logger.error(f"构造钓鱼通知失败: {e}")

    async def _notify_empty(self, user_id, user, spot_id):
        """超时未中鱼通知：扔进通知队列。"""
        try:
            nickname = user.get("nickname", "钓手")
            text = f"🎣 在 {spot_id} 钓了一整天，一条都没上……先收竿吧。"
            try:
                qq = int(user_id) if user_id.isdigit() else user_id
            except (ValueError, AttributeError):
                qq = user_id

            from astrbot.core.message.message_event_result import MessageChain
            chain = MessageChain().at(name=nickname, qq=qq).message(text)

            q = getattr(self.plugin, "_notify_queue", None)
            if q is None:
                return
            # 9/6: 优先用完整 session_key (新); 回退到 start_group_id (旧数据)
            action_detail = user.get("action_detail", {})
            action_data = action_detail.get("data", {})
            session_key = action_data.get("session_key", "") or action_data.get("start_group_id", "")
            q.put_nowait((user_id, chain, session_key))
        except Exception as e:
            self.plugin.logger.error(f"构造空竿通知失败: {e}")

    def _lose_gear_on_line_break(self, user: dict) -> list[str]:
        """9/6: 断线时丢失鱼线/鱼钩/鱼饵(1个)/鱼漂

        Args:
            user: 用户数据 (in-place 修改)

        Returns:
            丢失的装备名列表
        """
        lost = []
        equipped = user.get("equipped_items", {})
        # 鱼线 - 必丢 (9/7 命名统一, 兼容老 key "line")
        line = equipped.get("fishing_line") or equipped.get("line", {})
        if line:
            lost.append(f"鱼线:{line.get('id', '?')}")
            equipped["fishing_line"] = {}
        # 鱼钩 - 必丢 (9/7: 兼容 hook_slots 老 key + hook 单字段 fallback)
        hook_slots = equipped.get("hook_slots", [])
        if not hook_slots:
            single_hook = equipped.get("hook") or equipped.get("fishing_hook")
            if isinstance(single_hook, dict) and single_hook.get("id"):
                lost.append(f"鱼钩:{single_hook.get('id', '?')}")
                equipped["fishing_hook"] = {}
        if hook_slots and isinstance(hook_slots, list):
            new_slots = []
            for hs in hook_slots:
                if isinstance(hs, dict) and hs.get("id"):
                    lost.append(f"鱼钩:{hs.get('id', '?')}")
                else:
                    new_slots.append(hs)
            equipped["hook_slots"] = new_slots
        # 鱼漂 - 必丢 (9/7: 兼容老 key "float")
        fl = equipped.get("fishing_float") or equipped.get("float", {})
        if fl:
            lost.append(f"鱼漂:{fl.get('id', '?')}")
            equipped["fishing_float"] = {}
        # 鱼饵 - 只丢 1 个 (9/7: 兼容 bait_slots 老 key + bait 单字段)
        bait_slots = equipped.get("bait_slots", [])
        if not bait_slots:
            single_bait = equipped.get("bait") or equipped.get("fishing_bait")
            if isinstance(single_bait, dict) and single_bait.get("id"):
                single_bait["quantity"] = single_bait.get("quantity", 1) - 1
                lost.append(f"鱼饵:{single_bait.get('id', '?')}")
        if bait_slots and isinstance(bait_slots, list):
            for bs in bait_slots:
                if isinstance(bs, dict) and bs.get("id"):
                    # quantity -1
                    bs["quantity"] = bs.get("quantity", 1) - 1
                    lost.append(f"鱼饵:{bs.get('id', '?')}")
                    break  # 只扣一个
        user["equipped_items"] = equipped
        return lost

    def _lose_gear_on_rod_break(self, user: dict) -> list[str]:
        """9/6: 断竿时丢失鱼竿/鱼轮/鱼线/鱼钩/鱼漂/鱼饵(1个)

        Args:
            user: 用户数据 (in-place 修改)

        Returns:
            丢失的装备名列表
        """
        lost = []
        equipped = user.get("equipped_items", {})
        # 鱼竿 - 必丢
        rod = equipped.get("fishing_rod", {})
        if rod:
            lost.append(f"鱼竿:{rod.get('id', '?')}")
            equipped["fishing_rod"] = {}
        # 鱼轮 - 必丢
        reel = equipped.get("fishing_reel", {})
        if reel:
            lost.append(f"鱼轮:{reel.get('id', '?')}")
            equipped["fishing_reel"] = {}
        # 鱼线 - 必丢 (9/7 命名统一, 兼容老 key "line")
        line = equipped.get("fishing_line") or equipped.get("line", {})
        if line:
            lost.append(f"鱼线:{line.get('id', '?')}")
            equipped["fishing_line"] = {}
        # 鱼钩 - 必丢
        # 鱼钩 - 必丢 (9/7: 兼容 hook_slots 老 key + hook 单字段 fallback)
        hook_slots = equipped.get("hook_slots", [])
        if not hook_slots:
            # 兼容: 单字段 hook / fishing_hook
            single_hook = equipped.get("hook") or equipped.get("fishing_hook")
            if isinstance(single_hook, dict) and single_hook.get("id"):
                lost.append(f"鱼钩:{single_hook.get('id', '?')}")
                equipped["fishing_hook"] = {}
        if hook_slots and isinstance(hook_slots, list):
            new_slots = []
            for hs in hook_slots:
                if isinstance(hs, dict) and hs.get("id"):
                    lost.append(f"鱼钩:{hs.get('id', '?')}")
                else:
                    new_slots.append(hs)
            equipped["hook_slots"] = new_slots
        # 鱼漂 - 必丢 (9/7: 兼容老 key "float")
        fl = equipped.get("fishing_float") or equipped.get("float", {})
        if fl:
            lost.append(f"鱼漂:{fl.get('id', '?')}")
            equipped["fishing_float"] = {}
        # 鱼饵 - 只丢 1 个 (9/7: 兼容 bait_slots 老 key + bait 单字段)
        bait_slots = equipped.get("bait_slots", [])
        if not bait_slots:
            # 兼容: 单字段 bait / fishing_bait
            single_bait = equipped.get("bait") or equipped.get("fishing_bait")
            if isinstance(single_bait, dict) and single_bait.get("id"):
                single_bait["quantity"] = single_bait.get("quantity", 1) - 1
                lost.append(f"鱼饵:{single_bait.get('id', '?')}")
        if bait_slots and isinstance(bait_slots, list):
            for bs in bait_slots:
                if isinstance(bs, dict) and bs.get("id"):
                    bs["quantity"] = bs.get("quantity", 1) - 1
                    lost.append(f"鱼饵:{bs.get('id', '?')}")
                    break
        user["equipped_items"] = equipped
        return lost


    async def _notify_rod_break(self, user_id, catch, detail, lost_gear: list = []):
        """9/6: 断竿通知 - 巨物咬钩但鱼竿承受不住, 竿损坏

        catch dict:
            _rod_break: True
            fish_id, fish_name, weight, size_label
            overload_pct: 超载百分比
            rod_load_max: 鱼竿承载力 (kg)
        """
        try:
            nickname = detail.get("nickname") if detail else "钓手"
            fish_name = catch.get("fish_name", catch.get("fish_id", "巨物"))
            weight = catch.get("weight", 0)
            overload = catch.get("overload_pct", 0)
            cap = catch.get("rod_load_max", 0)
            lost_str = ", ".join(lost_gear) if lost_gear else "无"
            text = (
                f"🎣 咔嚓！{fish_name} ({weight}kg) 咬钩后扯断了鱼竿……\n"
                f"超载 {overload}%（竿承重 {cap}kg）\n"
                f"💔 丢失装备: {lost_str}"
            )
            try:
                qq = int(user_id) if user_id.isdigit() else user_id
            except (ValueError, AttributeError):
                qq = user_id

            from astrbot.core.message.message_event_result import MessageChain
            chain = MessageChain().at(name=nickname or "钓手", qq=qq).message(text)

            q = getattr(self.plugin, "_notify_queue", None)
            if q is None:
                self.plugin.logger.error("plugin._notify_queue 未初始化")
                return

            session_key = detail.get("session_key", "") if detail else ""
            try:
                q.put_nowait((user_id, chain, session_key))
            except Exception as e:
                self.plugin.logger.error(f"构造断竿通知失败: {e}")
        except Exception as e:
            logger.error(f"[断竿通知失败] user_id={user_id}, error={e}")


    async def _notify_line_break(self, user_id, catch, detail, lost_gear: list = []):
        """9/3深夜: 断线通知 - 巨物咬钩但线断了, 不算鱼仅通知

        catch dict:
            _line_break: True
            fish_id, fish_name, weight, size_label
            overload_pct: 超载百分比
            line_load_max: 鱼线承载力 (kg)
        """
        try:
            nickname = detail.get("nickname") if detail else "钓手"
            # 简略: @用户 + "巨物逃了" + 关键数据
            fish_name = catch.get("fish_name", catch.get("fish_id", "巨物"))
            weight = catch.get("weight", 0)
            overload = catch.get("overload_pct", 0)
            cap = catch.get("line_load_max", 0)
            lost_str = ", ".join(lost_gear) if lost_gear else "无"
            text = (
                f"🎣 噗通！{fish_name} ({weight}kg) 咬钩后扯断了线……\n"
                f"超载 {overload}%（线承重 {cap}kg）\n"
                f"💔 丢失装备: {lost_str}"
            )
            try:
                qq = int(user_id) if user_id.isdigit() else user_id
            except (ValueError, AttributeError):
                qq = user_id

            from astrbot.core.message.message_event_result import MessageChain
            chain = MessageChain().at(name=nickname or "钓手", qq=qq).message(text)

            q = getattr(self.plugin, "_notify_queue", None)
            if q is None:
                self.plugin.logger.error("plugin._notify_queue 未初始化")
                return
            # 9/6: 优先用完整 session_key (新); 回退到 start_group_id (旧数据)
            action_data = (detail or {}).get("data", {})
            session_key = action_data.get("session_key", "") or action_data.get("start_group_id", "")
            q.put_nowait((user_id, chain, session_key))
        except Exception as e:
            self.plugin.logger.error(f"构造断线通知失败: {e}")

    def _consume_one_bait(self, user: dict, consume_targets: list, bait_slots_data: list = None):
        """9/4晚: 中鱼后扣 bait_slot 内 quantity (消耗饵), 拟饵不扣

        consume_targets: [(bait_id, is_consumable), ...] (兼容性保留)
        bait_slots_data: bait_slots 列表 (优先), 包含 quantity 字段

        拟饵 (quantity=None) 永不消耗
        消耗饵 quantity -= 1, qty 归零后从 list 移除 (避免残留)
        9/7: 修复鱼饵消耗后残留 bug - qty=0 时不删除 slot 导致渔具卡死
        """
        if not bait_slots_data:
            return

        # 找到第一个消耗饵槽扣 1 个
        for slot in bait_slots_data:
            if not slot.get("consumable", False):
                continue
            qty = slot.get("quantity")
            if qty is None or qty <= 0:
                continue
            new_qty = qty - 1
            if new_qty <= 0:
                # 9/7: 数量归零 → 从列表移除 slot, 避免卡装备栏
                bait_slots_data.remove(slot)
            else:
                slot["quantity"] = new_qty
            return  # 只扣一个槽


# ============================================================
# TickManager - Tick 管理器 + 时间触发器
# ============================================================

class TickManager:
    """Tick管理器 - 包含用户Tick和时间触发器"""
    
    def __init__(self, plugin):
        self.plugin = plugin
        self._processors = {
            TICK_TYPE_WORK: WorkTickProcessor(plugin),
            TICK_TYPE_LEARN: LearnTickProcessor(plugin),
            TICK_TYPE_ENTERTAIN: EntertainTickProcessor(plugin),
            TICK_TYPE_FISHING: FishingTickProcessor(plugin),
        }
        
        # 时间触发器状态
        self._last_hour = None
        self._last_day = None
        self._cron_states = {}  # {cron_key: last_trigger_time}
    
    # ========================================================
    # 用户动作处理
    # ========================================================
    
    async def process_user_actions(self, user_id: str, user: dict, now: datetime):
        """处理用户的所有进行中动作"""
        detail = user.get("action_detail")
        if not detail:
            return
        
        action_type = detail.get("action_type")
        processor = self._processors.get(action_type)
        
        if not processor:
            self.plugin.logger.warning(f"未知的动作类型: {action_type}，强制结束")
            user["status"] = "空闲"
            user["current_action"] = None
            user["action_detail"] = None
            await self.plugin._store.update_user(user_id, user)
            return
        
        # 检查是否已完成
        if ActionDetail.is_expired(detail, now):
            self.plugin.logger.info(f"用户 {user['nickname']} 的{action_type}已完成，清理状态")
            
            # 如果是学习动作，写入经验
            if action_type == TICK_TYPE_LEARN:
                course_name = detail.get("data", {}).get("course_name")
                course = COURSES.get(course_name)
                if not course:
                    self.plugin.logger.warning(f"停机恢复: 课程不存在 [{course_name}]")
                else:
                    course_skill = course.get("skill")
                    if course_skill and detail.get("earned_exp", 0) > 0:
                        user.setdefault("skill_exp", {})
                        user["skill_exp"][course_skill] = user["skill_exp"].get(course_skill, 0) + detail["earned_exp"]
                        exp_rate = get_skill_exp_rate(course_skill)
                        user.setdefault("skills", {})
                        user["skills"][course_skill] = get_skill_level(user["skill_exp"][course_skill], exp_rate)
                        self.plugin.logger.info(
                            f"停机恢复: {user['nickname']} {course_skill}技能提升至 Lv.{user['skills'][course_skill]}"
                        )
                # 无论课程是否存在都清理动作状态
                user["status"] = "空闲"
                user["current_action"] = None
                user["action_detail"] = None
                await self.plugin._store.update_user(user_id, user)
                return
        
        # 正常处理
        try:
            completed = await processor.process(user_id, user, detail, now)
            if completed:
                user["status"] = "空闲"
                user["current_action"] = None
                user["action_detail"] = None
                await self.plugin._store.update_user(user_id, user)
                self.plugin.logger.info(f"用户 {user['nickname']} 的{action_type}完成")
        except Exception as e:
            self.plugin.logger.error(f"处理{action_type}时出错: {e}")
    
    async def tick_all_users(self, now: datetime):
        """Tick所有用户"""
        users = await self.plugin._store.get_all_users()
        
        # 检查是否到达整点，用于空闲用户结算
        is_hourly_settle = (now.minute == 0)
        current_hour_str = f"{now.hour:02d}:00" if is_hourly_settle else None
        
        for user_id, user in users.items():
            try:
                await self.process_user_actions(user_id, user, now)
                
                # 被动效果：仅对空闲状态用户生效
                if user.get("status") == UserStatus.FREE:
                    effects = calc_equipped_effects(user)
                    attrs = user.get("attributes", {})
                    checkin = user.get("checkin", {})
                    active_buffs = checkin.get("active_buffs", [])
                    cost_multi = calc_cost_multi(active_buffs)
                    
                    # ========== 整点结算空闲属性 ==========
                    if is_hourly_settle and current_hour_str:
                        last_idle_settle = user.get("last_idle_settle")
                        if last_idle_settle != current_hour_str:
                            # 执行整点结算
                            await self._settle_idle_hourly(user, user_id, effects, attrs, cost_multi, now)
                            user["last_idle_settle"] = current_hour_str
                            user["attributes"] = attrs
                    
                    # 非整点时只处理被动效果（但不结算属性变化）
                    else:
                        # 被动心情恢复 (per tick/minute)
                        passive_mood = effects.get("passive_mood", 0)
                        if passive_mood > 0:
                            attrs["mood"] = max(0, min(100, attrs.get("mood", 100) + passive_mood))
                        
                        # 被动金币获取 (per tick/minute)
                        passive_gold = effects.get("passive_gold", 0)
                        if passive_gold > 0:
                            user["gold"] = max(0, user.get("gold", 0) + passive_gold)
                    
                    user["attributes"] = attrs
                    await self.plugin._store.update_user(user_id, user)
                    
            except Exception as e:
                import traceback as _tb
                self.plugin.logger.error(f"Tick用户{user_id}时出错: {e}\n{_tb.format_exc()}")
    
    async def _settle_idle_hourly(
        self, user: dict, user_id: str,
        effects: dict, attrs: dict, cost_multi: float, now: datetime
    ):
        """空闲用户整点结算
        
        Args:
            user: 用户数据
            user_id: 用户ID
            effects: 装备效果
            attrs: 用户属性
            cost_multi: 消耗倍率
            now: 当前时间
        """
        # 获取上次结算时间
        last_settle_str = user.get("last_idle_tick") or now.isoformat()
        last_settle = datetime.fromisoformat(last_settle_str)
        if last_settle.tzinfo is None:
            pass  # last_idle_tick 存的是本地时间，不做 UTC 转换
        if now.tzinfo is None:
            pass  # now 已是本地时间，不做 UTC 转换
        
        hours_since_last = (now - last_settle).total_seconds() / 3600.0
        if hours_since_last <= 0:
            return
        
        # 被动心情恢复（每小时）
        passive_mood = effects.get("passive_mood", 0)
        if passive_mood > 0:
            attrs["mood"] = max(0, min(100, attrs.get("mood", 100) + passive_mood * hours_since_last))
        
        # 被动金币获取（每小时）
        passive_gold = effects.get("passive_gold", 0)
        if passive_gold > 0:
            user["gold"] = max(0, user.get("gold", 0) + int(passive_gold * hours_since_last))
        
        # 饱食度自然消耗（每小时约5点）- 已禁用，避免长时间不操作导致资产清零
        # natural_satiety_drain = 5 * hours_since_last * cost_multi
        # attrs["satiety"] = max(0, attrs.get("satiety", 100) - natural_satiety_drain)
        
        # 更新上次结算时间
        user["last_idle_tick"] = now.isoformat()
        
        self.plugin.logger.info(
            f"整点结算: {user['nickname']} 空闲 "
            f"结算 {hours_since_last:.2f} 小时"
        )
    
    # ========================================================
    # 时间触发器
    # ========================================================
    
    async def trigger_time_based_events(self, now: datetime):
        """触发基于时间的事件
        
        在主循环中每分钟调用，检查并触发：
        1. 每小时触发 (xx:00)
        2. 每日触发 (00:00)
        3. Cron触发 (指定时间)
        """
        # 检查每小时触发
        if now.minute == 0:
            if self._last_hour is None or self._last_hour != now.hour:
                await self._trigger_hourly(now)
                self._last_hour = now.hour
        
        # 检查每日触发
        if self._last_day is None or self._last_day != now.day:
            await self._trigger_daily(now)
            self._last_day = now.day
        
        # 检查Cron触发
        await self._trigger_cron(now)
    
    async def _trigger_hourly(self, now: datetime):
        """每小时触发的事件"""
        self.plugin.logger.info(f"小时级触发: {now.hour}:00")
        
        # 1. 更新股票价格
        await self._update_stocks(now)
        
        # 2. 刷新商店（如果实现）
        # await self._refresh_shop(now)
        
        # 3. 其他每小时事件可在此添加
        await self._save_tick_state(now)
    
    async def _trigger_daily(self, now: datetime):
        """每日触发的事件"""
        self.plugin.logger.info(f"每日触发: {now.date()}")
        
        # 1. 重置每日任务（如果实现）
        # await self._reset_daily_tasks(now)
        
        # 2. 重置每日限制（如果实现）
        # await self._reset_daily_limits(now)
        
        # 3. 发送每日报告
        # await self._send_daily_report(now)
        
        await self._save_tick_state(now)
    
    async def _trigger_cron(self, now: datetime):
        """Cron触发 - 按精确时间表（所有时间使用 CST 时区）"""
        from datetime import timezone, timedelta

        # 将 UTC 时间转为 CST
        cst = now

        # 每日结算: 23:30 CST
        cron_key = "daily_settlement"
        last_trigger = self._cron_states.get(cron_key)

        if cst.hour == 23 and cst.minute == 30:
            if last_trigger is None or last_trigger != "23:30":
                self.plugin.logger.info("Cron触发: 每日结算")
                await self.plugin._do_daily_settlement()
                self._cron_states[cron_key] = "23:30"
                await self._save_tick_state(now)

        # 每日报告: 读取配置的 hour/minute
        report_key = "daily_report"
        last_report = self._cron_states.get(report_key)
        report_hour = getattr(self.plugin.config, 'daily_report_hour', 23)
        report_min = getattr(self.plugin.config, 'daily_report_minute', 0)
        if report_hour is None:
            report_hour = 23
        if report_min is None:
            report_min = 0
        report_time_str = f"{report_hour:02d}:{report_min:02d}"

        if cst.hour == report_hour and cst.minute == report_min:
            if last_report is None or last_report != report_time_str:
                self.plugin.logger.info(f"Cron触发: 每日报告 ({report_time_str})")
                await self._send_daily_reports(cst)
                self._cron_states[report_key] = report_time_str
                await self._save_tick_state(now)
    
    # ========================================================
    # 股票系统
    # ========================================================
    
    async def _update_stocks(self, now: datetime):
        """更新股票价格（每小时调用）"""
        # now 已是本地时间(CST)，直接使用
        cst_hour = now.hour
        trading = is_trading_hour(cst_hour)
        
        try:
            for stock_name, stock_info in STOCKS.items():
                price_key = f"stock_price:{stock_name}"
                current_price = await self.plugin.get_kv_data(price_key, None)
                if current_price is None:
                    current_price = stock_info.get("base_price", 100)
                
                # CST 8:00 = UTC 0:00 开盘，重置开盘价和日内高低
                if cst_hour == 8:
                    await self.plugin.put_kv_data(f"stock_open:{stock_name}", current_price)
                    await self.plugin.put_kv_data(f"stock_high:{stock_name}", current_price)
                    await self.plugin.put_kv_data(f"stock_low:{stock_name}", current_price)
                    try:
                        self.plugin.logger.info(f"股票开盘: {stock_name} ¥{current_price:.2f}")
                    except Exception:
                        self.plugin.logger.error(f"股票开盘日志格式错误: stock={stock_name}, current_price={current_price!r}")
                
                # 加载或初始化趋势
                trend_key = f"stock_trend:{stock_name}"
                trend = await self.plugin.get_kv_data(trend_key, None)
                if trend is None:
                    trend = init_stock_trend(stock_name, stock_info)
                
                # 更新价格
                new_price, new_trend, msg = update_stock_price(
                    stock_name, stock_info, current_price, trend, trading
                )
                
                # 保存价格和趋势
                await self.plugin.put_kv_data(price_key, new_price)
                await self.plugin.put_kv_data(trend_key, new_trend)
                
                # 更新日内高低
                if trading:
                    high_key = f"stock_high:{stock_name}"
                    low_key = f"stock_low:{stock_name}"
                    high = await self.plugin.get_kv_data(high_key, new_price)
                    low = await self.plugin.get_kv_data(low_key, new_price)
                    if new_price > high:
                        await self.plugin.put_kv_data(high_key, new_price)
                    if new_price < low:
                        await self.plugin.put_kv_data(low_key, new_price)
                
                # 记录历史
                history_key = f"stock_history:{stock_name}"
                history = await self.plugin.get_kv_data(history_key, [])
                history.append({"time": now.isoformat(), "price": new_price})
                if len(history) > 48:  # 保留最多2天数据
                    history = history[-48:]
                await self.plugin.put_kv_data(history_key, history)
                
                try:
                    self.plugin.logger.info(
                        f"股票更新: {stock_name} ¥{current_price:.2f} -> ¥{new_price:.2f} | {msg}"
                    )
                except Exception as log_err:
                    self.plugin.logger.error(
                        f"股票日志格式错误: stock={stock_name}, current_price={current_price!r}, new_price={new_price!r}, msg={msg!r}, err={log_err}"
                    )
        except Exception as e:
            self.plugin.logger.error(f"股票更新失败: {e}")

    # ========================================================
    # 每日报告
    # ========================================================

    async def _send_daily_reports(self, cst_now):
        """发送每日报告（群组+个人）"""
        date_str = cst_now.strftime("%Y-%m-%d")
        today_key = date_str

        # 获取所有用户
        users = await self.plugin._store.get_all_users()

        # 按群组分组
        group_users: dict[str, list] = {}
        for user_id, user in users.items():
            for gid in user.get("groups", []):
                if gid not in group_users:
                    group_users[gid] = []
                group_users[gid].append((user_id, user))

        # 发送群组日报
        for group_id, members in group_users.items():
            config = await self.plugin._get_group_config(group_id)
            if not config.get("enabled", False):
                continue
            subscribers = config.get("subscribers", [])
            active = [u for u in members if u[0] in subscribers]
            if not active and subscribers:
                continue

            report = self.plugin._generate_group_daily_report(
                group_id, members, 0, [], date_str, today_key
            )
            try:
                from astrbot.api.star import StarTools
                from astrbot.core.message.message_event_result import MessageChain
                await StarTools.send_message_by_id(
                    "GroupMessage", group_id,
                    MessageChain().message(report)
                )
                self.plugin.logger.info(f"群 {group_id} 日报已发送")
            except Exception as e:
                self.plugin.logger.error(f"群 {group_id} 日报发送失败: {e}")

        # 发送个人日报
        for user_id, user in users.items():
            settings = user.get("settings", {})
            if not settings.get("sub_personal_daily", False):
                continue

            report = self.plugin._generate_personal_report(user, date_str, today_key)
            try:
                from astrbot.api.star import StarTools
                from astrbot.core.message.message_event_result import MessageChain
                await StarTools.send_message_by_id(
                    "PrivateMessage", user_id,
                    MessageChain().message(report)
                )
                self.plugin.logger.info(f"用户 {user_id} 个人日报已发送")
            except Exception as e:
                self.plugin.logger.error(f"用户 {user_id} 个人日报发送失败: {e}")

    # ========================================================
    # 状态持久化
    # ========================================================
    
    async def _save_tick_state(self, now: datetime):
        """保存触发器状态"""
        state = {
            "last_hourly_trigger": now.isoformat(),
            "last_daily_trigger": now.date().isoformat(),
            "cron_states": self._cron_states.copy()
        }
        await self.plugin.put_kv_data(TICK_STATE_KEY, state)
    
    async def load_tick_state(self):
        """加载触发器状态（插件初始化时调用）"""
        state = await self.plugin.get_kv_data(TICK_STATE_KEY, None)
        if state:
            last_hourly = state.get("last_hourly_trigger")
            if last_hourly:
                dt = datetime.fromisoformat(last_hourly)
                self._last_hour = dt.hour
            self._last_day = state.get("last_daily_trigger")
            self._cron_states = state.get("cron_states", {})
            self.plugin.logger.info(f"加载触发器状态: last_hour={self._last_hour}, last_day={self._last_day}")
