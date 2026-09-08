"""
tests/test_message_sender.py — MessageSender 单元测试

不依赖 AstrBot runtime: 用 stub plugin 模拟 get_kv_data / put_kv_data,
不直接调 event.send, 只测 MessageSender 的核心逻辑。

9/6 简化: 移除持久化/flush 测试 (相关代码已删除)。
保留测试:
- send_card: 渲染成功 / 渲染返回空 / 渲染异常
- send_text: at_user / 普通文本
- notify: 立即发送 / 无缓存丢弃
- _format_delay: 5 档粒度
- _build_session_key / _extract_session_key
- _get_kv_with_retry: 重试 helper
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

# Stub astrbot.core.message.message_event_result (runtime 不可用, 测试要绕过)
import types
_mock_astrbot = types.ModuleType("astrbot")
_mock_core = types.ModuleType("astrbot.core")
_mock_msg = types.ModuleType("astrbot.core.message")
_mock_msg_result = types.ModuleType("astrbot.core.message.message_event_result")

class _StubChain:
    """MessageChain stub: chain 属性是组件列表"""
    def __init__(self):
        self.chain = []
    def message(self, text):
        c = MagicMock()
        c.text = text
        self.chain.append(c)
        return self
    def url_image(self, url):
        c = MagicMock()
        c.url = url
        self.chain.append(c)
        return self
    def file_image(self, path):
        c = MagicMock()
        c.path = path
        self.chain.append(c)
        return self
    def append(self, comp):
        self.chain.append(comp)
        return self

_mock_msg_result.MessageChain = _StubChain
_sys_mods = _sys if False else __import__("sys")
_sys_mods.modules["astrbot"] = _mock_astrbot
_sys_mods.modules["astrbot.core"] = _mock_core
_sys_mods.modules["astrbot.core.message"] = _mock_msg
_sys_mods.modules["astrbot.core.message.message_event_result"] = _mock_msg_result

# 模块注入解决 dataclass 解析问题
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "astrbot_plugin_niumalife.src.ui.message_sender",
    PLUGIN_ROOT / "src" / "ui" / "message_sender.py",
)
_mod = importlib.util.module_from_spec(_spec)
_sys_mods.modules["astrbot_plugin_niumalife.src.ui.message_sender"] = _mod
_spec.loader.exec_module(_mod)

MessageSender = _mod.MessageSender
_format_delay = _mod._format_delay
_build_session_key = _mod._build_session_key
_extract_session_key = _mod._extract_session_key
_get_kv_with_retry = _mod._get_kv_with_retry


# ============================================================
# Stub Plugin
# ============================================================

class StubPlugin:
    """模拟 NiumaLife, 提供 _recent_events + get/put_kv_data + _renderer + _cache_event"""

    def __init__(self):
        self._recent_events = {}
        self._kv = {}
        self._renderer = MagicMock()
        self._cache_event = MagicMock(side_effect=self._real_cache_event)

    def _real_cache_event(self, event):
        """模拟真 main.py 的 _cache_event: 按 session_key 缓存 + 打时间戳"""
        import time
        try:
            sk = _extract_session_key(event)
            if not sk:
                return
            self._recent_events[sk] = event
            event._niuma_cached_at = time.time()
        except Exception:
            pass

    async def get_kv_data(self, key, default=None):
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value):
        self._kv[key] = value


def make_event(user_id="12345", session_type="GroupMessage", session_id="67890", platform_id="aiocqhttp"):
    """构造 fake event。"""
    import time as _t
    e = MagicMock()
    e.get_sender_id = MagicMock(return_value=user_id)
    e.get_group_id = MagicMock(return_value=session_id if session_type == "GroupMessage" else None)
    e.is_private_chat = MagicMock(return_value=(session_type == "PrivateMessage"))
    e.get_sender_name = MagicMock(return_value="TestPlayer")
    e.send = AsyncMock()
    e.image_result = MagicMock(side_effect=lambda u: f"image_result({u})")
    e.plain_result = MagicMock(side_effect=lambda t: f"plain_result({t})")
    e._platform_id = platform_id
    e._niuma_cached_at = _t.time()
    return e


def make_sender(plugin=None):
    plugin = plugin or StubPlugin()
    return MessageSender(plugin)


# ============================================================
# _format_delay 测试
# ============================================================

def test_format_delay_tiers():
    """5 档延迟粒度正确。"""
    assert _format_delay(60) == "数分钟"
    assert _format_delay(60 * 60) == "半小时"
    assert _format_delay(3 * 60 * 60) == "数小时"
    assert _format_delay(12 * 60 * 60) == "半天"
    assert _format_delay(48 * 60 * 60) == "太久"  # > 24h 实际不会到这里


# ============================================================
# session_key 测试
# ============================================================

def test_build_session_key():
    """构造 session_key。"""
    sk = _build_session_key("aiocqhttp", "GroupMessage", "group:abc")
    assert sk == "aiocqhttp|GroupMessage|group:abc"


def test_extract_session_key_group():
    """从群消息 event 提取 session_key。"""
    event = make_event(session_type="GroupMessage", session_id="abc")
    sk = _extract_session_key(event)
    assert sk == "aiocqhttp|GroupMessage|group:abc"


def test_extract_session_key_private():
    """从私聊 event 提取 session_key。"""
    event = make_event(session_type="PrivateMessage", session_id="abc")
    # PrivateMessage 路径: is_private_chat 返回 True → session_type="PrivateMessage"
    # session_id 用 sender_id (因为 is_private_chat 时 group_id 为 None)
    sk = _extract_session_key(event)
    # sender_id=12345, 走 PrivateMessage 路径, session_id = f"user:{user_id}" = "user:12345"
    assert sk == "aiocqhttp|PrivateMessage|user:12345"


# ============================================================
# send_card 测试
# ============================================================

def test_send_card_success():
    """send_card 渲染成功时调 event.image_result。"""
    async def run():
        plugin = StubPlugin()
        plugin._renderer._render = AsyncMock(return_value="file:///tmp/x.png")
        sender = make_sender(plugin)
        event = make_event()
        results = [r async for r in sender.send_card(event, "profile_card", {"name": "test"})]
        assert any("file://" in str(r) for r in results)
    asyncio.run(run())


def test_send_card_render_returns_empty():
    """send_card 渲染返回空 (网络/模板错误) → yield plain_result fallback。"""
    async def run():
        plugin = StubPlugin()
        plugin._renderer._render = AsyncMock(return_value="")
        sender = make_sender(plugin)
        event = make_event()
        results = [r async for r in sender.send_card(event, "profile_card", {"name": "test"}, fallback_text="fallback text")]
        assert any("fallback text" in str(r) for r in results)
    asyncio.run(run())


def test_send_card_render_raises():
    """send_card 渲染抛异常 → yield plain_result fallback。"""
    async def run():
        plugin = StubPlugin()
        plugin._renderer._render = AsyncMock(side_effect=RuntimeError("render failed"))
        sender = make_sender(plugin)
        event = make_event()
        results = [r async for r in sender.send_card(event, "profile_card", {"name": "test"}, fallback_text="render error fallback")]
        assert any("render error fallback" in str(r) for r in results)
    asyncio.run(run())


def test_send_card_caches_event():
    """send_card 自动缓存 event 给后续 notify 用。"""
    async def run():
        plugin = StubPlugin()
        plugin._renderer._render = AsyncMock(return_value="file:///tmp/x.png")
        sender = make_sender(plugin)
        event = make_event(session_type="GroupMessage", session_id="xyz")
        async for _ in sender.send_card(event, "profile_card", {}):
            pass
        plugin._cache_event.assert_called()
        sk = "aiocqhttp|GroupMessage|group:xyz"
        assert sk in plugin._recent_events
    asyncio.run(run())


# ============================================================
# send_text 测试
# ============================================================

def test_send_text_plain():
    """send_text 普通文本。"""
    async def run():
        plugin = StubPlugin()
        sender = make_sender(plugin)
        event = make_event()
        results = [r async for r in sender.send_text(event, "hello world")]
        assert any("hello world" in str(r) for r in results)
    asyncio.run(run())


def test_send_text_at_user():
    """send_text at_user 模式。"""
    async def run():
        plugin = StubPlugin()
        sender = make_sender(plugin)
        event = make_event()
        results = [r async for r in sender.send_text(event, "@user 你好", at_user="12345")]
        assert any("@user" in str(r) or "12345" in str(r) for r in results)
    asyncio.run(run())


# ============================================================
# notify 测试 (9/6 简化版)
# ============================================================

def test_notify_immediate_delivery():
    """有缓存 event → 直接调 event.send, 不读写 KV。"""
    async def run():
        plugin = StubPlugin()
        sender = make_sender(plugin)
        event = make_event()
        plugin._recent_events["aiocqhttp|GroupMessage|group:67890"] = event
        plugin._kv.clear()

        await sender.notify("12345", "low_attr", text="低饱食警告")

        event.send.assert_called_once()
        # 不应写 KV
        assert "_pending_notify:12345" not in plugin._kv
    asyncio.run(run())


def test_notify_no_event_persists():
    """9/6: 无缓存 event → 直接丢弃 (移除 KV 持久化)。"""
    async def run():
        plugin = StubPlugin()
        sender = make_sender(plugin)
        # 不缓存 event
        await sender.notify("12345", "low_attr", text="低饱食警告")
        # 不应写 KV
        assert "_pending_notify:12345" not in plugin._kv
        # event.send 不应被调用
        # (因为没有缓存 event)
    asyncio.run(run())


# ============================================================
# retry helper 测试
# ============================================================

async def test_retry_succeeds_after_transient_failure():
    """前2次失败, 第3次成功 - retry 应返回成功值."""
    _get_kv_with_retry  # 显式引用

    class StubPlugin:
        def __init__(self):
            self.calls = 0
        async def get_kv_data(self, key, default):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("simulated pool timeout")
            return "ok_value"

    plugin = StubPlugin()
    result = await _get_kv_with_retry(plugin, "key", "default")
    assert result == "ok_value"
    assert plugin.calls == 3


async def test_retry_raises_after_exhausted():
    """3次都失败 - retry 应 raise 最后一次异常."""
    _get_kv_with_retry  # 显式引用

    class StubPlugin:
        async def get_kv_data(self, key, default):
            raise TimeoutError(f"always fail: {key}")

    plugin = StubPlugin()
    try:
        await _get_kv_with_retry(plugin, "key", "default")
        assert False, "should have raised"
    except TimeoutError as e:
        assert "always fail" in str(e)


# ============================================================
# Runner
# ============================================================

if __name__ == "__main__":
    failures = 0
    tests = [
        # _format_delay
        test_format_delay_tiers,
        # session_key
        test_build_session_key,
        test_extract_session_key_group,
        test_extract_session_key_private,
        # send_card
        test_send_card_success,
        test_send_card_render_returns_empty,
        test_send_card_render_raises,
        test_send_card_caches_event,
        # send_text
        test_send_text_plain,
        test_send_text_at_user,
        # notify
        test_notify_immediate_delivery,
        test_notify_no_event_persists,
        # retry helper
        test_retry_succeeds_after_transient_failure,
        test_retry_raises_after_exhausted,
    ]
    for t in tests:
        try:
            if asyncio.iscoroutinefunction(t):
                asyncio.run(t())
            else:
                t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}\n      {e}")
            failures += 1
        except Exception as e:
            print(f"ERROR {t.__name__}\n      {type(e).__name__}: {e}")
            failures += 1
    if failures:
        raise SystemExit(1)
    print(f"\n{len(tests)} tests, 0 failures")