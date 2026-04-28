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
TICK_TYPE_SLEEP = "睡眠"
TICK_TYPE_LEARN = "学习"
TICK_TYPE_ENTERTAIN = "娱乐"


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
            start = start.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
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
            last_tick = last_tick.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
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
    """工作Tick处理器"""
    
    def get_action_type(self) -> str:
        return TICK_TYPE_WORK
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理工作tick"""
        
        action_type = detail.get("action_type")
        if action_type != TICK_TYPE_WORK:
            return False
        
        job_name = detail.get("data", {}).get("job_name")
        job = JOBS.get(job_name)
        if not job:
            return True  # 无效工作，直接结束
        
        # 检查是否力竭
        pressure_type = JOB_PRESSURE_TYPE.get(job_name, "body")
        if is_exhausted(user, pressure_type):
            # 力竭状态，直接取消工作
            return True
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 获取装备效果加成
        effects = calc_equipped_effects(user)
        work_income_bonus = effects.get("work_income_bonus", 0) / 100.0
        
        # 获取压力惩罚
        pressure = user.get(f"{pressure_type}_pressure", 0)
        pressure_penalty = 1.0 - get_pressure_penalty(pressure)
        
        # 每分钟结算
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            checkin = user.get("checkin", {})
            active_buffs = checkin.get("active_buffs", [])
            
            income_multi = calc_income_multi(active_buffs)
            cost_multi = calc_cost_multi(active_buffs)
            fixed_bonus = get_fixed_bonus(active_buffs)
            debuff_penalty = calc_debuff_income_penalty(user)
            
            # 每分钟消耗（按比例）
            consume_strength = job.get("consume_strength", 10) / TICKS_PER_HOUR * cost_multi
            consume_energy = job.get("consume_energy", 10) / TICKS_PER_HOUR * cost_multi
            consume_mood = job.get("consume_mood", 5) / TICKS_PER_HOUR
            consume_health = job.get("consume_health", 2) / TICKS_PER_HOUR
            consume_satiety = job.get("consume_satiety", 10) * 0.5 / TICKS_PER_HOUR
            
            attrs["strength"] = max(0, attrs["strength"] - consume_strength)
            attrs["energy"] = max(0, attrs["energy"] - consume_energy)
            attrs["mood"] = max(0, attrs["mood"] - consume_mood)
            attrs["health"] = max(0, attrs["health"] - consume_health)
            attrs["satiety"] = max(0, attrs["satiety"] - consume_satiety)
            
            # 计算效率 = 基础效率 * 压力惩罚 * debuff惩罚
            efficiency = pressure_penalty * debuff_penalty
            if attrs["satiety"] < 20:
                efficiency *= 0.7
            
            # 每分钟获得金币
            gold_per_tick = job.get("hourly_wage", 20) / TICKS_PER_HOUR * efficiency * income_multi * (1 + work_income_bonus)
            gold_earned = int(gold_per_tick) + int(fixed_bonus / TICKS_PER_HOUR)
            detail["earned_gold"] += gold_earned
            user["gold"] += gold_earned
            
            user["attributes"] = attrs
        
        # 累积压力（每小时累积一次，按 tick 数均分）
        pressure_rate_per_tick = JOB_PRESSURE_RATE.get(job_name, 3) / TICKS_PER_HOUR
        pressure_to_add = pressure_rate_per_tick * ticks_since_last if ticks_since_last >= 1.0 else 0
        if pressure_to_add > 0:
            accumulate_pressure(user, pressure_type, pressure_to_add)
        
        # 如果超过1分钟没更新，保存一次
        if ticks_since_last >= 1.0:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        # 检查是否完成
        if completed >= planned:
            hours = planned / TICKS_PER_HOUR
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
            
            return True
        
        return False


# ============================================================
# SleepTickProcessor - 睡眠处理器
# ============================================================

class SleepTickProcessor(TickProcessor):
    """睡眠Tick处理器"""
    
    def get_action_type(self) -> str:
        return TICK_TYPE_SLEEP
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理睡眠tick"""
        
        action_type = detail.get("action_type")
        if action_type != TICK_TYPE_SLEEP:
            return False
        
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES["桥下"])
        sleep_bonus = res_info.get("sleep_bonus", 1.0)
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 装备效果加成
        effects = calc_equipped_effects(user)
        sleep_strength_bonus = effects.get("sleep_strength_bonus", 0) / 100.0
        sleep_energy_bonus = effects.get("sleep_energy_bonus", 0) / 100.0
        
        # 每分钟恢复
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            
            # 每分钟恢复（按比例）
            strength_rec = res_info.get("strength_recovery", 5) / TICKS_PER_HOUR * sleep_bonus * 1.5 * (1 + sleep_strength_bonus)
            energy_rec = res_info.get("energy_recovery", 5) / TICKS_PER_HOUR * sleep_bonus * 1.5 * (1 + sleep_energy_bonus)
            mood_rec = res_info.get("mood_recovery", 2) / TICKS_PER_HOUR * sleep_bonus
            health_rec = res_info.get("health_recovery", 2) / TICKS_PER_HOUR * sleep_bonus
            
            attrs["strength"] = min(MAX_ATTRIBUTE, attrs["strength"] + strength_rec)
            attrs["energy"] = min(MAX_ATTRIBUTE, attrs["energy"] + energy_rec)
            attrs["mood"] = min(MAX_ATTRIBUTE, attrs["mood"] + mood_rec)
            attrs["health"] = min(MAX_ATTRIBUTE, attrs["health"] + health_rec)
            # 睡眠时饱食消耗减半
            attrs["satiety"] = max(0, attrs["satiety"] - 5 * 0.5 / TICKS_PER_HOUR)
            
            user["attributes"] = attrs
        
        if ticks_since_last >= 1.0:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        if completed >= planned:
            return True
        
        return False


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
        
        if ticks_since_last >= 1.0:
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
            
            return True
        
        if ticks_since_last >= 1.0:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        return False


# ============================================================
# TickManager - Tick 管理器 + 时间触发器
# ============================================================

class TickManager:
    """Tick管理器 - 包含用户Tick和时间触发器"""
    
    def __init__(self, plugin):
        self.plugin = plugin
        self._processors = {
            TICK_TYPE_WORK: WorkTickProcessor(plugin),
            TICK_TYPE_SLEEP: SleepTickProcessor(plugin),
            TICK_TYPE_LEARN: LearnTickProcessor(plugin),
            TICK_TYPE_ENTERTAIN: EntertainTickProcessor(plugin),
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
        for user_id, user in users.items():
            try:
                await self.process_user_actions(user_id, user, now)
                
                # 被动效果：仅对空闲状态用户生效
                if user.get("status") == UserStatus.FREE.value:
                    effects = calc_equipped_effects(user)
                    attrs = user.get("attributes", {})
                    
                    # 被动心情恢复 (per tick/minute)
                    passive_mood = effects.get("passive_mood", 0)
                    if passive_mood > 0:
                        attrs["mood"] = min(100, attrs.get("mood", 100) + passive_mood)
                    
                    # 被动金币获取 (per tick/minute)
                    passive_gold = effects.get("passive_gold", 0)
                    if passive_gold > 0:
                        user["gold"] = user.get("gold", 0) + passive_gold
                    
                    user["attributes"] = attrs
                    await self.plugin._store.update_user(user_id, user)
                    
            except Exception as e:
                self.plugin.logger.error(f"Tick用户{user_id}时出错: {e}")
    
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
        cst = now.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))

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
        # UTC hour 转 CST hour：交易时段 CST 08-20 = UTC 00-12
        cst_hour = (now.hour + 8) % 24
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
