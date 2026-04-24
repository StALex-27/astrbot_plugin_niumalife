"""
Tick结算系统模块
统一处理工作/睡眠/学习/娱乐等状态的定时结算
支持停机恢复和精确计时
"""
from datetime import datetime, timezone
from typing import Optional, Callable
import asyncio


class TickType:
    """Tick类型"""
    WORK = "工作"
    SLEEP = "睡眠"
    LEARN = "学习"
    ENTERTAIN = "娱乐"


class ActionDetail:
    """统一的ActionDetail结构"""
    
    @staticmethod
    def create(action_type: str, hours: int, start_time: datetime, **kwargs) -> dict:
        """创建ActionDetail
        
        Args:
            action_type: 动作类型 (TickType.WORK等)
            hours: 计划时长（小时）
            start_time: 开始时间
            **kwargs: 额外参数
                - job_name: 工作名称（工作用）
                - course_name: 课程名称（学习用）
                - entertainment_name: 娱乐名称（娱乐用）
                - base_gold: 每小时基础金币（工作和娱乐用）
                - consume_*: 各属性消耗
                - restore_*: 各属性恢复
        
        Returns:
            dict: 动作详情字典
        """
        detail = {
            "action_type": action_type,
            "start_time": start_time.isoformat(),
            "planned_hours": hours,
            "hours_completed": 0,
            "last_tick": start_time.isoformat(),  # 上次结算时间
            "earned_gold": 0,  # 已获得金币（累计）
            "data": kwargs,
        }
        return detail
    
    @staticmethod
    def get_elapsed_hours(detail: dict, now: datetime) -> float:
        """获取自开始以来的总小时数（精确）"""
        start = datetime.fromisoformat(detail["start_time"])
        # 确保时区一致
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return (now - start).total_seconds() / 3600
    
    @staticmethod
    def get_hours_since_last_tick(detail: dict, now: datetime) -> float:
        """获取自上次tick以来的小时数（精确）"""
        last_tick = datetime.fromisoformat(detail.get("last_tick", detail["start_time"]))
        if last_tick.tzinfo is None:
            last_tick = last_tick.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return (now - last_tick).total_seconds() / 3600
    
    @staticmethod
    def is_expired(detail: dict, now: datetime) -> bool:
        """检查是否已过期（完成）"""
        elapsed = ActionDetail.get_elapsed_hours(detail, now)
        return elapsed >= detail["planned_hours"]
    
    @staticmethod
    def update_tick(detail: dict, now: datetime):
        """更新结算时间"""
        detail["last_tick"] = now.isoformat()


class TickProcessor:
    """Tick处理器基类"""
    
    def __init__(self, plugin):
        self.plugin = plugin
    
    async def process(self, user_id: str, user: dict, detail: dict, now: datetime) -> bool:
        """
        处理一个tick
        返回True表示动作完成，False表示继续
        
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


class WorkTickProcessor(TickProcessor):
    """工作Tick处理器"""
    
    def get_action_type(self) -> str:
        return TickType.WORK
    
    async def process(self, user_id: str, user: dict, detail: dict, now: datetime) -> bool:
        """处理工作tick"""
        from ..modules.constants import JOBS
        
        action_type = detail.get("action_type")
        if action_type != TickType.WORK:
            return False
        
        job_name = detail.get("data", {}).get("job_name")
        job = JOBS.get(job_name)
        if not job:
            return True  # 无效工作，直接结束
        
        # 计算时间
        hours_since_start = ActionDetail.get_elapsed_hours(detail, now)
        hours_since_last = ActionDetail.get_hours_since_last_tick(detail, now)
        planned = detail["planned_hours"]
        completed = detail["hours_completed"]
        
        # 每小时结算
        current_hour = int(hours_since_start)
        while completed < current_hour and completed < planned:
            completed += 1
            
            # 获取当前属性（可能已被之前tick修改）
            attrs = user["attributes"]
            
            # 获取buff加成
            checkin = user.get("checkin", {})
            active_buffs = checkin.get("active_buffs", [])
            from ..modules.buff import calc_income_multi, calc_cost_multi, get_fixed_bonus
            
            income_multi = calc_income_multi(active_buffs)
            cost_multi = calc_cost_multi(active_buffs)
            fixed_bonus = get_fixed_bonus(active_buffs)
            
            # 消耗属性
            consume_strength = int(job.get("consume_strength", 10) * cost_multi)
            consume_energy = int(job.get("consume_energy", 10) * cost_multi)
            consume_mood = job.get("consume_mood", 5)
            consume_health = job.get("consume_health", 2)
            consume_satiety = job.get("consume_satiety", 10) * 0.5
            
            attrs["strength"] = max(0, attrs["strength"] - consume_strength)
            attrs["energy"] = max(0, attrs["energy"] - consume_energy)
            attrs["mood"] = max(0, attrs["mood"] - consume_mood)
            attrs["health"] = max(0, attrs["health"] - consume_health)
            attrs["satiety"] = max(0, attrs["satiety"] - consume_satiety)
            
            # 计算效率
            efficiency = 1.0
            if attrs["satiety"] < 20:
                efficiency *= 0.7
            
            # 获得金币
            gold_earned = int(job.get("hourly_wage", 20) * efficiency * income_multi) + fixed_bonus
            detail["earned_gold"] += gold_earned
            user["gold"] += gold_earned
            
            user["attributes"] = attrs
            self.plugin._store.update_user(user_id, user)
            
            self.plugin.logger.info(
                f"用户 {user['nickname']} 完成第{completed}小时工作，"
                f"获得{gold_earned}金币(收益x{income_multi:.1f})，体力{attrs['strength']}"
            )
        
        # 更新完成数
        detail["hours_completed"] = completed
        ActionDetail.update_tick(detail, now)
        
        # 检查是否完成
        if completed >= planned:
            # 记录履历
            user.setdefault("records", []).append({
                "type": "工作",
                "detail": f"完成了{job_name}{planned}小时",
                "gold_change": detail["earned_gold"],
                "time": now.isoformat(),
            })
            
            # 消耗job_count类型的buff
            checkin = user.get("checkin", {})
            buffs = checkin.get("active_buffs", [])
            remaining_buffs = []
            from ..modules.buff import BuffManager, BuffLimit
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
        
        # 未完成，保存进度
        user["action_detail"] = detail
        self.plugin._store.update_user(user_id, user)
        return False


class SleepTickProcessor(TickProcessor):
    """睡眠Tick处理器"""
    
    def get_action_type(self) -> str:
        return TickType.SLEEP
    
    async def process(self, user_id: str, user: dict, detail: dict, now: datetime) -> bool:
        """处理睡眠tick"""
        from ..modules.constants import RESIDENCES, MAX_ATTRIBUTE
        
        action_type = detail.get("action_type")
        if action_type != TickType.SLEEP:
            return False
        
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES["桥下"])
        sleep_bonus = res_info.get("sleep_bonus", 1.0)
        
        # 计算时间
        hours_since_start = ActionDetail.get_elapsed_hours(detail, now)
        hours_since_last = ActionDetail.get_hours_since_last_tick(detail, now)
        planned = detail["planned_hours"]
        completed = detail["hours_completed"]
        
        # 每小时恢复
        current_hour = int(hours_since_start)
        while completed < current_hour and completed < planned:
            completed += 1
            
            attrs = user["attributes"]
            attrs["strength"] = min(MAX_ATTRIBUTE, attrs["strength"] + int(res_info.get("strength_recovery", 5) * sleep_bonus * 1.5))
            attrs["energy"] = min(MAX_ATTRIBUTE, attrs["energy"] + int(res_info.get("energy_recovery", 5) * sleep_bonus * 1.5))
            attrs["mood"] = min(MAX_ATTRIBUTE, attrs["mood"] + res_info.get("mood_recovery", 2) * sleep_bonus)
            attrs["health"] = min(MAX_ATTRIBUTE, attrs["health"] + res_info.get("health_recovery", 2) * sleep_bonus)
            # 睡眠时饱食消耗减半
            attrs["satiety"] = max(0, attrs["satiety"] - 5 * 0.5)
            
            user["attributes"] = attrs
            self.plugin._store.update_user(user_id, user)
            
            self.plugin.logger.info(
                f"用户 {user['nickname']} 睡眠第{completed}小时，"
                f"体力{attrs['strength']} 精力{attrs['energy']}"
            )
        
        # 更新完成数
        detail["hours_completed"] = completed
        ActionDetail.update_tick(detail, now)
        
        # 检查是否完成
        if completed >= planned:
            return True
        
        # 未完成，保存进度
        user["action_detail"] = detail
        self.plugin._store.update_user(user_id, user)
        return False


class LearnTickProcessor(TickProcessor):
    """学习Tick处理器"""
    
    def get_action_type(self) -> str:
        return TickType.LEARN
    
    async def process(self, user_id: str, user: dict, detail: dict, now: datetime) -> bool:
        """处理学习tick"""
        from ..modules.constants import COURSES
        from ..modules.buff import calc_exp_multi
        
        action_type = detail.get("action_type")
        if action_type != TickType.LEARN:
            return False
        
        course_name = detail.get("data", {}).get("course_name")
        course = COURSES.get(course_name)
        if not course:
            return True
        
        # 计算时间
        hours_since_start = ActionDetail.get_elapsed_hours(detail, now)
        planned = detail["planned_hours"]
        completed = detail["hours_completed"]
        
        # 获取exp加成
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        exp_multi = calc_exp_multi(active_buffs)
        
        # 每小时学习
        current_hour = int(hours_since_start)
        while completed < current_hour and completed < planned:
            completed += 1
            
            # 消耗属性
            attrs = user["attributes"]
            attrs["strength"] = max(0, attrs["strength"] - course.get("consume_strength", 3))
            attrs["energy"] = max(0, attrs["energy"] - course.get("consume_energy", 8))
            attrs["mood"] = max(0, attrs["mood"] - course.get("consume_mood", 5))
            attrs["satiety"] = max(0, attrs["satiety"] - course.get("consume_satiety", 5))
            
            # 获得经验
            exp_gained = int(course.get("exp_per_hour", 10) * exp_multi)
            user.setdefault("exp", 0)
            user["exp"] = user.get("exp", 0) + exp_gained
            
            user["attributes"] = attrs
            self.plugin._store.update_user(user_id, user)
            
            self.plugin.logger.info(
                f"用户 {user['nickname']} 学习{completed}小时，"
                f"获得{exp_gained}经验(exp x{exp_multi:.1f})"
            )
        
        # 更新完成数
        detail["hours_completed"] = completed
        ActionDetail.update_tick(detail, now)
        
        # 检查是否完成
        if completed >= planned:
            user.setdefault("records", []).append({
                "type": "学习",
                "detail": f"完成了{course_name}{planned}小时",
                "gold_change": 0,
                "time": now.isoformat(),
            })
            return True
        
        # 未完成
        user["action_detail"] = detail
        self.plugin._store.update_user(user_id, user)
        return False


class EntertainTickProcessor(TickProcessor):
    """娱乐Tick处理器"""
    
    def get_action_type(self) -> str:
        return TickType.ENTERTAIN
    
    async def process(self, user_id: str, user: dict, detail: dict, now: datetime) -> bool:
        """处理娱乐tick"""
        from ..modules.constants import ENTERTAINMENTS
        
        action_type = detail.get("action_type")
        if action_type != TickType.ENTERTAIN:
            return False
        
        entertainment_name = detail.get("data", {}).get("entertainment_name")
        entertainment = ENTERTAINMENTS.get(entertainment_name)
        if not entertainment:
            return True
        
        # 计算时间
        hours_since_start = ActionDetail.get_elapsed_hours(detail, now)
        planned = detail["planned_hours"]
        completed = detail["hours_completed"]
        
        # 每小时娱乐
        current_hour = int(hours_since_start)
        while completed < current_hour and completed < planned:
            completed += 1
            
            attrs = user["attributes"]
            
            # 消耗金币
            cost = entertainment.get("cost_per_hour", 10)
            user["gold"] = max(0, user["gold"] - cost)
            
            # 恢复心情，消耗体力
            attrs["mood"] = min(100, attrs["mood"] + entertainment.get("restore_mood", 15))
            attrs["strength"] = max(0, attrs["strength"] - entertainment.get("consume_strength", 5))
            attrs["energy"] = max(0, attrs["energy"] - entertainment.get("consume_energy", 3))
            
            user["attributes"] = attrs
            self.plugin._store.update_user(user_id, user)
            
            self.plugin.logger.info(
                f"用户 {user['nickname']} 娱乐{completed}小时({entertainment_name})，"
                f"心情{attrs['mood']} 体力{attrs['strength']}"
            )
        
        # 更新完成数
        detail["hours_completed"] = completed
        ActionDetail.update_tick(detail, now)
        
        # 检查是否完成
        if completed >= planned:
            user.setdefault("records", []).append({
                "type": "娱乐",
                "detail": f"完成了{entertainment_name}{planned}小时",
                "gold_change": -entertainment.get("cost_per_hour", 10) * planned,
                "time": now.isoformat(),
            })
            return True
        
        # 未完成
        user["action_detail"] = detail
        self.plugin._store.update_user(user_id, user)
        return False


class TickManager:
    """Tick管理器"""
    
    def __init__(self, plugin):
        self.plugin = plugin
        self._processors = {
            TickType.WORK: WorkTickProcessor(plugin),
            TickType.SLEEP: SleepTickProcessor(plugin),
            TickType.LEARN: LearnTickProcessor(plugin),
            TickType.ENTERTAIN: EntertainTickProcessor(plugin),
        }
    
    async def process_user_actions(self, user_id: str, user: dict, now: datetime):
        """处理用户的所有进行中动作
        
        统一处理工作/睡眠/学习/娱乐状态的结算
        支持停机恢复后的补算
        """
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
            self.plugin._store.update_user(user_id, user)
            return
        
        # 检查是否已过期（完成）
        if ActionDetail.is_expired(detail, now):
            # 已过期但未清理（插件停机期间完成），立即处理
            self.plugin.logger.info(f"用户 {user['nickname']} 的{action_type}在停机期间完成，清理状态")
            completed = detail["planned_hours"]
            detail["hours_completed"] = completed
            user["status"] = "空闲"
            user["current_action"] = None
            user["action_detail"] = None
            self.plugin._store.update_user(user_id, user)
            return
        
        # 正常处理
        try:
            completed = await processor.process(user_id, user, detail, now)
            if completed:
                user["status"] = "空闲"
                user["current_action"] = None
                user["action_detail"] = None
                self.plugin._store.update_user(user_id, user)
                self.plugin.logger.info(f"用户 {user['nickname']} 的{action_type}完成")
        except Exception as e:
            self.plugin.logger.error(f"处理{action_type}时出错: {e}")
    
    async def tick_all_users(self, now: datetime):
        """Tick所有用户"""
        users = self.plugin._store._load_users()
        for user_id, user in users.items():
            try:
                await self.process_user_actions(user_id, user, now)
            except Exception as e:
                self.plugin.logger.error(f"Tick用户{user_id}时出错: {e}")
