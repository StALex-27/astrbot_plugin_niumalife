"""
Tick结算系统模块 v2
统一处理工作/睡眠/学习/娱乐等状态的定时结算
基于 tick (分钟) 精度，支持时间触发器

主要改动:
- 使用 tick (分钟) 而非 hour (小时) 作为结算单位
- 新增统一时间触发系统 (每小时/每日/Cron)
- 支持停机恢复和精确计时
"""
from datetime import datetime, timezone
from typing import Optional
import asyncio
import math

from .constants import TICKS_PER_HOUR


# ============================================================
# 常量
# ============================================================

class TickType:
    """Tick类型"""
    WORK = "工作"
    SLEEP = "睡眠"
    LEARN = "学习"
    ENTERTAIN = "娱乐"


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
            action_type: 动作类型 (TickType.WORK等)
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
        return TickType.WORK
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理工作tick"""
        from .constants import JOBS
        from .buff import calc_income_multi, calc_cost_multi, get_fixed_bonus
        
        action_type = detail.get("action_type")
        if action_type != TickType.WORK:
            return False
        
        job_name = detail.get("data", {}).get("job_name")
        job = JOBS.get(job_name)
        if not job:
            return True  # 无效工作，直接结束
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 每分钟结算
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            # 获取当前属性
            attrs = user["attributes"]
            checkin = user.get("checkin", {})
            active_buffs = checkin.get("active_buffs", [])
            
            # 计算加成
            income_multi = calc_income_multi(active_buffs)
            cost_multi = calc_cost_multi(active_buffs)
            fixed_bonus = get_fixed_bonus(active_buffs)
            
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
            
            # 计算效率
            efficiency = 1.0
            if attrs["satiety"] < 20:
                efficiency *= 0.7
            
            # 每分钟获得金币
            gold_per_tick = job.get("hourly_wage", 20) / TICKS_PER_HOUR * efficiency * income_multi
            gold_earned = int(gold_per_tick) + int(fixed_bonus / TICKS_PER_HOUR)
            detail["earned_gold"] += gold_earned
            user["gold"] += gold_earned
            
            user["attributes"] = attrs
        
        # 如果超过1分钟没更新，保存一次
        if ticks_since_last >= 1.0:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        # 检查是否完成
        if completed >= planned:
            # 记录履历
            hours = planned / TICKS_PER_HOUR
            user.setdefault("records", []).append({
                "type": "工作",
                "detail": f"完成了{job_name}{hours}小时",
                "gold_change": detail["earned_gold"],
                "time": now.isoformat(),
            })
            
            # 消耗 job_count 类型的 buff
            buffs = checkin.get("active_buffs", [])
            remaining_buffs = []
            from .buff import BuffManager, BuffLimit
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
        return TickType.SLEEP
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理睡眠tick"""
        from .constants import RESIDENCES, MAX_ATTRIBUTE
        
        action_type = detail.get("action_type")
        if action_type != TickType.SLEEP:
            return False
        
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES["桥下"])
        sleep_bonus = res_info.get("sleep_bonus", 1.0)
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        # 每分钟恢复
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            
            # 每分钟恢复（按比例）
            strength_rec = res_info.get("strength_recovery", 5) / TICKS_PER_HOUR * sleep_bonus * 1.5
            energy_rec = res_info.get("energy_recovery", 5) / TICKS_PER_HOUR * sleep_bonus * 1.5
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
        return TickType.LEARN
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理学习tick"""
        from .constants import COURSES
        from .buff import calc_exp_multi
        
        action_type = detail.get("action_type")
        if action_type != TickType.LEARN:
            return False
        
        course_name = detail.get("data", {}).get("course_name")
        course = COURSES.get(course_name)
        if not course:
            return True
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        exp_multi = calc_exp_multi(active_buffs)
        
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
            exp_per_tick = course.get("exp_per_hour", 10) / TICKS_PER_HOUR * exp_multi
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
            user.setdefault("records", []).append({
                "type": "学习",
                "detail": f"完成了{course_name}{hours}小时",
                "gold_change": 0,
                "time": now.isoformat(),
            })
            return True
        
        return False


# ============================================================
# EntertainTickProcessor - 娱乐处理器
# ============================================================

class EntertainTickProcessor(TickProcessor):
    """娱乐Tick处理器"""
    
    def get_action_type(self) -> str:
        return TickType.ENTERTAIN
    
    async def process(
        self, user_id: str, user: dict, detail: dict, now: datetime
    ) -> bool:
        """处理娱乐tick"""
        from .constants import ENTERTAINMENTS
        
        action_type = detail.get("action_type")
        if action_type != TickType.ENTERTAIN:
            return False
        
        entertainment_name = detail.get("data", {}).get("entertainment_name")
        entertainment = ENTERTAINMENTS.get(entertainment_name)
        if not entertainment:
            return True
        
        ticks_since_last = ActionDetail.get_ticks_since_last_tick(detail, now)
        planned = detail["planned_ticks"]
        completed = detail["completed_ticks"]
        
        while ticks_since_last >= 1.0 and completed < planned:
            ticks_since_last -= 1.0
            completed += 1
            
            attrs = user["attributes"]
            
            # 每分钟消耗金币
            cost_per_tick = entertainment.get("cost_per_hour", 10) / TICKS_PER_HOUR
            user["gold"] = max(0, user["gold"] - cost_per_tick)
            
            # 每分钟恢复/消耗
            attrs["mood"] = min(100, attrs["mood"] + entertainment.get("restore_mood", 15) / TICKS_PER_HOUR)
            attrs["strength"] = max(0, attrs["strength"] - entertainment.get("consume_strength", 5) / TICKS_PER_HOUR)
            attrs["energy"] = max(0, attrs["energy"] - entertainment.get("consume_energy", 3) / TICKS_PER_HOUR)
            
            user["attributes"] = attrs
        
        if ticks_since_last >= 1.0:
            detail["completed_ticks"] = completed
            ActionDetail.update_tick(detail, now)
            user["action_detail"] = detail
            await self.plugin._store.update_user(user_id, user)
        
        if completed >= planned:
            hours = planned / TICKS_PER_HOUR
            user.setdefault("records", []).append({
                "type": "娱乐",
                "detail": f"完成了{entertainment_name}{hours}小时",
                "gold_change": -entertainment.get("cost_per_hour", 10) * planned / TICKS_PER_HOUR,
                "time": now.isoformat(),
            })
            return True
        
        return False


# ============================================================
# TickManager - Tick 管理器 + 时间触发器
# ============================================================

class TickManager:
    """Tick管理器 - 包含用户Tick和时间触发器"""
    
    def __init__(self, plugin):
        self.plugin = plugin
        self._processors = {
            TickType.WORK: WorkTickProcessor(plugin),
            TickType.SLEEP: SleepTickProcessor(plugin),
            TickType.LEARN: LearnTickProcessor(plugin),
            TickType.ENTERTAIN: EntertainTickProcessor(plugin),
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
            completed = detail["completed_ticks"]
            detail["completed_ticks"] = completed
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
        """Cron触发 - 按精确时间表"""
        # 每日结算: 23:30
        cron_key = "daily_settlement"
        last_trigger = self._cron_states.get(cron_key)
        
        if now.hour == 23 and now.minute == 30:
            if last_trigger is None or last_trigger != "23:30":
                self.plugin.logger.info("Cron触发: 每日结算")
                await self.plugin._do_daily_settlement()
                self._cron_states[cron_key] = "23:30"
                await self._save_tick_state(now)
    
    # ========================================================
    # 股票系统
    # ========================================================
    
    async def _update_stocks(self, now: datetime):
        """更新股票价格"""
        from .stock import trigger_stock_event
        from .constants import STOCKS
        
        try:
            for stock_name, stock_info in STOCKS.items():
                # 获取当前价格（从KV存储或使用基准价）
                price_key = f"stock_price:{stock_name}"
                current_price = await self.plugin.get_kv_data(price_key, None)
                
                if current_price is None:
                    current_price = stock_info.get("base_price", 100)
                
                # 触发随机事件更新价格
                new_price, msg = trigger_stock_event(stock_name, current_price)
                
                # 保存新价格
                await self.plugin.put_kv_data(price_key, new_price)
                
                # 保存价格历史
                history_key = f"stock_history:{stock_name}"
                history = await self.plugin.get_kv_data(history_key, [])
                history.append({
                    "time": now.isoformat(),
                    "price": new_price
                })
                # 保留最近30条历史
                if len(history) > 30:
                    history = history[-30:]
                await self.plugin.put_kv_data(history_key, history)
                
                self.plugin.logger.info(f"股票更新: {stock_name} ${current_price:.2f} -> ${new_price:.2f} | {msg}")
        except Exception as e:
            self.plugin.logger.error(f"股票更新失败: {e}")
    
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
