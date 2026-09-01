"""
牛马人生 - AstrBot 打工群游戏
重构版本: 模块化命令 + DAO数据访问
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

LOCAL_TZ = timezone(timedelta(hours=8))

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain

# 导入自定义模块
from .modules.constants import ITEMS, STOCKS, FOODS, RESIDENCES, JOBS, COURSES, ENTERTAINMENTS, MAX_ATTRIBUTE, INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS, TICKS_PER_HOUR
from .modules import constants as _constants_module
from .modules.user import DataStore, UserStatus, migrate_user_data
from .src.data.user_repository import UserRepository
from .src.reports.daily_report import DailyReportGenerator
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
from .modules.messenger import Messenger
from .modules.keyword_trigger import KeywordRouter
from .modules.keyword_routes import get_keyword_router

# 导入命令逻辑函数
from .src.commands import (
    run_profile_logic,
    run_work_logic,
    run_learn_logic,
    run_entertain_logic,
    run_eat_logic,
    run_checkin_logic,
    run_residence_logic,
    run_backpack_logic,
    run_stock_logic,
    run_cancel_logic,
    run_help_logic,
    run_shop_logic,
    run_equip_logic,
    run_my_jobs_logic,
    run_complete_job_logic,
    run_cancel_job_logic,
    run_settings_logic,
    run_fishing_logic,
    run_fish_dex_logic,
)
from .src.commands.interactive import get_job_mgr, get_favor_mgr


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

# 注意: GROUP_CONFIG_PREFIX / DEFAULT_GROUP_CONFIG / DAILY_SETTLEMENT_KV_KEY
# 已迁至 src/reports/daily_report.py（保持 KV key 不变，向后兼容）


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
    "0.1.9"
)
class NiumaLife(Star):
    """牛马人生插件主类
    
    所有 @filter.command 命令直接定义在此类上，作为 thin wrapper 调用 run_xxx_logic 函数。
    """
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config
        self.context = context

        self._data_dir = StarTools.get_data_dir("niumalife")
        self._store = UserRepository(self)
        self._daily_report = DailyReportGenerator(self, self._store, _constants_module)
        self._parser = CommandParser()
        self.logger = logger

        self._background_tasks: list[asyncio.Task] = []
        self._tick_interval = 60
        self._tick_manager = TickManager(self)
        self._renderer = CardRenderer()
        self._messenger = Messenger(self)
        self._keyword_router = get_keyword_router()
        self._keyword_handlers = self._build_keyword_handlers()

        self._last_hourly_tick = datetime.now(LOCAL_TZ)
        self._last_daily_tick = datetime.now(LOCAL_TZ)

        # 商店状态（随机商品刷新）
        self._shop_state = {}

        # === 通知基础设施（方案G） ===
        # tick 等非命令上下文需要发消息时，把 (user_id, MessageChain) 扔进这个队列。
        # 后台 _notification_consumer task 拿出后通过缓存的最近 event.send() 发送，
        # 走 AstrBot 内部路径，完全不碰 StarTools.send_message / platform_id。
        self._notify_queue: asyncio.Queue = asyncio.Queue()
        self._recent_event: dict[str, "AstrMessageEvent"] = {}  # user_id -> 最近 event
        self._event_max_age_seconds = 3600  # event 超过1小时视为过期

    def _cache_event(self, event) -> None:
        """由所有 @filter.command wrapper 调用，缓存最近事件用于后台通知。"""
        try:
            user_id = str(event.get_sender_id())
            self._recent_event[user_id] = event
        except Exception:
            pass

    async def _notification_consumer(self) -> None:
        """后台消费 _notify_queue，通过缓存的 event 发消息。

        完全不构造 MessageSession —— 走 event.send(MessageChain) 路径，
        AstrBot 内部处理 session/平台匹配，无需 platform_id。
        """
        while True:
            try:
                user_id, msg_chain = await self._notify_queue.get()
                event = self._recent_event.get(user_id)
                if event is None:
                    self.logger.warning(
                        f"[NiumaLife] 通知丢弃: 用户 {user_id} 无最近 event"
                    )
                    continue
                try:
                    await event.send(msg_chain)
                except Exception as e:
                    self.logger.error(
                        f"[NiumaLife] 通知发送失败 (user={user_id}): {e}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[NiumaLife] _notification_consumer 异常: {e}")

    # ========================================================
    # 关键词触发层（支持群聊中不使用 @ 直接触发）
    # ========================================================

    def _build_keyword_handlers(self) -> dict:
        """建立 action -> 方法名的映射，供 on_keyword_msg 调用"""
        return {
            "profile": self.profile,
            "work": self.work,
            "learn": self.learn,
            "entertain": self.entertain,
            "eat": self.eat,
            "checkin": self.checkin,
            "residence_cmd": self.residence_cmd,
            "equip_cmd": self.equip_cmd,
            "backpack": self.backpack,
            "shop_cmd": self.shop_cmd,
            "stock_cmd": self.stock_cmd,
            "cancel": self.cancel,
            "help_cmd": self.help_cmd,
            "my_jobs": self.my_jobs,
            "complete_job_cmd": self.complete_job_cmd,
            "cancel_job_cmd": self.cancel_job_cmd,
            "settings_cmd": self.settings_cmd,
            "fishing_cmd": self.fishing_cmd,
            "fish_dex_cmd": self.fish_dex_cmd,
        }

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_keyword_msg(self, event: AstrMessageEvent):
        """监听所有消息，在群聊中通过纯文触发指令（不需要 @）

        如果消息是 @ 触发的（is_at_or_wake_command=True），则跳过，
        交给 @filter.command 层处理。
        如果消息是普通文本，则走这里通过 KeywordRouter 匹配并执行。
        """
        self._cache_event(event)
        # 1. 如果是 @ 触发或私聊，走 @filter.command，跳过这里
        if event.is_at_or_wake_command or event.is_private_chat():
            return

        message_str = event.message_str
        if not message_str:
            return

        # 2. 用 KeywordRouter 匹配（支持 /打工、打工 等）
        route = self._keyword_router.match_command_route(message_str)
        if route is None:
            return

        # 3. 找到对应的 handler 并执行
        handler = self._keyword_handlers.get(route.action)
        if handler is None:
            logger.warning(f"[NiumaLife] 未找到 action 对应的 handler: {route.action}")
            return

        logger.info(f"[NiumaLife] 关键词触发: {route.keyword} -> {route.action}")
        try:
            async for result in handler(event):
                yield result
            event.stop_event()
        except TypeError:
            result = await handler(event)
            if result:
                yield result
            event.stop_event()

    # ========================================================
    # 命令路由 (thin wrapper)
    # 所有命令仅调用对应的 run_xxx_logic 函数
    # ========================================================

    @filter.command("档案")
    async def profile(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_profile_logic(event, self._store, self._renderer):
            yield result
        event.stop_event()

    @filter.command("打工")
    async def work(self, event: AstrMessageEvent):
        self._cache_event(event)
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        async for result in run_work_logic(event, self._store, self._parser, jmgr, fmgr, self._renderer):
            yield result
        event.stop_event()

    @filter.command("完成委托")
    async def complete_job(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_complete_job_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("学习")
    async def learn(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_learn_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("娱乐")
    async def entertain(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_entertain_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("吃")
    async def eat(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_eat_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("签到")
    async def checkin(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_checkin_logic(event, self._store, self._renderer):
            yield result
        event.stop_event()

    @filter.command("住")
    async def residence_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_residence_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("装备")
    async def equip_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_equip_logic(event, self._store, self._parser):
            yield result
        event.stop_event()

    @filter.command("背包")
    async def backpack(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_backpack_logic(event, self._store):
            yield result
        event.stop_event()

    @filter.command("商店")
    async def shop_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_shop_logic(event, self._store, self._parser, self):
            yield result
        event.stop_event()

    @filter.command("股市")
    async def stock_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_stock_logic(event, self._store, self._parser, self.get_kv_data):
            yield result
        event.stop_event()

    @filter.command("取消")
    async def cancel(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_cancel_logic(event, self._store, self._renderer):
            yield result
        event.stop_event()

    @filter.command("帮助")
    async def help_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_help_logic(event, self._renderer):
            yield result
        event.stop_event()

    @filter.command("我的委托")
    async def my_jobs(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_my_jobs_logic(event, self._store):
            yield result
        event.stop_event()

    @filter.command("完成委托")
    async def complete_job_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_complete_job_logic(event, self._store, self._parser, self._renderer):
            yield result
        event.stop_event()

    @filter.command("取消委托")
    async def cancel_job_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_cancel_job_logic(event, self._store, self._parser):
            yield result
        event.stop_event()

    @filter.command("设置")
    async def settings_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_settings_logic(event, self._store, self._parser, self._get_group_config, self._save_group_config):
            yield result
        event.stop_event()

    @filter.command("钓鱼")
    async def fishing_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_fishing_logic(event, self._store):
            yield result
        event.stop_event()

    @filter.command("鱼塘")
    async def fish_dex_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_fish_dex_logic(event, self._store, self._renderer):
            yield result
        event.stop_event()

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

        # 启动通知 consumer（方案G：tick 发消息走这里）
        task2 = asyncio.create_task(self._notification_consumer())
        self._background_tasks.append(task2)

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
                now = datetime.now(LOCAL_TZ)

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
            if status == UserStatus.HOSPITALIZED:
                await self._process_hospital(user_id, user, now)
            elif status == UserStatus.FREE:
                await self._process_free_passive_recovery(user_id, user, now)

    async def _process_hospital(self, user_id: str, user: dict, now: datetime):
        """处理住院状态用户"""
        from .modules.constants import (
            HOSPITAL_COST_PER_HOUR, HOSPITAL_HEALTH_PER_HOUR,
            HOSPITAL_STRENGTH_PER_HOUR, HOSPITAL_ENERGY_PER_HOUR,
            HOSPITAL_MOOD_PER_HOUR, HOSPITAL_DISCHARGE_THRESHOLD
        )

        attrs = user.get("attributes", {})

        # 免费住院，不扣金币
        # 每小时恢复四项属性
        attrs["health"] = max(0, min(100, attrs.get("health", 0) + HOSPITAL_HEALTH_PER_HOUR / TICKS_PER_HOUR))
        attrs["strength"] = max(0, min(100, attrs.get("strength", 0) + HOSPITAL_STRENGTH_PER_HOUR / TICKS_PER_HOUR))
        attrs["energy"] = max(0, min(100, attrs.get("energy", 0) + HOSPITAL_ENERGY_PER_HOUR / TICKS_PER_HOUR))
        attrs["mood"] = max(0, min(100, attrs.get("mood", 0) + HOSPITAL_MOOD_PER_HOUR / TICKS_PER_HOUR))

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

        # 被动恢复 (每小时基础值 / 60 = 每分钟恢复量 * 住所加成 * debuff惩罚)
        recovery_per_minute = 2 / 60
        attrs["health"] = min(MAX_ATTRIBUTE, attrs.get("health", 0) + recovery_per_minute * res_info.get("health_recovery", 1) * recovery_penalty)
        attrs["strength"] = min(MAX_ATTRIBUTE, attrs.get("strength", 0) + recovery_per_minute * res_info.get("strength_recovery", 1) * recovery_penalty)
        attrs["energy"] = min(MAX_ATTRIBUTE, attrs.get("energy", 0) + recovery_per_minute * res_info.get("energy_recovery", 1) * recovery_penalty)
        attrs["mood"] = min(MAX_ATTRIBUTE, attrs.get("mood", 0) + recovery_per_minute * res_info.get("mood_recovery", 0) * recovery_penalty)

        # 饱食度消耗已禁用
        # attrs["satiety"] = max(0, attrs.get("satiety", 0) - SATIETY_CONSUMPTION_RATE)

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
                if user.get("status") == UserStatus.FREE:
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
        """获取群组配置（thin wrapper，委托给 DailyReportGenerator）。"""
        return await self._daily_report.get_group_config(group_id)

    async def _save_group_config(self, group_id: str, config: dict):
        """保存群组配置（thin wrapper，委托给 DailyReportGenerator）。"""
        await self._daily_report.save_group_config(group_id, config)

    async def _get_or_create_group_config(self, group_id: str) -> dict:
        """获取或创建群组配置（保留兼容）。"""
        return await self._get_group_config(group_id)

    # ========================================================
    # 每日结算（thin wrapper）
    # ========================================================

    async def _do_daily_settlement(self):
        """执行每日结算（委托给 DailyReportGenerator）。"""
        await self._daily_report.settle()

