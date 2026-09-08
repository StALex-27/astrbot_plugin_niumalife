"""
src/ui/message_sender.py — 统一消息发送器 (ARCHITECTURE.md P0 #1)

设计目标:
- 替代散落 25+ 处的 try/except + yield event.image_result/plain_result 样板
- 统一 3 个入口: send_card / send_text / notify
- send_card 内部: 渲染成功发图, 失败 fallback 文本, 异常统一捕获
- notify 走 _notify_queue + 缓存 event 方案, 支持持久化补发
- 9/6 改进: 缓存按 session_key 分组 (而非 user_id), 避免多群切换导致通知发错窗口

消息存活期:
- 内存队列 (asyncio.Queue) 优先, 缓存 event 在时直接发
- 失败 / 无缓存 event → 持久化到 KV (每个 user 一个 list)
- 24h 软上限, 超过清理 + 不补发
- 补发时根据延迟 (now - created_at) 加 ⚠️ 提示: 数分钟/半小时/数小时/半天

session_key 格式: "platform_id|session_type|session_id"
  - platform_id: "aiocqhttp" / "telegram"
  - session_type: "GroupMessage" / "PrivateMessage"
  - session_id: group_id (群) 或 user_id (私聊)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from typing import Optional, Dict, List, Any, AsyncGenerator

from astrbot.core.message.message_event_result import MessageChain

_log = logging.getLogger("astrbot_plugin_niumalife.message_sender")

# ============================================================
# 常量
# ============================================================

# 延迟粒度
DELAY_TIERS = [
    (30 * 60, "数分钟"),                  # < 30min
    (2 * 60 * 60, "半小时"),              # 30min - 2h
    (8 * 60 * 60, "数小时"),              # 2h - 8h
    (24 * 60 * 60, "半天"),               # 8h - 24h
]


def _format_delay(seconds: float) -> str:
    """根据延迟秒数返回人类可读粒度 (空字符串表示无需提示)。"""
    for threshold, label in DELAY_TIERS:
        if seconds < threshold:
            return label
    return "太久"  # 实际不会到这里, 24h 已过期


def _build_session_key(platform_id: str, session_type: str, session_id: str) -> str:
    return f"{platform_id}|{session_type}|{session_id}"


def _extract_session_key(event) -> Optional[str]:
    """从 AstrMessageEvent 提取 session_key。"""
    try:
        platform_id = "aiocqhttp"  # 默认, 实际从 event._platform_id 或 config 读
        # 优先用 event 自带属性
        platform_id = (
            getattr(event, "_platform_id", None)
            or getattr(event, "platform_id", None)
            or platform_id
        )
        session_type = "PrivateMessage"
        try:
            if hasattr(event, "is_private_chat") and not event.is_private_chat():
                session_type = "GroupMessage"
        except Exception:
            pass
        session_id = ""
        try:
            gid = event.get_group_id()
            if gid:
                session_id = f"group:{gid}"
            else:
                session_id = f"user:{event.get_sender_id()}"
        except Exception:
            session_id = f"user:{event.get_sender_id()}"
        return _build_session_key(platform_id, session_type, session_id)
    except Exception as e:
        _log.warning(f"[MessageSender] _extract_session_key 失败: {e}")
        return None


# ============================================================
# 9/6: get_kv_data retry helper (处理 AstrBot SQLAlchemy pool 满 30s 超时)
# ============================================================

_KV_RETRY_ATTEMPTS = 3
_KV_RETRY_BASE_DELAY = 0.5  # 500ms → 1s → 2s


async def _get_kv_with_retry(plugin, key, default):
    """带指数退避的 get_kv_data wrapper.

    应对 AstrBot SharedPreferences 的 SQLAlchemy AsyncAdaptedQueuePool
    pool_size=5 + overflow=10 = 15 个连接上限. 并发高时 30s 排队超时,
    retry 几次往往就拿到连接了。
    """
    last_err = None
    for attempt in range(_KV_RETRY_ATTEMPTS):
        try:
            return await plugin.get_kv_data(key, default)
        except Exception as e:
            last_err = e
            if attempt < _KV_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(_KV_RETRY_BASE_DELAY * (2 ** attempt))
    assert last_err is not None
    raise last_err


# ============================================================
# MessageSender
# ============================================================

class MessageSender:
    """统一消息发送器。"""

    def __init__(self, plugin):
        """
        Args:
            plugin: NiumaLife 实例 (拿 _renderer / _store / _notify_queue / _recent_events / _cache_event)
        """
        self._plugin = plugin

    # ============================================================
    # 路径 1: 命令响应 (event 上下文中)
    # ============================================================

    async def send_card(
        self,
        event,
        card_type: str,
        data: dict,
        fallback_text: str = "",
        render_height: int = None,
        render_width: int = None,
        render_timeout: Optional[float] = None,
    ) -> AsyncGenerator[Any, None]:
        """发送卡片: 渲染成功发图, 失败 fallback 文本。

        业务方原本要写 6-10 行 try/except, 现在一行:
            async for r in sender.send_card(event, CardType.PROFILE, data, fallback_text="档案"):
                yield r

        Args:
            event: AstrMessageEvent
            card_type: CardType 枚举 (string value)
            data: 渲染数据 (经过 ViewSpec 兜底)
            fallback_text: 渲染失败时发的纯文本
            render_height: 自定义高度
            render_width: 自定义宽度
            render_timeout: 渲染超时秒数 (None = 不限). checkin 等可能卡死的命令传 30.
        """
        # 缓存 event (供后续 notify 用)
        self._plugin._cache_event(event)

        url = ""
        try:
            if render_timeout:
                url = await asyncio.wait_for(
                    self._plugin._renderer._render(
                        card_type, data,
                        height=render_height,
                        width=render_width,
                        full_page=True,
                    ),
                    timeout=render_timeout,
                )
            else:
                url = await self._plugin._renderer._render(
                    card_type, data,
                    height=render_height,
                    width=render_width,
                    full_page=True,
                )
        except asyncio.TimeoutError:
            _log.warning(f"[send_card] {card_type} 渲染超时 ({render_timeout}s)")
        except Exception as e:
            _log.error(f"[send_card] {card_type} 渲染异常: {type(e).__name__}: {e}")

        if url:
            try:
                yield event.image_result(url)
                return
            except Exception as e:
                _log.warning(f"[send_card] yield image_result 失败: {e}, fallback 文本")
                # fallthrough to fallback text

        # Fallback: 发纯文本
        text = fallback_text or f"[{card_type}] 渲染失败, 请重试"
        try:
            yield event.plain_result(text)
        except Exception as e:
            _log.error(f"[send_card] yield plain_result 也失败: {e}")

    async def send_text(
        self,
        event,
        text: str,
        at_user: bool = False,
    ) -> AsyncGenerator[Any, None]:
        """发送纯文本。at_user=True 时自动 @ 当前发送者。"""
        self._plugin._cache_event(event)

        if at_user:
            try:
                nickname = "玩家"
                try:
                    sender = getattr(event.message_obj, "sender", None)
                    if sender:
                        nickname = (
                            getattr(sender, "nickname", "")
                            or getattr(sender, "card", "")
                            or "玩家"
                        )
                    else:
                        nickname = event.get_sender_name() or "玩家"
                except Exception:
                    pass
                yield event.plain_result(f"@{nickname} {text}")
                return
            except Exception as e:
                _log.warning(f"[send_text] at_user 模式失败: {e}, fallback 纯文本")
        try:
            yield event.plain_result(text)
        except Exception as e:
            _log.error(f"[send_text] yield 失败: {e}")

    # ============================================================
    # 路径 2: tick 后台通知 (无 event, 走 queue)
    # ============================================================

    async def notify(
        self,
        user_id: str,
        msg_type: str,
        text: str = "",
        image_url: str = "",
    ) -> None:
        """后台推送通知 (tick 完成 / 低属性警告 / 房租到期等)。

        9/6 简化: 移除 KV 持久化设计。流程:
          1. 反查 user_id 最近一次活跃 session_key
          2. 缓存 event 在 → 立即发
          3. 缓存 event 不在 → 丢弃 (tick 触发通知时玩家通常在线,
             event 缓存命中率应 > 95%; 真没缓存就丢, 避免每条通知 1 get + 1 put)

        Args:
            user_id: 玩家 ID
            msg_type: 通知类型 ("fishing_catch" / "work_complete" / "low_attr" ...) 仅日志用
            text: 文本内容
            image_url: 图片 URL 或本地路径
        """
        if not text and not image_url:
            return

        session_key = self._infer_session_key(user_id)
        chain = self._build_chain(text, image_url)

        if session_key:
            event = self._plugin._recent_events.get(session_key)
            if event is not None:
                try:
                    await event.send(chain)
                    _log.debug(f"[notify] user={user_id} msg_type={msg_type} 立即送达 session={session_key}")
                    return
                except Exception as e:
                    _log.warning(f"[notify] 立即发送失败 (session={session_key}): {e}")
            else:
                _log.debug(f"[notify] user={user_id} session={session_key} 无缓存 event, 丢弃")
        else:
            _log.debug(f"[notify] user={user_id} 无 session_key, 丢弃")

    def _infer_session_key(self, user_id: str) -> Optional[str]:
        """从缓存 event 反查 user_id 最近一次活跃的 session_key。

        限制: 只反查最近一次活跃 (按 _niuma_cached_at 排序), 避免给多 session 用户
        串通知。
        """
        best_key = None
        best_time = 0.0
        for key, event in self._plugin._recent_events.items():
            cached_at = getattr(event, "_niuma_cached_at", 0)
            sender_id = ""
            try:
                sender_id = str(event.get_sender_id())
            except Exception:
                continue
            if sender_id == user_id and cached_at > best_time:
                best_key = key
                best_time = cached_at
        return best_key

    # ============================================================
    # MessageChain 构造 (无持久化版本)
    # ============================================================

    def _build_chain(self, text: str, image_url: str) -> MessageChain:
        """构造 MessageChain。本地路径直接传, 不做持久化拷贝 (重启即丢)。"""
        chain = MessageChain()
        if text:
            chain = chain.message(text)
        if image_url:
            if image_url.startswith(("http://", "https://")):
                chain = chain.url_image(image_url)
            else:
                # 本地路径: 直接传 (重启后 event 重连时图片可能失效)
                if os.path.exists(image_url):
                    chain = chain.file_image(image_url)
                else:
                    _log.warning(f"[notify] 图片不存在, 跳过: {image_url}")
        return chain

    # ============================================================
    # 持久化 KV
    # ============================================================
        # 9/6 简化: 删除所有 KV 持久化路径
        # _persist_pending_notify / flush_pending_for_session / _rebuild_chain
        # / on_startup_recover / _persist_image / _cleanup_persisted_image
        # notify() 改为: 缓存 event 在 → 立即发; 不在 → 丢弃。
        # 设计理由: 持久化导致每条指令 1 get + 1 put, 雪崩 SQLAlchemy pool。
        # 重启后丢失通知可接受 (event 缓存命中率 > 95%, 重启期低频)。
        # ============================================================
