"""
牛马人生 - AstrBot 打工群游戏
重构版本: 模块化命令 + DAO数据访问
"""

import asyncio
import inspect
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
from .modules.tick import TickManager, ActionDetail
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
    run_buy_logic,
    run_equip_logic,
    run_my_jobs_logic,
    run_complete_job_logic,
    run_cancel_job_logic,
    run_settings_logic,
    run_fishing_logic,
    run_fish_dex_logic,
    run_sell_logic,
    run_fishing_gear_logic,
    run_enchant_logic,
    run_use_logic,
)
from .src.commands.interactive import get_job_mgr, get_favor_mgr
from .src.llm_tools import register_game_tools
from .src.llm_tools.game_tools import (
    _tool_get_player_status,
    _tool_get_player_skills,
    _tool_get_fishing_records,
    _tool_get_inventory_summary,
    _tool_execute_sell,
)


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


def _format_food_effects_zh(effects: dict) -> str:
    """格式化食物效果为人话描述, 让 LLM 决定吃什么. 模块顶层 helper."""
    parts = []
    for k, v in (effects or {}).items():
        k_zh = {
            "satiety": "饱食度",
            "mood": "心情",
            "stamina": "体力",
            "health": "健康",
            "max_health": "健康上限",
            "sanity": "精神",
            "hp": "生命",
        }.get(k, k)
        try:
            parts.append(f"{k_zh} {float(v):+g}")
        except Exception:
            parts.append(f"{k_zh} {v}")
    return ", ".join(parts) if parts else "无效果"


@register(
    "niumalife",
    "海獭 🦦",
    "牛马人生 - 打工群文字模拟经营游戏",
    "0.1.10"
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
        # 9/6: 统一消息发送器 (ARCHITECTURE.md P0 #1)
        from src.ui.message_sender import MessageSender
        self._sender = MessageSender(self)
        self._keyword_router = get_keyword_router()
        self._keyword_handlers = self._build_keyword_handlers()

        self._last_hourly_tick = datetime.now(LOCAL_TZ)
        self._last_daily_tick = datetime.now(LOCAL_TZ)

        # 商店状态（随机商品刷新）
        self._shop_state = {}

        # === 通知基础设施 (方案 G+, 9/6 改进) ===
        # tick 等非命令上下文需要发消息时，把 (user_id, MessageChain, session_key) 扔进队列。
        # 后台 _notification_consumer task 取出后通过缓存的 event.send() 发送。
        #
        # 缓存按 session_key 分组 (而非 user_id): 同一玩家在群 A 钓鱼 / 群 B 闲聊时，
        # 两个 event 各自缓存。tick 完成的鱼通知必须用"发起动作的会话"event 发，
        # 不能因为玩家中途跑去别的群就被覆盖。
        #
        # session_key 格式: "platform_id|session_type|session_id"
        #   - platform_id: "aiocqhttp" / "telegram" 等
        #   - session_type: "GroupMessage" / "PrivateMessage"
        #   - session_id: group_id 或 user_id
        self._notify_queue: asyncio.Queue = asyncio.Queue()
        self._recent_events: dict[str, "AstrMessageEvent"] = {}  # session_key -> 最近 event
        # 9/6 简化: 移除持久化补发设计。原 1h 过期保护也已移除。
        # 当前策略: 只缓存内存 event, 重启即丢, 但正常运行期间
        # event 缓存命中率 > 95%, 通知不会丢。
        # 重启期 (几十秒) 触发的 tick 通知确实会丢, 玩家感知很小。

    def _cache_event(self, event) -> None:
        """由所有 @filter.command wrapper 调用, 缓存 event 用于后台通知。

        9/6 简化: 只缓存 event, 不再触发任何 KV 操作。
        缓存按 session_key 分组 (不是 user_id), 避免群 A 钓鱼/群 B 闲聊
        时通知发错窗口。
        """
        import time
        try:
            from src.ui.message_sender import _extract_session_key  # type: ignore
            session_key = _extract_session_key(event)
            if not session_key:
                return
            self._recent_events[session_key] = event
            event._niuma_cached_at = time.time()
            # 9/6: 移除 flush_pending_for_session 调用 — 不再做 KV 持久化补发
        except Exception:
            pass

    async def _notification_consumer(self) -> None:
        """后台消费 _notify_queue, 用缓存 event.send() 发送。

        9/6 简化:
          - 缓存按 session_key (而非 user_id) 索引
          - 失败 / 无缓存 event → 直接丢弃 (不再 KV 持久化补发)
        """
        sender = getattr(self, "_sender", None)
        while True:
            try:
                item = await self._notify_queue.get()
                # 解包: (user_id, msg_chain, session_key) 或 (user_id, msg_chain)
                if len(item) == 3:
                    user_id, msg_chain, session_key = item
                else:
                    user_id, msg_chain = item
                    session_key = ""
                if session_key:
                    # 9/6: 兼容两种 session_key 格式:
                    # 1) tick.py 推送的 start_group_id (纯数字)
                    # 2) _cache_event 缓存的完整 key ("platform|session_type|group:xxx")
                    event = self._recent_events.get(session_key)
                    if event is None:
                        # fallback: 按 group_id 后缀查找 (兼容完整 key)
                        suffix = f"|group:{session_key}"
                        for key, evt in self._recent_events.items():
                            if key.endswith(suffix):
                                event = evt
                                break
                else:
                    # 兼容老路径 (没传 session_key): 反查 user_id 最近会话
                    event = self._infer_event(user_id)
                if event is None:
                    self.logger.warning(
                        f"[NiumaLife] 通知跳过: user_id={user_id} session={session_key} "
                        f"无缓存 event (玩家可能已离开该会话)"
                    )
                    continue
                try:
                    await event.send(msg_chain)
                except Exception as e:
                    self.logger.error(
                        f"[NiumaLife] 通知发送失败 (user={user_id}, session={session_key}): {e}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"[NiumaLife] _notification_consumer 异常: {e}")

    def _infer_event(self, user_id: str):
        """反查 user_id 最近一次活跃的 event (按 _niuma_cached_at 排序)。"""
        best = None
        best_time = 0.0
        for key, event in self._recent_events.items():
            sender_id = ""
            try:
                sender_id = str(event.get_sender_id())
            except Exception:
                continue
            if sender_id == user_id:
                t = getattr(event, "_niuma_cached_at", 0)
                if t > best_time:
                    best = event
                    best_time = t
        return best

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
            "buy_cmd": self.buy_cmd,
            "stock_cmd": self.stock_cmd,
            "cancel": self.cancel,
            "help_cmd": self.help_cmd,
            "my_jobs": self.my_jobs,
            "complete_job_cmd": self.complete_job_cmd,
            "cancel_job_cmd": self.cancel_job_cmd,
            "settings_cmd": self.settings_cmd,
            "fishing_cmd": self.fishing_cmd,
            "fishing_gear_cmd": self.fishing_gear_cmd,
            "fish_dex_cmd": self.fish_dex_cmd,
            "sell_cmd": self.sell_cmd,
            "enchant_cmd": self.enchant_cmd,
            "use_cmd": self.use_cmd,
        }

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_keyword_msg(self, event: AstrMessageEvent):
        """监听所有消息，在群聊中通过纯文触发指令（不需要 @）

        如果消息是 @ 触发的（is_at_or_wake_command=True），则跳过，
        交给 @filter.command 层处理。
        如果消息是普通文本，则走这里通过 KeywordRouter 匹配并执行。
        """
        import logging
        _l = logging.getLogger("astrbot_plugin_niumalife")
        _l.warning(f"[KEYWORD_HANDLER] ENTER. group_id={event.get_group_id()!r}, is_at_or_wake={event.is_at_or_wake_command}, is_private={event.is_private_chat()}, msg={event.message_str!r}")
        self._cache_event(event)
        # 1. 如果是 @ 触发或私聊，走 @filter.command，跳过这里
        if event.is_at_or_wake_command or event.is_private_chat():
            _l.warning(f"[KEYWORD_HANDLER] SKIP (at_or_wake=True or private=True)")
            return

        message_str = event.message_str
        if not message_str:
            return

        # 2. 用 KeywordRouter 匹配（支持 /打工、打工 等）
        route = self._keyword_router.match_command_route(message_str)
        _l.warning(f"[KEYWORD_HANDLER] match_command_route({message_str!r}) = {route!r}")
        if route is None:
            _l.warning(f"[KEYWORD_HANDLER] no route matched, returning")
            return

        # 3. 找到对应的 handler 并执行
        handler = self._keyword_handlers.get(route.action)
        if handler is None:
            _l.warning(f"[KEYWORD_HANDLER] NO HANDLER for action={route.action!r}. handlers_keys={list(self._keyword_handlers.keys())!r}")
            return

        logger.info(f"[NiumaLife] 关键词触发: {route.keyword} -> {route.action}")
        try:
            # 9/6: 区分 async generator (yield) vs coroutine (return)
            # inspect.isasyncgenfunction 对 bound method 也生效
            if inspect.isasyncgenfunction(handler):
                async for result in handler(event):
                    yield result
            else:
                result = await handler(event)
                if result:
                    yield result
            event.stop_event()
        except Exception as e:
            logger.error(f"[NiumaLife] keyword handler '{route.action}' 异常: {e}")
            event.stop_event()
            yield event.plain_result(f"⚠️ 处理失败: {e}")

    # ========================================================
    # 命令路由 (thin wrapper)
    # 所有命令仅调用对应的 run_xxx_logic 函数
    # ========================================================

    @filter.command("档案")
    async def profile(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card() (替代 25 处散落 try/except 样板)
        async for result in run_profile_logic(event, self._store, self._sender):
            yield result
        event.stop_event()

    @filter.command("打工")
    async def work(self, event: AstrMessageEvent):
        self._cache_event(event)
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        async for result in run_work_logic(event, self._store, self._parser, jmgr, fmgr, self._sender):
            yield result
        event.stop_event()

    @filter.command("学习")
    async def learn(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_learn_logic(event, self._store, self._parser, self._sender):
            yield result
        event.stop_event()

    @filter.command("娱乐")
    async def entertain(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_entertain_logic(event, self._store, self._parser, self._sender):
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
        async for result in run_checkin_logic(event, self._store, self._sender):
            yield result
        event.stop_event()

    @filter.command("住")
    async def residence_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_residence_logic(event, self._store, self._parser, self._sender):
            yield result
        event.stop_event()

    @filter.command("装备")
    async def equip_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_equip_logic(event, self._store, self._parser):
            yield result
        event.stop_event()

    @filter.command("渔具")
    async def fishing_gear_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_fishing_gear_logic(event, self._store, self._parser, self._sender):
            yield result
        event.stop_event()

    @filter.command("背包")
    async def backpack(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_backpack_logic(event, self._store, self._parser, self._sender):
            yield result
        event.stop_event()

    @filter.command("商店")
    async def shop_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        async for result in run_shop_logic(event, self._store, self._parser, self._sender, self):
            yield result
        event.stop_event()

    @filter.command("买", alias={"购买", "购入", "入手"})
    async def buy_cmd(self, event: AstrMessageEvent):
        """购买指令 - 9/4: 独立购买指令, 不再依赖 /商店 买"""
        self._cache_event(event)
        async for result in run_buy_logic(event, self._store, self._parser, self):
            yield result
        event.stop_event()

    @filter.command("股市")
    async def stock_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_stock_logic(event, self._store, self._parser, self.get_kv_data, self._sender):
            yield result
        event.stop_event()

    @filter.command("取消")
    async def cancel(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_cancel_logic(event, self._store, self._sender):
            yield result
        event.stop_event()

    @filter.command("帮助")
    async def help_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_help_logic(event, self._sender):
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
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_complete_job_logic(event, self._store, self._parser, self._sender):
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
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_fishing_logic(event, self._store, self._sender):
            yield result
        event.stop_event()

    @filter.command("鱼塘")
    async def fish_dex_cmd(self, event: AstrMessageEvent):
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card()
        async for result in run_fish_dex_logic(event, self._store, self._sender):
            yield result
        event.stop_event()

    @filter.command("卖")
    async def sell_cmd(self, event: AstrMessageEvent):
        import logging
        _l = logging.getLogger("astrbot_plugin_niumalife")
        _l.warning(f"[SELL_CMD] entered. group_id={event.get_group_id()!r}, sender={event.get_sender_id()!r}, message={event.get_message_str()!r}")
        self._cache_event(event)
        # 9/6: 改用 MessageSender.send_card() (5 处 try/except 全部消除)
        async for result in run_sell_logic(event, self._store, self._parser, self._sender):
            yield result
        event.stop_event()

    @filter.command("附魔")
    async def enchant_cmd(self, event: AstrMessageEvent):
        """附魔 - 9/4晚

        用法:
        - /附魔 <物品>              使用背包第一张附魔券
        - /附魔 <物品> <附魔券>
        """
        self._cache_event(event)
        _, args = self._parser.parse(event)
        async for result in run_enchant_logic(event, self._store, args, self._sender):
            yield result
        event.stop_event()

    @filter.command("使用")
    async def use_cmd(self, event: AstrMessageEvent):
        """使用 - 9/4晚

        用法:
        - /使用 <附魔券> <物品>
        """
        self._cache_event(event)
        _, args = self._parser.parse(event)
        async for result in run_use_logic(event, self._store, args):
            yield result
        event.stop_event()

    # ========================================================
    # LLM Tools —— 供 AstrBot 接入的 persona (丽贝卡) 调用
    # 装饰器签名: async def xxx(self, event: AstrMessageEvent, ...)
    # 返回 dict (AstrBot 自动 JSON 序列化)
    # ⚠️ 改了本块必须 `kill PID + restart`, watchfiles reload 不会重新注册 llm_tool
    #
    # 身份安全 (9/3 session 教训): LLM 在群聊里容易把别的玩家当成当前 sender,
    # 导致 execute_sell 等写工具错卖他人背包。强制 3 重保险:
    # 1. 所有只读工具返回里都带 _sender 字段, LLM 必须用它确认 user_id
    # 2. execute_sell 必须检查 user_id == event.get_sender_id(), 不一致拒绝
    # 3. execute_sell 实际改数据后, 主动用 event.send() 发消息给"真人"确认已执行
    #
    # 图片传递模式 (9/3 加): LLM tool 不能 yield, 所以渲染好的图
    # 通过 event.send(MessageChain().image(url)) 主动发给真人, LLM 只拿文本摘要
    # ========================================================

    async def _send_image_to_user(self, event: AstrMessageEvent, image_url: str, fallback_text: str = "") -> bool:
        """主动给真人发图片。返回 True=发送成功, False=走文本 fallback."""
        if not image_url:
            return False
        try:
            if image_url.startswith(("http://", "https://")):
                await event.send(MessageChain().url_image(image_url))
            else:
                await event.send(MessageChain().file_image(image_url))
            return True
        except Exception as e:
            logger.warning(f"[llm_tool] 发图片失败: {e}")
            return False

    async def _run_command_for_llm(self, event: AstrMessageEvent, run_logic_func, *args, fake_cmd: str = "") -> dict:
        """通用 LLM tool helper: 跑一个 run_xxx_logic generator, 收集 yield 主动发出去.

        Args:
            event: AstrMessageEvent
            run_logic_func: run_xxx_logic 函数 (是 async generator)
            *args: 传给 run_logic_func 的额外参数
            fake_cmd: 临时替换 event.message_str 的命令字符串（如 "打工 外卖 4"）

        Returns:
            dict: {sent_count, last_text, success}
        """
        original_msg = getattr(event, "message_str", "")
        if fake_cmd:
            try:
                event.message_str = fake_cmd
            except Exception:
                pass
        sent_count = 0
        last_text_parts = []
        try:
            async for r in run_logic_func(event, *args):
                try:
                    # MessageEventResult 继承 MessageChain, 直接 event.send
                    await event.send(r)
                    sent_count += 1
                    # 提取文本组件作为 LLM 摘要
                    if hasattr(r, "chain") and r.chain:
                        for comp in r.chain:
                            text = getattr(comp, "text", None)
                            if text:
                                last_text_parts.append(text)
                except Exception as e:
                    logger.warning(f"[llm_tool] send fail: {e}")
        except Exception as e:
            logger.error(f"[llm_tool] run_logic exception: {e}", exc_info=True)
            return {"sent_count": sent_count, "last_text": " | ".join(last_text_parts), "success": False, "error": str(e)}
        finally:
            if fake_cmd:
                try:
                    event.message_str = original_msg
                except Exception:
                    pass
        return {
            "sent_count": sent_count,
            "last_text": " | ".join(last_text_parts)[:500],
            "success": True,
        }

    async def _get_sender_context(self, event: AstrMessageEvent) -> dict:
        """统一的 sender 上下文。所有 LLM 工具调用前都用这个。

        Returns:
            {user_id, nickname, is_private, group_id}
        """
        uid = str(event.get_sender_id()) if event.get_sender_id() else ""
        # 拿昵称 (sender.member.nickname 或 sender.nickname)
        nickname = ""
        try:
            sender = getattr(event.message_obj, "sender", None)
            if sender:
                nickname = getattr(sender, "nickname", "") or getattr(sender, "card", "") or ""
        except Exception:
            pass
        if not nickname:
            try:
                nickname = getattr(event, "get_sender_name", lambda: "")()
            except Exception:
                nickname = uid
        is_private = False
        group_id = ""
        try:
            is_private = event.is_private_chat() if hasattr(event, "is_private_chat") else False
            group_id = str(event.get_group_id()) if event.get_group_id() else ""
        except Exception:
            pass
        return {"user_id": uid, "nickname": nickname or "未知玩家", "is_private": is_private, "group_id": group_id}

    def _wrap_with_sender(self, result: dict, ctx: dict) -> dict:
        """给工具返回注入 _sender 字段, LLM 必须用它确认身份。"""
        result["_sender"] = {
            "user_id": ctx["user_id"],
            "nickname": ctx["nickname"],
            "is_private": ctx["is_private"],
            "group_id": ctx["group_id"],
            "_warning": "这是当前真实发消息的玩家。所有 user_id 参数必须等于 _sender.user_id, 否则拒绝执行。",
        }
        return result

    @filter.llm_tool(name="get_player_status")
    async def llm_get_player_status(self, event: AstrMessageEvent) -> dict:
        """获取当前玩家状态：金币、四维属性、所在位置、当前行动。玩家问"我有多少钱"、"我现在在干嘛"、"我状态怎么样"时调用。

        ⚠️ 此工具只能查当前发起会话的玩家, 不能查别人。
        返回里 _sender.user_id 是当前真实玩家, 任何后续写入工具的 user_id 参数必须等于这个值。

        Returns:
            dict: {gold, attributes, status, residence, current_action, action_detail, satiety, _sender} 或 {error}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return {"error": "无法识别当前玩家身份"}
        result = json.loads(await _tool_get_player_status(self, ctx["user_id"]))
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="get_player_skills")
    async def llm_get_player_skills(self, event: AstrMessageEvent) -> dict:
        """获取当前玩家全部技能等级和经验：钓鱼/学习/打工/娱乐/交易等。玩家问"我几级了"、"怎么升级"、"升级要多久"时调用。

        Returns:
            dict: {skills: {skill_name: {level, exp, exp_to_next}}, lifetime_peak_gold, _sender} 或 {error}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return {"error": "无法识别当前玩家身份"}
        result = json.loads(await _tool_get_player_skills(self, ctx["user_id"]))
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="get_fishing_records")
    async def llm_get_fishing_records(
        self,
        event: AstrMessageEvent,
        sort_by: str = "weight",
        limit: int = 5,
    ) -> dict:
        """查询当前玩家钓鱼记录。玩家问"我钓到过哪些鱼"、"最大的鱼是什么"、"最近钓了什么"时调用。

        Args:
            sort_by(string): 排序字段，可选 weight(按重量,默认)/time(按时间)/rarity(按稀有度)
            limit(number): 返回条数，1-50，默认5

        Returns:
            dict: {records: [{fish_name, weight, time, rarity}], _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return {"error": "无法识别当前玩家身份"}
        result = json.loads(await _tool_get_fishing_records(self, ctx["user_id"], sort_by, limit))
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="get_inventory_summary")
    async def llm_get_inventory_summary(
        self,
        event: AstrMessageEvent,
        category: str = "all",
    ) -> dict:
        """查询当前玩家背包物品和总估值。玩家问"我背包有什么"、"我有多少鱼"、"我背包值多少钱"时调用。

        Args:
            category(string): 类别，可选 all(全部)/fish(鱼)/food(食物)/item(装备杂物)，默认all

        Returns:
            dict: {items: [{name, category, quantity, estimated_value}], total_count, total_value, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return {"error": "无法识别当前玩家身份"}
        result = json.loads(await _tool_get_inventory_summary(self, ctx["user_id"], category))
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="preview_sell")
    async def llm_preview_sell(
        self,
        event: AstrMessageEvent,
        item_name: str = "",
        count: int = 0,
        category: str = "",
    ) -> dict:
        """【只读】预览当前玩家卖物品能得多少金币，不修改任何数据。

        当 LLM 不确定玩家是否真的要卖，或者想给玩家看预估收益时，先调用本工具预览。

        ⚠️ 此工具只能预览当前发起会话的玩家 (见 _sender.user_id), 不能预览别人。
        群聊也能用 —— 但 _sender.user_id 一定是当前 @ 你的那个人, 不是历史消息里的别人。

        Args:
            item_name(string): 物品名（如"草鱼"）；不传则按 category 预览
            count(number): 数量；不传或0=全卖预览
            category(string): 类别（fish/food/item），不传 item_name 时生效

        Returns:
            dict: {items_preview: [{name, type}], total_count, estimated_gold, _sender} 或 {error}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return {"error": "无法识别当前玩家身份"}
        name_arg = item_name.strip() if isinstance(item_name, str) and item_name.strip() else None
        cat_arg = category.strip() if isinstance(category, str) and category.strip() else None
        count_int = int(count) if count and int(count) > 0 else None
        # 强制 explicit=False 拿预览
        result = json.loads(await _tool_execute_sell(
            self, ctx["user_id"], name_arg, count_int, cat_arg, explicit=False, event=event
        ))
        preview = result.get("preview", {})
        out = {
            "items_preview": preview.get("items", []),
            "total_count": preview.get("total_count", 0),
            "estimated_gold": preview.get("estimated_gold", 0),
        }
        return self._wrap_with_sender(out, ctx)


    @filter.llm_tool(name="execute_sell")
    async def llm_execute_sell(
        self,
        event: AstrMessageEvent,
        item_name: str = "",
        count: int = 0,
        category: str = "",
        target_user_id: str = "",
    ) -> dict:
        """执行卖物品操作 —— 仅在玩家明确同意后调用。

        正确流程：
        1. LLM 觉得玩家可能要卖 → 先调 preview_sell 拿估值
        2. 把估值告诉玩家，等玩家说"是/卖/确认"
        3. 玩家明确同意 → 调用本工具执行
        4. 玩家没说同意 → 不要调本工具

        ⚠️ 安全规则（9/3 session 教训：保留身份验证，群聊私聊都可用）：
        - 禁止代替群里其他玩家执行高风险操作 (target_user_id != _sender.user_id 直接拒绝)
        - 群聊和私聊都能用, 但 _sender.user_id 永远是当前真实发消息的玩家
        - 写入执行后会主动用 event.send(MessageChain) 给真人发确认消息

        Args:
            item_name(string): 物品名（如"草鱼"）；不传则按 category 卖
            count(number): 数量；不传或0=全卖
            category(string): 类别（fish/food/item），不传 item_name 时生效
            target_user_id(string): 目标玩家 ID；必须等于当前发消息的玩家 (见 _sender.user_id)，否则拒绝

        Returns:
            dict: {status, sold_count, gold_received, gold_before, gold_after, _sender} 或 {status: error, reason}
        """
        ctx = await self._get_sender_context(event)
        real_uid = ctx["user_id"]

        # === 安全检查: 禁止代其他玩家执行 (群聊私聊都启用) ===
        if not real_uid:
            return {"status": "error", "reason": "无法识别当前玩家身份, 拒绝执行"}
        if target_user_id and str(target_user_id) != real_uid:
            return self._wrap_with_sender({
                "status": "error",
                "reason": (
                    f"❌ 拒绝执行: 目标玩家 {target_user_id} != 当前真实发消息的玩家 {real_uid} ({ctx['nickname']}). "
                    f"LLM 不准代替群里其他玩家调用高风险操作。"
                ),
            }, ctx)

        name_arg = item_name.strip() if isinstance(item_name, str) and item_name.strip() else None
        cat_arg = category.strip() if isinstance(category, str) and category.strip() else None
        count_int = int(count) if count and int(count) > 0 else None

        # 先读 user, 拿执行前金币数
        user = await self._store.get_user(real_uid)
        if not user:
            return self._wrap_with_sender({"status": "error", "message": "用户不存在"}, ctx)
        gold_before = user.get("gold", 0)

        # === BUG 修复 (9/3 session): market.sell_items 只算了 total 没改 user.gold ===
        from .src.market import sell_items  # type: ignore[arg-type]
        try:
            sold, total_gold, err_msg = sell_items(user, name=name_arg, count=count_int)
        except Exception as e:
            logger.error(f"[llm_execute_sell] 失败: {e}", exc_info=True)
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

        if err_msg:
            return self._wrap_with_sender({"status": "error", "message": err_msg}, ctx)
        if not sold:
            return self._wrap_with_sender({
                "status": "no_match",
                "message": f"没找到可卖的「{name_arg or cat_arg or '所有物品'}」",
            }, ctx)

        # ⚠️ 关键修复: 手动加金币 (market.sell_items 不会改 user.gold)
        user["gold"] = user.get("gold", 0) + total_gold

        await self._store.update_user(real_uid, user)
        gold_after = user.get("gold", 0)
        # 统计 sold
        sold_summary: dict[str, int] = {}
        for s in sold:
            n = s.get("name", "?")
            sold_summary[n] = sold_summary.get(n, 0) + 1

        result = {
            "status": "success",
            "sold_count": len(sold),
            "sold_summary": sold_summary,
            "gold_received": total_gold,
            "gold_before": gold_before,
            "gold_after": gold_after,
            "remaining_count": sum(1 for i in user.get("inventory", []) if i.get("type") == "fish"),
            "message": (
                f"✅ 玩家 {ctx['nickname']} ({real_uid}) 卖出 {len(sold)} 件, "
                f"获得 {total_gold} 金币 (余额 {gold_before} → {gold_after})"
            ),
        }

        # === 主动给真人发消息确认已执行 (避免 LLM 自己编造结果) ===
        try:
            chat_label = "私聊" if ctx["is_private"] else f"群 {ctx['group_id']}"
            confirm_text = (
                f"💰 [{chat_label}] {ctx['nickname']} 卖出 {len(sold)} 件 "
                f"({', '.join(f'{k}×{v}' for k,v in sold_summary.items())}), "
                f"+{total_gold} 金币 (余额 {gold_after})"
            )
            await event.send(MessageChain().message(confirm_text))
        except Exception as e:
            logger.warning(f"[llm_execute_sell] 主动发消息失败: {e}")

        return self._wrap_with_sender(result, ctx)


        return self._wrap_with_sender(result, ctx)

    # ========================================================
    # 只读视图工具 v2 —— 让 LLM 能主动给真人发对应的卡片图
    # 模式: read user → call renderer → event.send(image) → return dict summary
    # 9/3 加: 图片走 event.send, LLM 只拿到文本摘要 + 状态
    # ========================================================

    @filter.llm_tool(name="view_profile")
    async def llm_view_profile(self, event: AstrMessageEvent) -> dict:
        """【只读】给真人发"档案"卡片图，并返回文字摘要。

        玩家问"看看我的档案"、"我状态怎么样"、"我有什么"时调用。

        Returns:
            dict: {status, summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({
                "status": "not_registered",
                "message": "玩家还没注册, 请告诉 Ta 输入 /签到 自动注册",
            }, ctx)
        try:
            url = await self._renderer.render_profile(user, event)
            sent = await self._send_image_to_user(event, url or "")
            return self._wrap_with_sender({
                "status": "success" if sent else "fallback_text",
                "summary": {
                    "gold": user.get("gold", 0),
                    "residence": user.get("residence"),
                    "status": user.get("status"),
                    "skills_count": len(user.get("skills", {})),
                    "inventory_count": len(user.get("inventory", [])),
                },
                "image_sent": sent,
                "message": "档案图已发给玩家" if sent else "档案渲染失败, 让玩家手动 /档案",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_fish_dex")
    async def llm_view_fish_dex(self, event: AstrMessageEvent) -> dict:
        """【只读】给真人发"鱼塘图鉴"卡片图。

        玩家问"我钓到过哪些鱼"、"图鉴"、"鱼塘"时调用。

        Returns:
            dict: {status, summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        try:
            # FISHES 是模块级全局 dict, 这里必须显式 import 才能引用
            from .src.fishing.fishing_manager import FISHES
            from .src.fishing import fishing_manager as _fm
            _fm._ensure_loaded()  # 确保 FISHES 已加载
            # 9/6: 改用 UserView 消除嵌套访问
            from .src.data.user_view import get_fish_caught, get_biggest_catch, get_fish_title
            caught = get_fish_caught(user)
            url = await self._renderer.render_fish_dex(user, event, caught, FISHES)
            sent = await self._send_image_to_user(event, url or "")
            return self._wrap_with_sender({
                "status": "success" if sent else "fallback_text",
                "summary": {
                    "fish_collected": len(caught),
                    "total_species": len(FISHES),
                    "completion_pct": f"{len(caught)/max(1, len(FISHES))*100:.1f}%",
                    "biggest_catch": get_biggest_catch(user),
                    "title": get_fish_title(user),
                },
                "image_sent": sent,
                "message": "鱼塘图鉴已发给玩家" if sent else "渲染失败",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_my_jobs")
    async def llm_view_my_jobs(self, event: AstrMessageEvent) -> dict:
        """【只读】查询玩家当前进行中的委托。

        玩家问"我的委托"、"我在做什么委托"、"委托进度"时调用。

        Returns:
            dict: {status, in_progress_jobs: [{id, progress_pct, remaining_hours}], _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        from .src.commands.interactive import get_job_mgr
        jmgr = get_job_mgr()
        in_progress = jmgr.get_player_current_jobs(user)
        if not in_progress:
            return self._wrap_with_sender({
                "status": "empty",
                "in_progress_jobs": [],
                "message": "当前没有进行中的委托",
            }, ctx)
        from datetime import datetime, timezone, timedelta
        LOCAL_TZ = timezone(timedelta(hours=8))
        jobs_summary = []
        for j in in_progress:
            try:
                accepted = datetime.fromisoformat(j["accepted_at"])
                expected = datetime.fromisoformat(j["expected_complete_at"])
                remaining_h = max(0, (expected - datetime.now(LOCAL_TZ)).total_seconds() / 3600)
                total_s = max(1, (expected - accepted).total_seconds())
                elapsed_s = (datetime.now(LOCAL_TZ) - accepted).total_seconds()
                progress = min(100, int(elapsed_s / total_s * 100))
                jobs_summary.append({
                    "id": j.get("id", "?"),
                    "name": j.get("name", "?"),
                    "progress_pct": progress,
                    "remaining_hours": round(remaining_h, 1),
                })
            except Exception:
                jobs_summary.append({"id": j.get("id"), "name": j.get("name")})
        return self._wrap_with_sender({
            "status": "success",
            "in_progress_jobs": jobs_summary,
            "count": len(jobs_summary),
            "message": f"你有 {len(jobs_summary)} 个进行中的委托",
        }, ctx)

    @filter.llm_tool(name="view_shop")
    async def llm_view_shop(self, event: AstrMessageEvent) -> dict:
        """【只读】查询商店全部商品（含效果/价格），让 LLM 推荐买什么。

        玩家问"今天商店有什么"、"商店"、"买点吃的"、"买什么能恢复饱食度"时调用。

        Returns:
            dict: {status, items: [{name, type, category, price, effects, effect_summary}], shops: [...], _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        try:
            from .modules.shop import get_sellable_items, CATEGORY_NAMES
            from .modules.constants import ITEMS
            groups = get_sellable_items()
            all_items = []
            for cat_key, items in groups.items():
                for item_id, item in items:
                    effects = item.get("effects", {}) or {}
                    entry = {
                        "shop_category": CATEGORY_NAMES.get(cat_key, cat_key),
                        "category_key": cat_key,
                        "name": item.get("name", item_id),
                        "item_id": item_id,       # ⭐ 显式 key, LLM 直接拿这个传给 do_buy_shop_item
                        "id": item_id,            # 保留 alias 兼容
                        "tier": item.get("tier", 1),
                        "rarity": item.get("rarity", "common"),
                        "subcategory": item.get("subcategory", ""),
                        "category": item.get("category", "item"),
                        "type": item.get("type", "物品"),
                        "price": item.get("price", 0),
                        "emoji": item.get("emoji", "📦"),
                        "effects": effects,
                    }
                    if effects:
                        entry["effect_summary"] = _format_food_effects_zh(effects)
                    all_items.append(entry)
            # 排序: 食物在前, 其余按 tier
            all_items.sort(key=lambda x: (0 if x.get("category") == "food" else 1, x.get("tier", 1), x.get("price", 0)))
            return self._wrap_with_sender({
                "status": "success",
                "items": all_items,
                "categories": {k: CATEGORY_NAMES.get(k, k) for k in groups.keys()},
                "count": len(all_items),
                "message": f"商店有 {len(all_items)} 件商品, 分 4 类: 食物/药品/装备/渔具. 让玩家 /商店 看 UI, LLM 用 item_id 字段买",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_stock")
    async def llm_view_stock(self, event: AstrMessageEvent) -> dict:
        """【只读】查询股市行情和玩家持仓。

        玩家问"股市"、"我持有哪些股票"、"某股票现在多少钱"时调用。

        Returns:
            dict: {status, holdings: {stock_name: shares}, market_summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        try:
            from .modules.stock import STOCKS, get_user_stocks
            # get_user_stocks 不存在时降级到 user dict 原字段 (老数据兼容)
            holdings = get_user_stocks(user) if hasattr(get_user_stocks, "__call__") else user.get("stock_holdings", {})
            return self._wrap_with_sender({
                "status": "success",
                "holdings": holdings,
                "available_stocks": list(STOCKS.keys()) if STOCKS else [],
                "gold_available": user.get("gold", 0),
                "message": f"你持有 {len(holdings)} 只股票, 详情让玩家 /股市 看图",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_help")
    async def llm_view_help(self, event: AstrMessageEvent) -> dict:
        """【只读】给真人发"帮助"卡片图。

        玩家问"有什么命令"、"怎么玩"、"帮助"时调用。

        Returns:
            dict: {status, summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        try:
            url = await self._renderer.render_help(event)
            sent = await self._send_image_to_user(event, url or "")
            return self._wrap_with_sender({
                "status": "success" if sent else "fallback_text",
                "image_sent": sent,
                "message": "帮助图已发给玩家" if sent else "渲染失败",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_settings")
    async def llm_view_settings(self, event: AstrMessageEvent) -> dict:
        """【只读】查询玩家当前设置（订阅/通知/日报等）。

        玩家问"我的设置"、"我订阅了什么"、"通知开没开"时调用。

        Returns:
            dict: {status, settings, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        try:
            settings = await self._store.get_user_settings(ctx["user_id"])
            return self._wrap_with_sender({
                "status": "success",
                "settings": settings,
                "message": "玩家设置已返回",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="view_residence")
    async def llm_view_residence(self, event: AstrMessageEvent) -> dict:
        """【只读】查询玩家当前住所和房租情况。

        玩家问"我住哪"、"我的住所"、"房租"时调用。

        Returns:
            dict: {status, residence, summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        return self._wrap_with_sender({
            "status": "success",
            "residence": user.get("residence", "桥下"),
            "gold": user.get("gold", 0),
            "message": f"你当前住在 {user.get('residence', '桥下')}, 金币 {user.get('gold', 0)}",
        }, ctx)

    @filter.llm_tool(name="view_equipment")
    async def llm_view_equipment(self, event: AstrMessageEvent) -> dict:
        """【只读】查询玩家当前装备。

        玩家问"我的装备"、"我穿了什么"、"装备"时调用。

        Returns:
            dict: {status, equipped_items, summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        eq = user.get("equipped_items", {})
        return self._wrap_with_sender({
            "status": "success",
            "equipped_items": eq,
            "summary": "无装备" if not eq else f"装备 {len(eq)} 件: {', '.join(eq.keys())}",
            "message": f"装备: {', '.join(eq.keys()) if eq else '无'}",
        }, ctx)

    @filter.llm_tool(name="view_fishing_gear")
    async def llm_view_fishing_gear(self, event: AstrMessageEvent) -> dict:
        """【只读】查询玩家渔具 5 槽装备状态。

        玩家问"我的渔具"、"钓鱼竿"、"我用什么装备钓鱼"时调用。

        渔具双轨制 (9/3): 5 槽独立于通用装备系统
        - fishing_rod (鱼竿)
        - line (鱼线)
        - hook (鱼钩)
        - float (浮漂)
        - bait (鱼饵)

        Returns:
            dict: {status, fishing_gear: {slot: item}, effects_summary, _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        equipped = user.get("equipped_items", {})
        # 9/3晚: 加 reel 槽 (鱼轮: 钓鱼经验加成 + rare_bonus + duration_reduce)
        gear_slots = ["fishing_rod", "line", "hook", "float", "bait", "reel"]
        gear = {s: equipped.get(s) for s in gear_slots if equipped.get(s)}
        empty_slots = [s for s in gear_slots if not equipped.get(s)]
        return self._wrap_with_sender({
            "status": "success",
            "fishing_gear": gear,
            "equipped_count": len(gear),
            "empty_slots": empty_slots,
            "summary": f"渔具 {len(gear)}/6 件: {', '.join(gear.keys())}" if gear else "渔具: 无",
            "message": f"渔具 {len(gear)}/6 件: {', '.join(gear.keys())}" if gear else "渔具: 无装备 (使用默认虚拟竹竿+空手)",
        }, ctx)

    @filter.llm_tool(name="view_available_jobs")
    async def llm_view_available_jobs(self, event: AstrMessageEvent) -> dict:
        """【只读】查询当前玩家可接取的委托列表（基于等级和属性筛选）。

        玩家问"我能接什么委托"、"有什么委托"、"打工选项"时调用。
        LLM 可以根据这个列表建议玩家接哪个, 但实际接取要玩家输入 /打工 自己选。

        Returns:
            dict: {status, available_jobs: [{id, name, difficulty, reward, required_skills}], _sender}
        """
        ctx = await self._get_sender_context(event)
        if not ctx["user_id"]:
            return self._wrap_with_sender({"status": "error", "message": "无法识别身份"}, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "not_registered", "message": "玩家还没注册"}, ctx)
        try:
            from .src.commands.interactive import get_job_mgr
            jmgr = get_job_mgr()
            # JobManager 用 generate_job_pool(user, count) 生成可用委托池
            available_pool = jmgr.generate_job_pool(user, count=10)
            jobs_data = []
            for job in available_pool[:10]:
                # job 是 Job dataclass, 用 to_dict() 序列化
                if hasattr(job, "to_dict"):
                    snap = job.to_dict()
                elif isinstance(job, dict):
                    snap = job
                else:
                    snap = {"name": str(job)}
                jobs_data.append({
                    "id": snap.get("id", snap.get("name", "?")),
                    "name": snap.get("name", "?"),
                    "reward_gold": snap.get("reward_gold", snap.get("gold", 0)),
                    "required_skills": snap.get("required_skills", {}),
                    "duration_hours": snap.get("duration_hours", 0),
                })
            return self._wrap_with_sender({
                "status": "success",
                "available_jobs": jobs_data,
                "count": len(jobs_data),
                "message": f"可接委托 {len(jobs_data)} 个, 让玩家用 /打工 查看详情",
            }, ctx)
        except Exception as e:
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    # ========================================================
    # 写入工具 (do_xxx) —— 9/3 session 安全规范
    # 模式: _check_identity → 临时替换 event.message_str → _run_command_for_llm → 主动确认
    # 所有写入工具都接受 target_user_id 参数, 强制验证 == _sender.user_id
    # ========================================================

    async def _check_write_permission(self, event: AstrMessageEvent, target_user_id: str) -> tuple[dict | None, dict]:
        """统一身份验证。返回 (None, ctx) 表示通过, (error_dict, ctx) 表示拒绝."""
        ctx = await self._get_sender_context(event)
        real_uid = ctx["user_id"]
        if not real_uid:
            return ({"status": "error", "reason": "无法识别当前玩家身份, 拒绝执行"}, ctx)
        if target_user_id and str(target_user_id) != real_uid:
            return ({
                "status": "error",
                "reason": (
                    f"❌ 拒绝执行: 目标玩家 {target_user_id} != 当前真实发消息的玩家 {real_uid} ({ctx['nickname']}). "
                    f"LLM 不准代替群里其他玩家调用高风险操作。"
                ),
            }, ctx)
        return (None, ctx)

    @filter.llm_tool(name="do_checkin")
    async def llm_do_checkin(self, event: AstrMessageEvent, target_user_id: str = "") -> dict:
        """【写入】帮当前玩家签到（自动注册）。每日一次, 给金币/经验。

        玩家明确说"帮我签到"、"签到吧"时调用。如果玩家今天已经签到, 会告诉玩家。

        Args:
            target_user_id(string): 必须等于 _sender.user_id (强制)

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        result = await self._run_command_for_llm(
            event, run_checkin_logic, self._store, self._sender, fake_cmd="签到"
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_cancel")
    async def llm_do_cancel(self, event: AstrMessageEvent, target_user_id: str = "") -> dict:
        """【写入】取消当前玩家的进行中动作（打工/学习/娱乐/钓鱼等）。

        Args:
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        result = await self._run_command_for_llm(
            event, run_cancel_logic, self._store, self._sender, fake_cmd="取消"
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_work")
    async def llm_do_work(
        self,
        event: AstrMessageEvent,
        job_name: str = "",
        hours: int = 4,
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家接取委托开始打工（中等风险 - 扣属性、可能失败）。

        玩家明确说"帮我打工"、"去送外卖 4 小时"时调用。
        推测玩家意图 ("要不要去打工?") 时, 先告诉玩家预估收益再确认。

        Args:
            job_name(string): 工作名（如"外卖"、"快递"），必填或留空走推荐
            hours(number): 工时，默认4小时
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        from .src.commands.interactive import get_job_mgr, get_favor_mgr
        jmgr = get_job_mgr()
        fmgr = get_favor_mgr()
        # 构造命令字符串: "打工 外卖 4"
        cmd = "打工"
        if job_name:
            cmd += f" {job_name}"
        if hours and hours > 0:
            cmd += f" {hours}"
        result = await self._run_command_for_llm(
            event, run_work_logic, self._store, self._parser, jmgr, fmgr, self._sender,
            fake_cmd=cmd,
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_learn")
    async def llm_do_learn(
        self,
        event: AstrMessageEvent,
        course_name: str = "",
        hours: int = 4,
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家开始学习（中等风险 - 扣金币、长时间 tick）。

        Args:
            course_name(string): 课程名（如"编程"、"英语"），必填或留空走推荐
            hours(number): 学时，默认4小时
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "学习"
        if course_name:
            cmd += f" {course_name}"
        if hours and hours > 0:
            cmd += f" {hours}"
        result = await self._run_command_for_llm(
            event, run_learn_logic, self._store, self._parser, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_entertain")
    async def llm_do_entertain(
        self,
        event: AstrMessageEvent,
        entertainment_name: str = "",
        hours: int = 2,
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家开始娱乐（中等风险 - 扣金币、扣属性）。

        Args:
            entertainment_name(string): 娱乐项目（如"游戏"、"唱歌"），必填或留空走推荐
            hours(number): 时长，默认2小时
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "娱乐"
        if entertainment_name:
            cmd += f" {entertainment_name}"
        if hours and hours > 0:
            cmd += f" {hours}"
        result = await self._run_command_for_llm(
            event, run_entertain_logic, self._store, self._parser, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_eat")
    async def llm_do_eat(
        self,
        event: AstrMessageEvent,
        food_name: str = "",
        quantity: int = 1,
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家吃东西（低风险 - 扣饱食度/金币，看吃什么）。

        **前提：食物必须在背包里**。如背包没有, 先调 `do_buy_shop_item` 买一个。
        **quantity 支持批量吃** (默认 1): 例如背包有 3 个泡面, quantity=3 一次吃完 (属性 = 单份 × N), 比循环 3 次更快.

        Args:
            food_name(string): 食物名（如"泡面"、"汉堡"），必填或留空走推荐
            quantity(number): 吃几个, 默认 1, 上限 10 (避免误操作)
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        # 数量校验
        try:
            qty = int(quantity) if quantity else 1
        except (ValueError, TypeError):
            qty = 1
        if qty < 1:
            qty = 1
        if qty > 10:
            return self._wrap_with_sender({
                "status": "error",
                "reason": f"❌ quantity={qty} 超过单次上限 10, 请分批吃",
            }, ctx)
        if not food_name:
            return self._wrap_with_sender({
                "status": "error",
                "reason": "❌ food_name 不能为空. 留空会走背包+商店推荐列表, 想批量吃请指定具体食物名",
            }, ctx)
        # 走单次命令, 让 run_eat_logic 内部批量处理 (方案 B)
        # 9/3: 数字 selector (args[1]) 直接走批量路径 (群聊和 LLM 共用)
        cmd = f"吃 {food_name} {qty}"
        result = await self._run_command_for_llm(
            event, run_eat_logic, self._store, self._parser, self._renderer, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        result["quantity_requested"] = qty
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_buy_shop_item")
    async def llm_do_buy_shop_item(
        self,
        event: AstrMessageEvent,
        item_name: str = "",
        item_id: str = "",
        quantity: int = 1,
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家从商店买物品（中风险 - 扣金币, 买错不能退）。

        工作流: 先调 view_shop 查商品, 拿到 item_id, 再调本工具传 item_id 优先匹配。
        **买前必须调 get_player_status 确认 gold >= price × quantity**。

        常见用途:
        - 买食物再调 do_eat (恢复饱食度/健康)
        - 买装备再调 do_equip (穿戴)
        - 买药品直接用

        Args:
            item_name(string): 物品名（如"泡面"、"止痛药"）—— fallback 用, 优先用 item_id
            item_id(string): 物品 ID (view_shop 返回的 item_id 字段), 优先匹配
            quantity(number): 数量，默认1
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        if not item_name and not item_id:
            return self._wrap_with_sender({
                "status": "error",
                "reason": "❌ item_id 和 item_name 不能同时为空. 建议先调 view_shop 拿 item_id, 再传 item_id 给我.",
            }, ctx)
        user = await self._store.get_user(ctx["user_id"])
        if not user:
            return self._wrap_with_sender({"status": "error", "message": "用户不存在"}, ctx)
        try:
            from .modules.constants import ITEMS
            from .modules.shop import buy_item, get_sellable_items
            # 优先用 item_id, fallback 用 item_name
            resolved_item_id = None
            if item_id and item_id in ITEMS:
                resolved_item_id = item_id
            elif item_name:
                for iid, it in ITEMS.items():
                    if it.get("name") == item_name or iid == item_name:
                        resolved_item_id = iid
                        break
            if not resolved_item_id:
                return self._wrap_with_sender({
                    "status": "error",
                    "reason": f"❌ 找不到物品: item_id={item_id!r} item_name={item_name!r}",
                }, ctx)
            # 9/4: 检查物品是否在商店中 (可售卖)
            groups = get_sellable_items()
            in_shop = any(resolved_item_id in [iid for iid, _ in items] for items in groups.values())
            if not in_shop:
                return self._wrap_with_sender({
                    "status": "error",
                    "reason": f"❌ {ITEMS[resolved_item_id].get('name', resolved_item_id)} 不可购买 (无价格或非卖品)",
                }, ctx)
            qty = int(quantity) if quantity and int(quantity) > 0 else 1
            price = ITEMS[resolved_item_id].get("price", 0) * qty
            if user.get("gold", 0) < price:
                return self._wrap_with_sender({
                    "status": "error",
                    "reason": f"❌ 金币不足！需要 {price}, 你只有 {int(user.get('gold', 0))}",
                }, ctx)
            # 调 buy_item 新签名 (plugin, user, item_id, quantity) - 无需 shop_id
            success, msg = buy_item(self, user, resolved_item_id, qty)
            if not success:
                return self._wrap_with_sender({
                    "status": "error",
                    "reason": f"❌ 购买失败: {msg}",
                }, ctx)
            gold_after = user.get("gold", 0)
            await self._store.update_user(ctx["user_id"], user)
            # 主动发确认消息给真人
            try:
                await event.send(
                    MessageChain().at(ctx.get("nickname", ""), ctx["user_id"])
                    .message(f" ✅ 已购买 {ITEMS[resolved_item_id].get('name', resolved_item_id)} × {qty}, 花费 {price} 金币, 余额 {gold_after}")
                )
            except Exception:
                pass
            return self._wrap_with_sender({
                "status": "success",
                "item": ITEMS[resolved_item_id].get("name", resolved_item_id),
                "item_id": resolved_item_id,
                "quantity": qty,
                "price": price,
                "gold_after": gold_after,
                "message": f"成功购买 {qty} 个 {ITEMS[resolved_item_id].get('name', resolved_item_id)}, 花费 {price} 金币",
            }, ctx)
        except Exception as e:
            logger.error(f"[llm_tool do_buy_shop_item] exception: {e}", exc_info=True)
            return self._wrap_with_sender({"status": "error", "message": str(e)}, ctx)

    @filter.llm_tool(name="do_residence")
    async def llm_do_residence(
        self,
        event: AstrMessageEvent,
        action: str = "",
        residence_name: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家租/买房（中风险 - 买房大额金币）。

        Args:
            action(string): "租" 或 "买"
            residence_name(string): 住所名
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "住"
        if action:
            cmd += f" {action}"
        if residence_name:
            cmd += f" {residence_name}"
        result = await self._run_command_for_llm(
            event, run_residence_logic, self._store, self._parser, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_equip")
    async def llm_do_equip(
        self,
        event: AstrMessageEvent,
        item_name: str = "",
        action: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家穿/脱装备（低风险）。

        Args:
            item_name(string): 装备名
            action(string): "穿" / "脱" / "装备" (默认查装备列表)
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "装备"
        if item_name:
            cmd += f" {item_name}"
        if action:
            cmd += f" {action}"
        result = await self._run_command_for_llm(
            event, run_equip_logic, self._store, self._parser, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_fishing_gear")
    async def llm_do_fishing_gear(
        self,
        event: AstrMessageEvent,
        item_name: str = "",
        action: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家穿/脱渔具（低风险）。

        渔具双轨制 (9/3): 5 槽独立. 玩家说"换鱼钩"、"装备竹竿"时调用.

        Args:
            item_name(string): 渔具名(如"竹竿"、"尼龙线"、"钛合金钩"、"夜光漂"、"蚯蚓")或背包序号
            action(string): "装"/"装备"/"wear"/"卸"/"卸下"/"unequip" (默认查渔具状态)
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "渔具"
        if item_name:
            cmd += f" 装 {item_name}" if action in ("装", "装备", "wear", "equip", "") else f" 卸 {item_name}"
        result = await self._run_command_for_llm(
            event, run_fishing_gear_logic, self._store, self._parser, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_complete_job")
    async def llm_do_complete_job(
        self,
        event: AstrMessageEvent,
        job_id: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家完成进行中的委托（中风险 - 结算金币/属性）。

        Args:
            job_id(string): 委托ID（可选, 不传完成第一个可完成的）
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "完成委托"
        if job_id:
            cmd += f" {job_id}"
        result = await self._run_command_for_llm(
            event, run_complete_job_logic, self._store, self._parser, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_cancel_job")
    async def llm_do_cancel_job(
        self,
        event: AstrMessageEvent,
        job_id: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家取消进行中的委托（低风险）。

        Args:
            job_id(string): 委托ID（可选, 不传取消第一个）
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "取消委托"
        if job_id:
            cmd += f" {job_id}"
        result = await self._run_command_for_llm(
            event, run_cancel_job_logic, self._store, self._parser, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_fishing_start")
    async def llm_do_fishing_start(
        self,
        event: AstrMessageEvent,
        spot_id: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家开始钓鱼（低风险 - 启动 tick 任务）。

        Args:
            spot_id(string): 钓点ID（可选, 不传走默认）
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "钓鱼"
        if spot_id:
            cmd += f" {spot_id}"
        result = await self._run_command_for_llm(
            event, run_fishing_logic, self._store, self._sender, fake_cmd=cmd
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

    @filter.llm_tool(name="do_settings")
    async def llm_do_settings(
        self,
        event: AstrMessageEvent,
        setting_key: str = "",
        setting_value: str = "",
        target_user_id: str = "",
    ) -> dict:
        """【写入】帮当前玩家改设置（低风险 - 通知订阅/日报）。

        Args:
            setting_key(string): 设置项（如"通知"、"订阅"、"日报"）
            setting_value(string): 设置值（如"开"、"关"、"23:00"）
            target_user_id(string): 必须等于 _sender.user_id

        Returns:
            dict: {status, last_text, _sender}
        """
        err, ctx = await self._check_write_permission(event, target_user_id)
        if err:
            return self._wrap_with_sender(err, ctx)
        cmd = "设置"
        if setting_key:
            cmd += f" {setting_key}"
        if setting_value:
            cmd += f" {setting_value}"
        result = await self._run_command_for_llm(
            event, run_settings_logic, self._store, self._parser,
            self._get_group_config, self._save_group_config,
            fake_cmd=cmd,
        )
        result["_sender"] = {"user_id": ctx["user_id"], "nickname": ctx["nickname"]}
        return self._wrap_with_sender(result, ctx)

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

        # 9/4: 钓鱼技能曲线升级 - 老用户经验迁移 (只跑一次)
        await self._migrate_fishing_exp_once()

        # 注册 LLM Tools (供丽贝卡 persona 调用)
        register_game_tools(self)

        # 启动主循环
        task1 = asyncio.create_task(self._tick_loop())
        self._background_tasks.append(task1)

        # 启动通知 consumer（方案G：tick 发消息走这里）
        task2 = asyncio.create_task(self._notification_consumer())
        self._background_tasks.append(task2)

        logger.info("Tick系统已启动 (基于时间触发)")

    async def _migrate_fishing_exp_once(self):
        """9/4: 钓鱼技能曲线升级 - 老用户降级到应有水平

        原曲线 standard (1-10级, 满5400), 新曲线 fishing_30 (1-30级, 满855500)
        原曲线太快, 用户等级虚高 (5400 exp 就满级)
        新曲线 N 平方, 5400 exp 在新曲线只对应 Lv5

        设计: 不动 skill_exp, 让 get_skill_level 按新曲线自动重新查等级
              老用户等级自然下降, 但他们的进度条也会变低
              体验: 用户感觉从"满级"变成"中等", 知道还有大量升级空间
        """
        # 不做数据迁移, 只是日志记录
        logger.info("[MIGRATION] 钓鱼技能曲线升级 (standard -> fishing_30)")
        logger.info("[MIGRATION] 老用户经验保留, 等级按新曲线重新计算")
        logger.info("[MIGRATION] 无需数据迁移, get_skill_level 自动用 fishing_30")

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
        last_cache_log = 0.0
        while True:
            try:
                await asyncio.sleep(self._tick_interval)
                now = datetime.now(LOCAL_TZ)

                # 每 10 分钟输出渲染缓存统计
                import time as _t
                if _t.time() - last_cache_log > 600 and hasattr(self, "_renderer"):
                    try:
                        stats = self._renderer.cache_stats()
                        logger.info(
                            f"[NiumaLife] 渲染缓存统计: {stats['hits']} 命中 / "
                            f"{stats['misses']} 未命中 ({stats['hit_rate']}), "
                            f"{stats['size']} 项"
                        )
                    except Exception as e:
                        logger.debug(f"cache stats failed: {e}")
                    last_cache_log = _t.time()

                # 处理所有空闲用户的被动恢复
                try:
                    await self._process_all_free_passive_recovery(now)
                except Exception as e:
                    logger.warning(f"_process_all_free_passive_recovery 异常: {type(e).__name__}: {str(e)}")

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

 
 
