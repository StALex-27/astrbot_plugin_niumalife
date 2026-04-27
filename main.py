"""
牛马人生 - AstrBot 打工群游戏
重构版本: 模块化命令 + DAO数据访问
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain

# 导入自定义模块
from .modules.constants import ITEMS, STOCKS, FOODS, RESIDENCES, JOBS, COURSES, ENTERTAINMENTS, MAX_ATTRIBUTE, INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS, TICKS_PER_HOUR
from .modules.user import DataStore, UserStatus, migrate_user_data
from .modules.status import StatusTransition
from .modules.skills import get_skill_level, exp_to_next_level
from .modules.checkin import (
    get_luck_rating, get_streak_reward, roll_lucky_drop,
    format_checkin_report, get_next_streak_threshold, BASE_DROP_CHANCE
)
from .modules.buff import (
    BuffManager, BuffType, BuffLimit,
    ALL_BUFFS, create_buff, consume_buff,
    calc_income_multi, calc_cost_multi, calc_exp_multi, get_fixed_bonus,
    roll_buff, format_buffs, get_effective_buffs
)
from .modules.tick import TickManager, ActionDetail, TICK_TYPE_SLEEP
from .modules.renderer import CardRenderer

# 导入命令模块
from .src.commands import register_all_commands


# ============================================================
# 常量定义
# ============================================================

TEST_MODE = False
TEST_TIME_SCALE = 0.1

# 不再使用，保留用于兼容性
# DAILY_SETTLEMENT_HOUR = 23
# DAILY_SETTLEMENT_MINUTE = 30

SATIETY_CONSUMPTION_RATE = 0.05

GROUP_ID = ""

# KV Storage Keys
GROUP_CONFIG_PREFIX = "group_config:"
GROUP_DAILY_PREFIX = "group_daily:"

# 群组默认配置
DEFAULT_GROUP_CONFIG = {
    "enabled": False,
    "daily_report_hour": 23,
    "daily_report_minute": 0,
    "subscribers": [],
    "total_gold_earned": 0,
    "total_members": 0,
}
DAILY_SETTLEMENT_KV_KEY = "__daily_settlement__:last_date"


# ============================================================
# 通用指令解析器
# ============================================================

class CommandParser:
    @staticmethod
    def parse(event: AstrMessageEvent) -> tuple[str, list[str]]:
        raw = event.message_str.strip()
        parts = raw.split()
        if not parts:
            return "", []
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        return cmd, args

    @staticmethod
    def get_string(args: list[str], index: int, default: str = "") -> str:
        return args[index] if index < len(args) else default

    @staticmethod
    def get_int(args: list[str], index: int, default: int = 0) -> tuple[bool, int, str]:
        if index >= len(args):
            return False, default, "参数不足"
        try:
            return True, int(args[index]), ""
        except ValueError:
            return False, default, f"「{args[index]}」不是有效数字"

    @staticmethod
    def get_range(args: list[str], index: int, min_val: int, max_val: int) -> tuple[bool, int, str]:
        success, value, err = CommandParser.get_int(args, index)
        if not success:
            return False, value, err
        if value < min_val or value > max_val:
            return False, value, f"数值必须在 {min_val}-{max_val} 之间"
        return True, value, ""


# ============================================================
# 插件主类
# ============================================================

@register(
    "niumalife",
    "海獭 🦦",
    "牛马人生 - 打工群文字模拟经营游戏",
    "0.1.7"
)
class NiumaLife(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self.context = context

        self._data_dir = StarTools.get_data_dir("niumalife")
        self._store = DataStore(self)
        self._parser = CommandParser()
        self.logger = logger

        self._background_tasks: list[asyncio.Task] = []
        self._tick_interval = 60
        self._tick_manager = TickManager(self)
        self._renderer = CardRenderer()

        self._last_hourly_tick = datetime.now(timezone.utc)
        self._last_daily_tick = datetime.now(timezone.utc)
        
        # 商店状态（随机商品刷新）
        self._shop_state = {}

        # 注册所有命令
        register_all_commands(self)

    # ========================================================
    # 配置读取助手
    # ========================================================

    @property
    def test_mode(self) -> bool:
        """测试模式"""
        return getattr(self.config, 'test_mode', False)

    @property
    def test_time_scale(self) -> float:
        """测试模式时间倍率"""
        return getattr(self.config, 'test_time_scale', 0.1)

    def parse_time_config(self, time_str: str, default: tuple[int, int] = (23, 0)) -> tuple[int, int]:
        """
        解析 HH:MM 格式的时间配置
        
        Args:
            time_str: HH:MM 格式字符串
            default: 解析失败时的默认值
        Returns:
            (hour, minute) 元组
        """
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        except (ValueError, IndexError):
            pass
        return default

    @property
    def daily_settlement_time(self) -> tuple[int, int]:
        """每日结算时间 (hour, minute)"""
        time_str = getattr(self.config, 'daily_settlement_time', '23:30')
        return self.parse_time_config(time_str, (23, 30))

    @property
    def daily_report_time(self) -> tuple[int, int]:
        """群组日报发送时间 (hour, minute)"""
        time_str = getattr(self.config, 'daily_report_time', '23:00')
        return self.parse_time_config(time_str, (23, 0))

    async def initialize(self):
        global GROUP_ID
        logger.info("牛马人生插件初始化 - v0.1.7")

        config_file = self._data_dir / "config.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                GROUP_ID = config.get("group_id", "")
                if GROUP_ID:
                    logger.info(f"已加载群ID配置: {GROUP_ID}")

        # 加载触发器状态
        await self._tick_manager.load_tick_state()

        # 启动主循环
        task1 = asyncio.create_task(self._tick_loop())
        self._background_tasks.append(task1)

        logger.info("Tick系统已启动 (基于时间触发)")

    async def terminate(self):
        logger.info("牛马人生插件关闭")
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)

    # ========================================================
    # 工具方法 (供命令模块调用)
    # ========================================================

    def _check_skill_required(self, user_skills: dict, requirement: dict) -> bool:
        """检查技能是否满足要求"""
        for skill, level in requirement.items():
            user_skill = user_skills.get(skill, {})
            if isinstance(user_skill, dict):
                user_level = user_skill.get("level", 0)
            else:
                user_level = int(user_skill) if user_skill else 0
            if user_level < level:
                return False
        return True

    def _check_attribute_enough(self, attrs: dict, job: dict, hours: int) -> tuple[bool, str]:
        """检查属性是否足够"""
        if attrs["strength"] < job["consume_strength"] * hours * 0.5:
            return False, "体力不足"
        if attrs["energy"] < job["consume_energy"] * hours * 0.5:
            return False, "精力不足"
        if attrs["satiety"] < 10:
            return False, "饱食度过低,先吃点东西吧"
        return True, ""

    def _format_attributes(self, attrs: dict) -> str:
        """格式化属性显示"""
        return (
            f"❤️ 健康: {attrs.get('health', 0)}\n"
            f"💪 体力: {attrs.get('strength', 0)}\n"
            f"⚡ 精力: {attrs.get('energy', 0)}\n"
            f"😊 心情: {attrs.get('mood', 0)}\n"
            f"🍖 饱食: {attrs.get('satiety', 0)}"
        )

    def _format_profile(self, user: dict) -> str:
        """格式化档案显示"""
        attrs = user.get("attributes", {})
        checkin = user.get("checkin", {})

        luck_rating = get_luck_rating(checkin.get("last_luck", 50))

        # 格式化技能
        skills_lines = []
        skills = user.get("skills", {})
        if isinstance(skills, dict):
            for name, data in skills.items():
                lvl = data.get("level", 0) if isinstance(data, dict) else (int(data) if data else 0)
                exp = data.get("exp", 0) if isinstance(data, dict) else 0
                skills_lines.append(f"◆ {name} Lv.{lvl} (EXP: {exp})")

        skills_text = "\n".join(skills_lines) if skills_lines else "无"

        return (
            f"{'='*20}\n"
            f"【 牛马档案 】\n"
            f"{'='*20}\n"
            f"👤 {user.get('nickname', '未知')}\n"
            f"💰 金币: {user.get('gold', 0)}\n"
            f"🏠 住所: {user.get('residence', '桥下')}\n"
            f"📋 状态: {user.get('status', '空闲')}\n"
            f"{'='*20}\n"
            f"【 属性 】\n"
            f"{self._format_attributes(attrs)}\n"
            f"{'='*20}\n"
            f"【 签到 】\n"
            f"🔥 连续: {checkin.get('streak', 0)} 天\n"
            f"📅 总计: {checkin.get('total_days', 0)} 天\n"
            f"🎲 欧气: {luck_rating.get('name', '普通人')}\n"
            f"{'='*20}\n"
            f"【 技能 】\n"
            f"{skills_text}\n"
            f"{'='*20}"
        )

    def _check_attributes_effects(self, user: dict) -> list[str]:
        """检查属性异常并返回警告信息"""
        warnings = []
        attrs = user.get("attributes", {})

        if attrs.get("satiety", 100) < 20:
            warnings.append("⚠️ 饱食度过低!请及时进食")
        if attrs.get("mood", 100) < 20:
            warnings.append("⚠️ 心情过低!建议娱乐")
        if attrs.get("health", 100) < 50:
            warnings.append("⚠️ 健康偏低!注意休息")
        if attrs.get("energy", 100) < 20:
            warnings.append("⚠️ 精力不足!建议睡觉恢复")

        return warnings

    # ========================================================
    # 后台任务
    # ========================================================

    async def _tick_loop(self):
        """Tick主循环 - 每分钟检查一次"""
        while True:
            try:
                await asyncio.sleep(self._tick_interval)
                now = datetime.now(timezone.utc)

                # 处理所有空闲用户的被动恢复
                try:
                    await self._process_all_free_passive_recovery(now)
                except Exception as e:
                    logger.warning(f"_process_all_free_passive_recovery 异常: {type(e).__name__}: {str(e)}")

                # 检查是否需要自动睡觉
                try:
                    await self._check_night_auto_sleep(now)
                except Exception as e:
                    logger.warning(f"_check_night_auto_sleep 异常: {type(e).__name__}: {str(e)}")

                # 触发基于时间的事件（每小时/每日/Cron）
                try:
                    await self._tick_manager.trigger_time_based_events(now)
                except Exception as e:
                    logger.warning(f"trigger_time_based_events 异常: {type(e).__name__}: {str(e)}")

                # Tick 所有用户动作
                try:
                    await self._tick_manager.tick_all_users(now)
                except Exception as e:
                    logger.warning(f"tick_all_users 异常: {type(e).__name__}: {str(e)}")

                # 每小时数据保存
                try:
                    await self._hourly_data_save(now)
                except Exception as e:
                    logger.warning(f"_hourly_data_save 异常: {type(e).__name__}: {str(e)}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                try:
                    logger.error(f"Tick循环错误: {e}", exc_info=True)
                except Exception:
                    logger.error(f"Tick循环错误: {type(e).__name__}: {str(e)}")

    async def _process_all_free_passive_recovery(self, now: datetime):
        """处理所有空闲用户的被动恢复"""
        users = await self._store.get_all_users()
        for user_id, user in users.items():
            status = user.get("status")
            if status == UserStatus.HOSPITALIZED.value:
                await self._process_hospital(user_id, user, now)
            elif status == UserStatus.FREE.value:
                await self._process_free_passive_recovery(user_id, user, now)

    async def _process_hospital(self, user_id: str, user: dict, now: datetime):
        """处理住院状态用户"""
        from .modules.constants import (
            HOSPITAL_COST_PER_HOUR, HOSPITAL_HEALTH_PER_HOUR,
            HOSPITAL_STRENGTH_PER_HOUR, HOSPITAL_ENERGY_PER_HOUR,
            HOSPITAL_MOOD_TARGET, HOSPITAL_DISCHARGE_THRESHOLD
        )

        attrs = user.get("attributes", {})

        # 每小时消耗金币
        cost_per_tick = HOSPITAL_COST_PER_HOUR / TICKS_PER_HOUR
        user["gold"] = max(0, user.get("gold", 0) - cost_per_tick)

        # 每分钟恢复
        attrs["health"] = min(100, attrs.get("health", 0) + HOSPITAL_HEALTH_PER_HOUR / TICKS_PER_HOUR)
        attrs["strength"] = min(100, attrs.get("strength", 0) + HOSPITAL_STRENGTH_PER_HOUR / TICKS_PER_HOUR)
        attrs["energy"] = min(100, attrs.get("energy", 0) + HOSPITAL_ENERGY_PER_HOUR / TICKS_PER_HOUR)

        # 心情固定在 HOSPITAL_MOOD_TARGET
        current_mood = attrs.get("mood", 0)
        if current_mood > HOSPITAL_MOOD_TARGET:
            attrs["mood"] = max(HOSPITAL_MOOD_TARGET, current_mood - 1 / TICKS_PER_HOUR)
        elif current_mood < HOSPITAL_MOOD_TARGET:
            attrs["mood"] = min(HOSPITAL_MOOD_TARGET, current_mood + 1 / TICKS_PER_HOUR)

        user["attributes"] = attrs

        # 检查是否可以出院
        if attrs.get("health", 0) >= HOSPITAL_DISCHARGE_THRESHOLD:
            user["status"] = UserStatus.FREE
            user["current_action"] = None
            user["action_detail"] = None
            logger.info(f"用户 {user.get('nickname')} 康复出院")

        await self._store.update_user(user_id, user)

    async def _process_free_passive_recovery(self, user_id: str, user: dict, now: datetime):
        """处理单个空闲用户的被动恢复"""
        from .modules.debuff import (
            check_and_update_debuffs, calc_debuff_recovery_penalty,
            apply_debuff_strength_drain, decay_pressure
        )
        from .modules.constants import PRESSURE_DECAY_IDLE

        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES.get("桥下"))

        attrs = user.get("attributes", {})

        # 检查健康是否 <= 0 → 强制住院
        if attrs.get("health", 100) <= 0:
            user["status"] = UserStatus.HOSPITALIZED
            user["current_action"] = None
            user["action_detail"] = None
            await self._store.update_user(user_id, user)
            logger.info(f"用户 {user.get('nickname')} 健康归零，强制住院")
            return

        # 检查并更新 debuff
        debuff_changes = check_and_update_debuffs(user, now)

        # 计算 debuff 恢复惩罚
        recovery_penalty = calc_debuff_recovery_penalty(user)

        # 被动恢复 (每小时基础值 * 住所加成 * debuff惩罚)
        recovery_per_hour = 2
        attrs["health"] = min(MAX_ATTRIBUTE, attrs.get("health", 0) + recovery_per_hour * res_info.get("health_recovery", 1) * recovery_penalty)
        attrs["strength"] = min(MAX_ATTRIBUTE, attrs.get("strength", 0) + recovery_per_hour * res_info.get("strength_recovery", 1) * recovery_penalty)
        attrs["energy"] = min(MAX_ATTRIBUTE, attrs.get("energy", 0) + recovery_per_hour * res_info.get("energy_recovery", 1) * recovery_penalty)
        attrs["mood"] = min(MAX_ATTRIBUTE, attrs.get("mood", 0) + recovery_per_hour * res_info.get("mood_recovery", 0) * recovery_penalty)

        # 饱食度每分钟消耗
        attrs["satiety"] = max(0, attrs.get("satiety", 0) - SATIETY_CONSUMPTION_RATE)

        # 应用 debuff 体力流失（饥饿等）
        apply_debuff_strength_drain(attrs, user)

        # 空闲时压力自然衰减（每小时）
        decay_per_tick = PRESSURE_DECAY_IDLE / TICKS_PER_HOUR
        decay_pressure(user, "body", decay_per_tick)
        decay_pressure(user, "mind", decay_per_tick)

        user["attributes"] = attrs
        await self._store.update_user(user_id, user)

    async def _check_night_auto_sleep(self, now: datetime):
        """夜间自动睡觉检测 (0-8点空闲用户自动睡眠)"""
        hour = now.hour
        # 0点到8点之间,空闲状态的用户自动睡眠
        if hour >= 0 and hour < 8:
            users = await self._store.get_all_users()
            for user_id, user in users.items():
                if user.get("status") == UserStatus.FREE.value:
                    await self._start_sleep_auto(user_id, user, now)

    async def _start_sleep_auto(self, user_id: str, user: dict, now: datetime):
        """自动开始睡眠"""
        hour = now.hour
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES["桥下"])

        # 计算距离8点的睡眠时长
        hours_to_8 = 8 - hour if hour < 8 else 8
        sleep_hours = max(1, min(8, hours_to_8))

        detail = ActionDetail.create(
            action_type=TICK_TYPE_SLEEP,
            hours=sleep_hours,
            start_time=now,
            sleep_bonus=res_info.get("sleep_bonus", 1.0),
            residence=residence
        )

        user["status"] = UserStatus.SLEEPING
        user["current_action"] = TICK_TYPE_SLEEP
        user["action_detail"] = detail
        await self._store.update_user(user_id, user)

    async def _hourly_data_save(self, now: datetime):
        """每小时保存数据"""
        try:
            await self._store.save()
        except Exception as e:
            logger.error(f"数据保存失败: {e}")

    async def _get_group_config(self, group_id: str) -> dict:
        """获取群组配置"""
        key = f"{GROUP_CONFIG_PREFIX}{group_id}"
        config = await self.get_kv_data(key, None)
        if config is None:
            config = DEFAULT_GROUP_CONFIG.copy()
            config["subscribers"] = []
            await self.put_kv_data(key, config)
        return config
    
    async def _save_group_config(self, group_id: str, config: dict):
        """保存群组配置"""
        key = f"{GROUP_CONFIG_PREFIX}{group_id}"
        await self.put_kv_data(key, config)
    
    async def _get_or_create_group_config(self, group_id: str) -> dict:
        """获取或创建群组配置"""
        config = await self._get_group_config(group_id)
        return config
    
    # ========================================================
    # 每日结算
    # ========================================================
    
    async def _do_daily_settlement(self):
        """执行每日结算"""

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        local_now = datetime.now(timezone(timedelta(hours=8)))
        today_key = local_now.strftime("%Y-%m-%d")

        # 从 KV 读取上次结算日期（持久化）
        last_date = await self.get_kv_data(DAILY_SETTLEMENT_KV_KEY, "")
        if last_date == date_str:
            logger.info("今日已结算,跳过")
            return

        logger.info(f"执行每日结算: {date_str}")

        # 收集所有用户数据
        users = await self._store.get_all_users()
        
        # 按群组分组用户
        group_users: dict[str, list] = {}  # group_id -> [(user_id, user), ...]
        user_groups: dict[str, list] = {}   # user_id -> [group_id, ...]
        rent_deducted: dict[str, list] = {} # group_id -> [(name, amount, res), ...]
        group_gold: dict[str, int] = {}     # group_id -> total gold earned today
        
        for user_id, user in users.items():
            try:
                # 更新每日统计中的今日金币变动
                from .modules.user import update_lifetime_stat, update_daily_stat, get_today_key
                today_stats = user.get("daily_stats", {}).get(get_today_key(), {})
                gold_work = today_stats.get("gold_work", 0)
                gold_profit = today_stats.get("gold_stock_profit", 0)
                gold_loss = today_stats.get("gold_stock_loss", 0)
                net_gold = gold_work + gold_profit - gold_loss
                
                if net_gold > 0:
                    update_lifetime_stat(user, "total_gold_earned", net_gold)
                
                # 处理房租
                attrs = user.get("attributes", {})
                residence = user.get("residence", "桥下")
                if residence != "桥下":
                    res_info = RESIDENCES.get(residence)
                    if res_info:
                        daily_rent = res_info.get("daily_rent", 0)
                        if daily_rent > 0 and user.get("gold", 0) >= daily_rent:
                            user["gold"] -= daily_rent
                            # 记录到用户所在群
                            for gid in user.get("groups", []):
                                if gid not in rent_deducted:
                                    rent_deducted[gid] = []
                                rent_deducted[gid].append((user.get("nickname", "匿名"), daily_rent, residence))
                            # 累计群金币
                            for gid in user.get("groups", []):
                                group_gold[gid] = group_gold.get(gid, 0) + daily_rent
                
                # 属性衰减
                attrs["satiety"] = max(0, attrs.get("satiety", 0) - 20)
                if attrs["satiety"] < 20:
                    attrs["health"] = max(0, attrs["health"] - 5)
                    attrs["mood"] = max(0, attrs["mood"] - 10)
                
                # 按群组记录用户
                for gid in user.get("groups", []):
                    if gid not in group_users:
                        group_users[gid] = []
                    group_users[gid].append((user_id, user))
                
                # 更新群组累计金币
                for gid in user.get("groups", []):
                    if net_gold > 0:
                        group_gold[gid] = group_gold.get(gid, 0) + int(net_gold)
                
                await self._store.update_user(user_id, user)
                
                # 清理过期每日数据（保留30天）
                from .modules.user import cleanup_old_daily_stats
                cleanup_old_daily_stats(user)
                
            except Exception as e:
                logger.error(f"结算用户 {user_id} 时出错: {e}")

        # 结算完成写入 KV
        await self.put_kv_data(DAILY_SETTLEMENT_KV_KEY, date_str)

        # 发送群组日报
        for group_id, members in group_users.items():
            config = await self._get_group_config(group_id)
            if not config.get("enabled", False):
                continue
            # 只发送有订阅者的群
            subscribers = config.get("subscribers", [])
            active_in_group = [u for u in members if u[0] in subscribers]
            if not active_in_group and subscribers:
                continue
            
            report = self._generate_group_daily_report(
                group_id, members, group_gold.get(group_id, 0),
                rent_deducted.get(group_id, []), date_str, today_key
            )
            try:
                await StarTools.send_message_by_id(
                    "GroupMessage", group_id,
                    MessageChain().message(report)
                )
                logger.info(f"群 {group_id} 日报已发送")
            except Exception as e:
                logger.error(f"群 {group_id} 日报发送失败: {e}")

        # 发送个人日报
        for user_id, user in users.items():
            settings = user.get("settings", {})
            if not settings.get("sub_personal_daily", False):
                continue
            
            report = self._generate_personal_report(user, date_str, today_key)
            try:
                await StarTools.send_message_by_id(
                    "PrivateMessage", user_id,
                    MessageChain().message(report)
                )
                logger.info(f"用户 {user_id} 个人日报已发送")
            except Exception as e:
                logger.error(f"用户 {user_id} 个人日报发送失败: {e}")

        logger.info(f"日报生成完成")

    async def _generate_group_daily_report(
        self, group_id: str, members: list, total_group_gold: int,
        rent_deducted: list, date_str: str, today_key: str
    ) -> str:
        """生成群组日报"""
        from .modules.user import get_today_key
        from .modules.constants import STOCKS
        
        lines = [
            "━━━━━━━━━━━━━━",
            f"【 🗞️ 牛马日报 】",
            f"📅 {date_str}",
            "━━━━━━━━━━━━━━",
        ]
        
        # ---- 股市涨跌榜 ----
        lines.append("")
        lines.append("📈 股市涨跌榜")
        lines.append("━━━━━━━━━━━━━━")
        
        stock_changes = []
        for name, info in STOCKS.items():
            base = info.get("base_price", 100)
            open_price = await self.get_kv_data(f"stock_open:{name}", base)
            current_price = await self.get_kv_data(f"stock_price:{name}", base)
            change = ((current_price - open_price) / open_price * 100) if open_price else 0.0
            stock_changes.append((name, current_price, change))
        
        # 按涨跌幅排序
        stock_changes.sort(key=lambda x: x[2], reverse=True)
        
        rising = [(n, p, c) for n, p, c in stock_changes if c >= 0]
        falling = [(n, p, c) for n, p, c in stock_changes if c < 0]
        
        if rising:
            lines.append("↑ 涨幅榜:")
            for name, price, change in rising[:3]:
                sym = "🔺" if change > 0 else "➖"
                lines.append(f" {sym} {name} {change:+.2f}% ¥{price:.2f}")
        if falling:
            lines.append("↓ 跌幅榜:")
            for name, price, change in falling[:3]:
                lines.append(f" 🔻 {name} {change:.2f}% ¥{price:.2f}")
        
        # ---- 金币榜 ----
        lines.append("")
        lines.append("💰 今日金币榜 (Top5)")
        lines.append("━━━━━━━━━━━━━━")
        
        user_earnings = []
        for _, user in members:
            today_stats = user.get("daily_stats", {}).get(today_key, {})
            work_gold = today_stats.get("gold_work", 0)
            stock_pnl = today_stats.get("gold_stock_profit", 0) - today_stats.get("gold_stock_loss", 0)
            total = work_gold + stock_pnl
            user_earnings.append((user.get("nickname", "匿名"), total))
        
        user_earnings.sort(key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, (name, gold) in enumerate(user_earnings[:5]):
            medal = medals[i] if i < 3 else f"{i+1}."
            sign = "+" if gold >= 0 else ""
            lines.append(f" {medal} {name} {sign}{gold}金币")
        
        # ---- 打工榜 ----
        lines.append("")
        lines.append("📊 今日打工榜 (Top3)")
        lines.append("━━━━━━━━━━━━━━")
        
        user_work = []
        for _, user in members:
            today_stats = user.get("daily_stats", {}).get(today_key, {})
            hours = today_stats.get("work_hours", 0)
            count = today_stats.get("work_count", 0)
            if hours > 0:
                user_work.append((user.get("nickname", "匿名"), hours, count))
        
        user_work.sort(key=lambda x: x[1], reverse=True)
        for i, (name, hours, count) in enumerate(user_work[:3]):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            lines.append(f" {medal} {name} {hours:.1f}h ({count}次)")
        
        # ---- 房租支出 ----
        if rent_deducted:
            lines.append("")
            lines.append("📝 今日房租支出")
            lines.append("━━━━━━━━━━━━━━")
            for name, amount, res in rent_deducted[:5]:
                lines.append(f" {name}: -{amount}金 ({res})")
        
        # ---- 本群数据 ----
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"🏠 群成员: {len(members)}人")
        lines.append(f"💰 群累计赚取: {total_group_gold:,}金币")
        lines.append("━━━━━━━━━━━━━━")
        report_hour = getattr(self.config, 'daily_report_hour', 23)
        report_min = getattr(self.config, 'daily_report_minute', 0)
        lines.append(f"⏰ 每日 {report_hour:02d}:{report_min:02d} 自动生成")
        
        return "\n".join(lines)

    def _generate_personal_report(self, user: dict, date_str: str, today_key: str) -> str:
        """生成个人日报"""
        from .modules.user import get_today_key
        
        lines = [
            "━━━━━━━━━━━━━━",
            f"【 📋 个人日报 】",
            f"📅 {date_str}",
            "━━━━━━━━━━━━━━",
        ]
        
        today = user.get("daily_stats", {}).get(today_key, {})
        lifetime = user.get("lifetime_stats", {})
        
        # 今日收益
        work_gold = today.get("gold_work", 0)
        stock_profit = today.get("gold_stock_profit", 0)
        stock_loss = today.get("gold_stock_loss", 0)
        spent = today.get("gold_spent", 0)
        net = work_gold + stock_profit - stock_loss
        
        lines.append("")
        lines.append("💵 今日收支")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f" 工作收入: +{work_gold}金币")
        lines.append(f" 股票盈亏: {'+' if stock_profit >= 0 else ''}{stock_profit-stock_loss}金币")
        lines.append(f" 消费支出: -{spent}金币")
        lines.append(f" 净收益: {'+' if net >= 0 else ''}{net}金币")
        
        # 今日活动
        lines.append("")
        lines.append("📊 今日活动")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f" 工作: {today.get('work_hours', 0):.1f}h ({today.get('work_count', 0)}次)")
        lines.append(f" 学习: {today.get('learn_hours', 0):.1f}h")
        lines.append(f" 娱乐: {today.get('entertain_count', 0)}次")
        lines.append(f" 股票交易: {today.get('stock_trades', 0)}次")
        
        # 持仓状态
        holdings = user.get("stock_holdings", {})
        if holdings:
            lines.append("")
            lines.append("📈 持仓状况")
            lines.append("━━━━━━━━━━━━━━")
            for name, hold in holdings.items():
                code = STOCKS.get(name, {}).get("code", "?")
                amount = hold.get("amount", 0)
                avg = hold.get("avg_price", 0)
                lines.append(f" {code} {name}: {amount}股 (成本¥{avg:.2f})")
        
        # 累计数据
        lines.append("")
        lines.append("🏆 累计成就")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f" 累计赚取: {int(lifetime.get('total_gold_earned', 0)):,}金币")
        lines.append(f" 最高金币: {int(lifetime.get('peak_gold', 0)):,}金币")
        lines.append(f" 累计工作: {lifetime.get('total_work_hours', 0):.0f}h")
        lines.append(f" 股票盈亏: {'+' if lifetime.get('total_stock_profit', 0) >= 0 else ''}{int(lifetime.get('total_stock_profit', 0)):,}金币")
        
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"💳 当前余额: {user.get('gold', 0):,}金币")
        lines.append("━━━━━━━━━━━━━━")
        
        return "\n".join(lines)

