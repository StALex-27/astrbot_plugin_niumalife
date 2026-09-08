"""
消息管理器 - 集中管理所有消息发送
牛马人生项目

职责：
- 统一消息发送入口（文本 / 卡片）
- 判断消息类型是否需要渲染卡片
- 后台任务（tick）完成通知的主动推送
- 兼容命令响应和后台推送两种调用模式

9/5 重构：_send_platform_message 不再走 StarTools.send_message（platform_id 解析有 bug），
改用 main.py 的 _notify_queue + 缓存 event 方案，与 tick.py 的 _notify_catch / _notify_empty
走同一条路，避免 3 套发送路径并存（ARCHITECTURE.md L4 设计目标）。
"""

from enum import Enum, auto
from typing import Optional, Dict, Any

from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain


class _EventProxy:
    """
    轻量事件代理，用于后台通知（event=None）场景。
    只实现 renderer 方法实际用到的 get_sender_id()。
    """
    def __init__(self, user_id: str):
        self._user_id = user_id

    def get_sender_id(self) -> str:
        return self._user_id

    def is_private_chat(self) -> bool:
        return True  # 后台通知默认发私聊

    def get_group_id(self) -> Optional[str]:
        return None


class MessageType(Enum):
    """消息类型枚举，定义哪些消息需要渲染卡片"""
    # ---- 纯文本类（不发卡片）----
    PLAIN = auto()          # 纯文本提醒/简单提示
    ERROR = auto()          # 错误提示（可渲染 error 卡片或纯文本）
    SUCCESS = auto()        # 成功提示（可渲染 success 卡片或纯文本）
    DAILY_REPORT = auto()   # 日报（群/个人，已有自己的卡片逻辑）

    # ---- 卡片渲染类（需要生成图片）----
    PROFILE = auto()        # 档案卡片
    STATUS = auto()         # 状态卡片
    WORK_RESULT = auto()    # 工作结果卡片
    LEARN_RESULT = auto()   # 学习结果卡片
    ENTERTAIN_RESULT = auto()  # 娱乐结果卡片
    FOOD_RESULT = auto()    # 吃饭结果卡片
    CHECKIN = auto()        # 签到卡片
    CHECKIN_STATS = auto()  # 签到统计卡片
    BUFF_LIST = auto()      # buff 列表卡片
    JOB_LIST = auto()       # 委托池列表卡片
    COURSE_LIST = auto()    # 课程列表卡片
    FOOD_LIST = auto()      # 食物列表卡片
    HOUSING_LIST = auto()   # 住房列表卡片
    ENTERTAINMENT_LIST = auto()  # 娱乐列表卡片
    RESIDENCE = auto()      # 住所卡片
    SHOP = auto()           # 商店卡片
    STOCK = auto()          # 股市卡片
    BACKPACK = auto()       # 背包卡片
    HELP = auto()           # 帮助卡片

    # ---- 后台通知类（tick 完成推送）----
    NOTIFY_WORK_COMPLETE = auto()   # 工作完成通知
    NOTIFY_LEARN_COMPLETE = auto()   # 学习完成通知
    NOTIFY_ENTERTAIN_COMPLETE = auto()  # 娱乐完成通知
    NOTIFY_EAT_COMPLETE = auto()     # 吃饭完成通知
    NOTIFY_LOW_ATTR = auto()         # 属性过低警告
    NOTIFY_RENT_DUE = auto()         # 房租到期提醒
    NOTIFY_BUFF_EXPIRE = auto()      # buff 即将过期提醒
    NOTIFY_STOCK_ALERT = auto()      # 股价提醒


# 配置：哪些 MessageType 默认需要渲染卡片
# 设为 False 则始终发纯文本（更快更轻量）
RENDER_CARD_BY_DEFAULT: Dict[MessageType, bool] = {
    # 纯文本类
    MessageType.PLAIN: False,
    MessageType.ERROR: False,
    MessageType.SUCCESS: False,
    MessageType.DAILY_REPORT: False,  # 日报有自己独立的渲染逻辑

    # 卡片渲染类
    MessageType.PROFILE: True,
    MessageType.STATUS: True,
    MessageType.WORK_RESULT: True,
    MessageType.LEARN_RESULT: True,
    MessageType.ENTERTAIN_RESULT: True,
    MessageType.FOOD_RESULT: True,
    MessageType.CHECKIN: True,
    MessageType.CHECKIN_STATS: True,
    MessageType.BUFF_LIST: True,
    MessageType.JOB_LIST: True,
    MessageType.COURSE_LIST: True,
    MessageType.FOOD_LIST: True,
    MessageType.HOUSING_LIST: True,
    MessageType.ENTERTAINMENT_LIST: True,
    MessageType.RESIDENCE: True,
    MessageType.SHOP: True,
    MessageType.STOCK: True,
    MessageType.BACKPACK: True,
    MessageType.HELP: True,

    # 后台通知类（默认不发卡片，只有用户主动开启才发）
    MessageType.NOTIFY_WORK_COMPLETE: False,
    MessageType.NOTIFY_LEARN_COMPLETE: False,
    MessageType.NOTIFY_ENTERTAIN_COMPLETE: False,
    MessageType.NOTIFY_EAT_COMPLETE: False,
    MessageType.NOTIFY_LOW_ATTR: False,
    MessageType.NOTIFY_RENT_DUE: False,
    MessageType.NOTIFY_BUFF_EXPIRE: False,
    MessageType.NOTIFY_STOCK_ALERT: False,
}


class Messenger:
    """
    集中消息管理器

    使用方式：

    1. 命令响应（事件上下文中）：
       async for chunk in messenger.send(event, MessageType.PROFILE, data):
           yield chunk

    2. 后台推送（非事件上下文）：
       await messenger.push(user_id, MessageType.NOTIFY_WORK_COMPLETE, data)

    卡片渲染偏好由用户设置控制：
    - notification_card_mode: "always" | "never" | "smart"（默认 smart）
      - always: 所有支持卡片的类型都渲染卡片
      - never: 全部发纯文本
      - smart: 按 RENDER_CARD_BY_DEFAULT 配置 + 用户 per-type 偏好
    """

    def __init__(self, plugin):
        """
        Args:
            plugin: NiumaLifePlugin 实例（提供 renderer / store / logger）
        """
        self._plugin = plugin
        self._renderer = plugin._renderer
        self._store = plugin._store

    # ============================================================
    # 内部工具方法
    # ============================================================

    def _should_render_card(self, msg_type: MessageType, user_id: str,
                            user_settings: Optional[dict] = None) -> bool:
        """判断某用户某消息类型是否应渲染卡片"""
        # 检查全局开关
        if not user_settings:
            return RENDER_CARD_BY_DEFAULT.get(msg_type, False)

        enabled = user_settings.get("notification_enabled", True)
        if not enabled:
            return False

        card_mode = user_settings.get("notification_card_mode", "smart")

        if card_mode == "never":
            return False
        if card_mode == "always":
            return msg_type in RENDER_CARD_BY_DEFAULT  # 只对有渲染方法的类型有效

        # smart 模式：按类型默认配置走
        return RENDER_CARD_BY_DEFAULT.get(msg_type, False)

    async def _render_card(self, msg_type: MessageType, data: dict) -> Optional[str]:
        """调用 renderer 渲染卡片，返回图片 URL"""
        renderer = self._renderer

        # 后台推送时 event 为 None，需要创建轻量代理
        event = data.get("event")
        if event is None:
            user_id = data.get("user_id")
            if user_id:
                event = _EventProxy(user_id)

        try:
            if msg_type == MessageType.PROFILE:
                return await renderer.render_profile(data["user"], event)
            elif msg_type == MessageType.STATUS:
                return await renderer.render_status(data["user"], event)
            elif msg_type == MessageType.CHECKIN:
                return await renderer.render_checkin(
                    data["user"], event,
                    data["result"], data.get("already_checked", False)
                )
            elif msg_type == MessageType.CHECKIN_STATS:
                return await renderer.render_checkin_stats(data["user"], event)
            elif msg_type == MessageType.BUFF_LIST:
                return await renderer.render_buff_list(data["user"], event)
            elif msg_type == MessageType.JOB_LIST:
                return await renderer.render_job_list(
                    data["jobs"], data["user"], event
                )
            elif msg_type == MessageType.WORK_RESULT:
                return await renderer.render_job_start(
                    data["user"], event,
                    data["job_name"], data["job_emoji"],
                    data["hours"],
                    data["expected_gold"],
                    data["expected_exp"],
                    data.get("consume_strength", 0),
                    data.get("consume_energy", 0),
                    data.get("consume_satiety", 0),
                    data.get("active_buffs"),
                )
            elif msg_type == MessageType.COURSE_LIST:
                return await renderer.render_course_list(
                    data["courses"], data["user"], event
                )
            elif msg_type == MessageType.FOOD_LIST:
                return await renderer.render_food_list(
                    data["foods"], data["user"], event
                )
            elif msg_type == MessageType.FOOD_RESULT:
                return await renderer.render_eat(
                    data["user"], event,
                    data["food_name"], data["food_emoji"],
                    data.get("restore_health", 0),
                    data.get("restore_strength", 0),
                    data.get("restore_energy", 0),
                    data.get("restore_mood", 0),
                )
            elif msg_type == MessageType.RESIDENCE:
                return await renderer.render_residence(
                    data["user"], event, data.get("residence_info")
                )
            elif msg_type == MessageType.HOUSING_LIST:
                return await renderer.render_housing_list(
                    data["rentals"], data["purchases"], data["user"], event
                )
            elif msg_type == MessageType.ENTERTAINMENT_LIST:
                return await renderer.render_entertainment_list(
                    data["entertainments"], data["user"], event
                )
            elif msg_type == MessageType.ENTERTAIN_RESULT:
                return await renderer.render_entertain_start(
                    data["user"], event,
                    data["ent_name"], data["ent_emoji"], data["hours"],
                    data.get("gain_mood", 0),
                    data.get("consume_satiety", 0),
                )
            elif msg_type == MessageType.STOCK:
                return await renderer.render_generic(
                    data["content"], event, data.get("height", 400)
                )
            elif msg_type == MessageType.HELP:
                return await renderer.render_help(event)
            elif msg_type == MessageType.SUCCESS:
                return await renderer.render_success(data["message"], event)
            elif msg_type == MessageType.ERROR:
                return await renderer.render_error(
                    data.get("title", "出错了"), data["message"], event
                )
            # 后台通知类（目前不发卡片）
            return None
        except Exception as e:
            self._plugin.logger.error(f"卡片渲染失败 [{msg_type.name}]: {e}")
            return None

    async def _send_platform_message(
        self,
        platform_msg_type: str,   # "GroupMessage" | "PrivateMessage" (保留签名兼容, 实际不再用)
        target_id: str,
        text: Optional[str] = None,
        image_url: Optional[str] = None,
        session_key: str = "",
    ):
        """实际发送平台消息（文本 或/和 图片）。

        9/5 重构：tick 后台通知改走 main.py 已有的 _notify_queue + 缓存 event 方案，
        跟随发起会话（群/私聊），不切换窗口。彻底避开 StarTools.send_message 的
        platform_id 解析问题。

        Args:
            platform_msg_type: 保留参数，仅用于日志区分（已不再用于路由）。
            target_id: 用户 ID（QQ 号）。
            text: 文本消息内容。
            image_url: 图片 URL 或本地路径。
        """
        if not text and not image_url:
            return

        # 构造 MessageChain (用本地路径走 file_image, http 走 url_image, 与 _LocalRenderer 对齐)
        chain = MessageChain()
        if text:
            chain = chain.message(text)
        if image_url:
            if image_url.startswith(("http://", "https://")):
                chain = chain.url_image(image_url)
            else:
                chain = chain.file_image(image_url)

        # 9/6: 走 _notify_queue: 后台 _notification_consumer 用缓存的 event.send
        # 同时入队 (user_id, msg_chain, session_key) - consumer 按 session_key 查找 event
        queue = getattr(self._plugin, "_notify_queue", None)
        if queue is None:
            self._plugin.logger.error(f"[Messenger] _notify_queue 未初始化, 通知丢弃 user={target_id}")
            return

        # 9/6: 优先用 caller 传的 session_key (Pattern 10)
        # 留空时才走反查 fallback (旧行为)
        if not session_key:
            try:
                from src.ui.message_sender import _extract_session_key  # type: ignore
            except ImportError:
                _extract_session_key = None  # 测试 / 单文件运行 fallback
            best = self._infer_recent_event(target_id)
            if best is not None and _extract_session_key is not None:
                try:
                    session_key = _extract_session_key(best) or ""
                except Exception:
                    session_key = ""

        # 持久化路径: 如果 queue 满了 / 拿不到 event, 走 sender.notify() 落 KV
        # 此处保持简化: 入队, consumer 找不到 event 时由 sender.notify 重试
        await queue.put((target_id, chain, session_key))

    def _infer_recent_event(self, user_id: str):
        """反查 user_id 最近一次活跃的 event (兼容旧 _recent_event dict)。"""
        # 新版 _recent_events (session_key -> event)
        events = getattr(self._plugin, "_recent_events", None)
        if events:
            best = None
            best_time = 0.0
            for ev in events.values():
                sender_id = ""
                try:
                    sender_id = str(ev.get_sender_id())
                except Exception:
                    continue
                if sender_id == user_id:
                    t = getattr(ev, "_niuma_cached_at", 0)
                    if t > best_time:
                        best = ev
                        best_time = t
            return best
        # 兼容旧 _recent_event (user_id -> event)
        old = getattr(self._plugin, "_recent_event", None)
        if isinstance(old, dict):
            return old.get(user_id)
        return None

    # ============================================================
    # 命令响应模式（事件上下文中使用 yield）
    # ============================================================

    async def send(
        self,
        event,
        msg_type: MessageType,
        data: dict,
        user_settings: Optional[dict] = None
    ):
        """
        命令响应模式：生成消息，通过 event yield 返回

        Args:
            event: AstrMessageEvent 实例
            msg_type: 消息类型
            data: 渲染所需的数据（包含 event）
            user_settings: 用户设置（可选）

        Yields:
            event.plain_result(str) 或 event.image_result(str)
        """
        user_id = str(event.get_sender_id())
        if user_settings is None:
            user_settings = {}

        should_card = self._should_render_card(msg_type, user_id, user_settings)
        image_url = None

        if should_card:
            image_url = await self._render_card(msg_type, data)

        text = data.get("plain_text")  # 降级文本（可选）

        if image_url:
            yield event.image_result(image_url)
        elif text:
            yield event.plain_result(text)
        else:
            # 没有图片也没有文本 → 静默（不应该发生）
            pass

    # ============================================================
    # 后台推送模式（非事件上下文）
    # ============================================================

    async def push(
        self,
        user_id: str,
        msg_type: MessageType,
        data: dict,
        platform: str = "PrivateMessage",
        session_key: str = "",
    ):
        """
        后台推送模式：主动向用户发送通知

        Args:
            user_id: 用户 ID
            msg_type: 消息类型
            data: 消息内容数据
            platform: "PrivateMessage" | "GroupMessage"
            session_key: 9/6 完整 session_key。优先用此 key 查缓存 event。
                留空时回退到反查 _recent_events (旧行为)。
        """
        # 获取用户设置判断是否启用通知
        settings = await self._store.get_user_settings(user_id)
        if not settings.get("notification_enabled", True):
            return

        should_card = self._should_render_card(msg_type, user_id, settings)
        image_url = None
        text = data.get("plain_text")

        if should_card:
            image_url = await self._render_card(msg_type, data)

        # 后台通知默认只发文本（除非强制开卡）
        await self._send_platform_message(
            platform, user_id,
            text=text,
            image_url=image_url if should_card else None,
            session_key=session_key,
        )

    # ============================================================
    # 便捷封装：常用消息的快速发送
    # ============================================================

    async def notify_work_complete(self, user_id: str, job_name: str,
                                   earned_gold: int, event=None, session_key: str = ""):
        """工作完成通知（后台推送）

        Args:
            session_key: 9/6 完整 session_key (Pattern 10 通知跟随发起会话)。
                留空时回退到反查 _recent_events (旧行为, 可能被误发到群聊)。
        """
        await self.push(
            user_id,
            MessageType.NOTIFY_WORK_COMPLETE,
            {
                "plain_text": (
                    f"📋 {job_name} 已完成！\n"
                    f"💰 获得 {earned_gold} 金币"
                )
            },
            session_key=session_key,
        )

    async def notify_learn_complete(self, user_id: str, skill_name: str,
                                    earned_exp: int, event=None, session_key: str = ""):
        """学习完成通知

        Args:
            session_key: 9/6 完整 session_key (Pattern 10)。
        """
        await self.push(
            user_id,
            MessageType.NOTIFY_LEARN_COMPLETE,
            {
                "plain_text": (
                    f"📚 {skill_name} 学习完成！\n"
                    f"📈 获得 {earned_exp} 经验"
                )
            },
            session_key=session_key,
        )

    async def notify_entertain_complete(self, user_id: str, ent_name: str,
                                        mood_gain: int, event=None, session_key: str = ""):
        """娱乐完成通知

        Args:
            session_key: 9/6 完整 session_key (Pattern 10)。
        """
        await self.push(
            user_id,
            MessageType.NOTIFY_ENTERTAIN_COMPLETE,
            {
                "plain_text": (
                    f"🎮 {ent_name} 结束！\n"
                    f"😊 心情 +{mood_gain}"
                )
            },
            session_key=session_key,
        )

    async def notify_low_attr(self, user_id: str, attr_name: str, value: float):
        """属性过低警告"""
        icon_map = {
            "satiety": "🍖 饱食度",
            "mood": "😊 心情",
            "health": "❤️ 健康",
            "energy": "⚡ 精力",
            "strength": "💪 体力",
        }
        attr_label = icon_map.get(attr_name, attr_name)
        await self.push(
            user_id,
            MessageType.NOTIFY_LOW_ATTR,
            {
                "plain_text": (
                    f"⚠️ {attr_label} 过低！\n"
                    f"当前: {int(value)}\n"
                    f"建议尽快补充！"
                )
            }
        )
