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

# 导入自定义模块
from .modules.constants import ITEMS, STOCKS, FOODS, RESIDENCES, JOBS, COURSES, ENTERTAINMENTS, MAX_ATTRIBUTE, INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS
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
from .modules.tick import TickManager, TickType, ActionDetail
from .modules.renderer import CardRenderer

# 导入命令模块
from .src.commands import register_all_commands


# ============================================================
# 常量定义
# ============================================================

TEST_MODE = False
TEST_TIME_SCALE = 0.1

DAILY_SETTLEMENT_HOUR = 23
DAILY_SETTLEMENT_MINUTE = 30

SATIETY_CONSUMPTION_RATE = 0.05

GROUP_ID = ""
_LAST_SETTLEMENT_DATE = ""


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
    "0.0.11"
)
class NiumaLife(Star):
    def __init__(self, context: Context):
        super().__init__(context)

        self._data_dir = StarTools.get_data_dir("niumalife")
        self._store = DataStore(self)
        self._parser = CommandParser()

        self._background_tasks: list[asyncio.Task] = []
        self._tick_interval = 60
        self._tick_manager = TickManager(self)
        self._renderer = CardRenderer()

        self._last_hourly_tick = datetime.now(timezone.utc)
        self._last_daily_tick = datetime.now(timezone.utc)

        # 注册所有命令
        register_all_commands(self)

    async def initialize(self):
        global GROUP_ID
        logger.info("牛马人生插件初始化 - v0.0.11 重构版")

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
                await self._process_all_free_passive_recovery(now)

                # 检查是否需要自动睡觉
                await self._check_night_auto_sleep(now)

                # 触发基于时间的事件（每小时/每日/Cron）
                await self._tick_manager.trigger_time_based_events(now)

                # Tick 所有用户动作
                await self._tick_manager.tick_all_users(now)

                # 每小时数据保存
                await self._hourly_data_save(now)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Tick循环错误: {e}")

    async def _hourly_tick_loop(self):
        """小时级Tick"""
        while True:
            try:
                await asyncio.sleep(3600)
                now = datetime.now(timezone.utc)
                logger.info("小时级Tick触发")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"小时Tick错误: {e}")

    async def _process_all_free_passive_recovery(self, now: datetime):
        """处理所有空闲用户的被动恢复"""
        users = await self._store.get_all_users()
        for user_id, user in users.items():
            if user.get("status") == UserStatus.FREE.value:
                await self._process_free_passive_recovery(user_id, user, now)

    async def _process_free_passive_recovery(self, user_id: str, user: dict, now: datetime):
        """处理单个空闲用户的被动恢复"""
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES.get("桥下"))

        attrs = user.get("attributes", {})

        # 被动恢复 (每小时基础值)
        recovery_per_hour = 2
        attrs["health"] = min(MAX_ATTRIBUTE, attrs.get("health", 0) + recovery_per_hour)
        attrs["strength"] = min(MAX_ATTRIBUTE, attrs.get("strength", 0) + res_info.get("strength_recovery", 2))
        attrs["energy"] = min(MAX_ATTRIBUTE, attrs.get("energy", 0) + res_info.get("energy_recovery", 2))
        attrs["mood"] = min(MAX_ATTRIBUTE, attrs.get("mood", 0) + res_info.get("mood_recovery", 0))

        # 饱食度每分钟消耗
        attrs["satiety"] = max(0, attrs.get("satiety", 0) - SATIETY_CONSUMPTION_RATE)

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
            action_type=TickType.SLEEP,
            hours=sleep_hours,
            start_time=now,
            sleep_bonus=res_info.get("sleep_bonus", 1.0),
            residence=residence
        )

        user["status"] = UserStatus.SLEEPING
        user["current_action"] = TickType.SLEEP
        user["action_detail"] = detail
        await self._store.update_user(user_id, user)

    async def _hourly_data_save(self, now: datetime):
        """每小时保存数据"""
        try:
            await self._store.save()
        except Exception as e:
            logger.error(f"数据保存失败: {e}")

    async def _daily_settlement_loop(self):
        """每日结算循环"""
        while True:
            try:
                # 计算距离下次结算的秒数
                now = datetime.now(timezone.utc)
                target_hour = DAILY_SETTLEMENT_HOUR
                target_minute = DAILY_SETTLEMENT_MINUTE

                next_settlement = datetime(now.year, now.month, now.day, target_hour, target_minute, tzinfo=timezone.utc)
                if now.hour >= target_hour and now.minute >= target_minute:
                    next_settlement += timedelta(days=1)

                sleep_seconds = (next_settlement - now).total_seconds()
                sleep_seconds = max(60, min(sleep_seconds, 86400))

                await asyncio.sleep(sleep_seconds)
                await self._do_daily_settlement()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"每日结算循环错误: {e}")

    async def _do_daily_settlement(self):
        """执行每日结算"""
        global _LAST_SETTLEMENT_DATE, GROUP_ID

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        if _LAST_SETTLEMENT_DATE == date_str:
            logger.info("今日已结算,跳过")
            return

        logger.info(f"执行每日结算: {date_str}")

        work_stats = []
        learn_stats = []
        rent_deducted = []

        users = await self._store.get_all_users()
        for user_id, user in users.items():
            try:
                attrs = user.get("attributes", {})
                residence = user.get("residence", "桥下")

                if residence != "桥下":
                    res_info = RESIDENCES.get(residence)
                    if res_info:
                        daily_rent = res_info.get("daily_rent", 0)
                        if daily_rent > 0 and user.get("gold", 0) >= daily_rent:
                            user["gold"] -= daily_rent
                            rent_deducted.append((user.get("nickname", "匿名"), daily_rent, residence))

                attrs["satiety"] = max(0, attrs.get("satiety", 0) - 20)

                if attrs["satiety"] < 20:
                    attrs["health"] = max(0, attrs["health"] - 5)
                    attrs["mood"] = max(0, attrs["mood"] - 10)

                await self._store.update_user(user_id, user)

            except Exception as e:
                logger.error(f"结算用户 {user_id} 时出错: {e}")

        _LAST_SETTLEMENT_DATE = date_str

        if GROUP_ID:
            report = self._generate_daily_report(work_stats, learn_stats, rent_deducted, date_str)
            logger.info(f"日报生成: {report[:200]}...")

    def _generate_daily_report(self, work_stats: list, learn_stats: list, rent_deducted: list, date_str: str) -> str:
        """生成每日报告"""
        lines = [
            f"━━━━━━━━━━━━━━",
            f"【 牛马日报 {date_str} 】",
            f"━━━━━━━━━━━━━━",
        ]

        if rent_deducted:
            lines.append("📝 房租扣除:")
            for name, amount, res in rent_deducted:
                lines.append(f"  {name}: -{amount}金 ({res})")

        lines.append(f"━━━━━━━━━━━━━━")
        lines.append(f"📋 每日 {DAILY_SETTLEMENT_HOUR}:{DAILY_SETTLEMENT_MINUTE:02d} 自动结算")

        return "\n".join(lines)
