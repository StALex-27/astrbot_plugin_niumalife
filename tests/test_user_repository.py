"""测试 user_repository 的 9/6 retry 行为。"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# 模拟 AstrBot runtime 命名空间: data.plugins.astrbot_plugin_niumalife
# 这样相对导入 `from ...modules.constants` 才能解析
def _install_pkg():
    # 顶层 "data" 包
    if "data" not in sys.modules:
        sys.modules["data"] = types.ModuleType("data")
        sys.modules["data"].__path__ = []  # type: ignore[attr-defined]
    if "data.plugins" not in sys.modules:
        sys.modules["data.plugins"] = types.ModuleType("data.plugins")
        sys.modules["data.plugins"].__path__ = []  # type: ignore[attr-defined]
    pkg_name = "data.plugins.astrbot_plugin_niumalife"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg


_install_pkg()

# 加载 modules.constants (user_repository 的依赖)
_spec = importlib.util.spec_from_file_location(
    "data.plugins.astrbot_plugin_niumalife.modules.constants",
    PLUGIN_ROOT / "modules" / "constants.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["data.plugins.astrbot_plugin_niumalife.modules.constants"] = _mod
_spec.loader.exec_module(_mod)

_spec = importlib.util.spec_from_file_location(
    "data.plugins.astrbot_plugin_niumalife.modules.user",
    PLUGIN_ROOT / "modules" / "user.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["data.plugins.astrbot_plugin_niumalife.modules.user"] = _mod
_spec.loader.exec_module(_mod)

# 加载被测模块
_spec = importlib.util.spec_from_file_location(
    "data.plugins.astrbot_plugin_niumalife.src.data.user_repository",
    PLUGIN_ROOT / "src" / "data" / "user_repository.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["data.plugins.astrbot_plugin_niumalife.src.data.user_repository"] = _mod
_spec.loader.exec_module(_mod)

_put_kv_with_retry = _mod._put_kv_with_retry
KV_RETRY_ATTEMPTS = _mod._KV_RETRY_ATTEMPTS


# ============================================================
# Stub Plugin
# ============================================================

class _FlakyPlugin:
    def __init__(self, fail_count):
        self.fail_count = fail_count
        self.calls = 0

    async def put_kv_data(self, key, value):
        self.calls += 1
        if self.calls <= self.fail_count:
            raise TimeoutError("simulated pool timeout")
        return None


class _AlwaysFailPlugin:
    async def put_kv_data(self, key, value):
        raise TimeoutError(f"always fail: {key}")


# ============================================================
# Tests
# ============================================================

async def test_retry_succeeds_after_transient_failure():
    """前2次失败, 第3次成功 - retry 应返回成功值."""
    plugin = _FlakyPlugin(fail_count=2)
    await _put_kv_with_retry(plugin, "key", {"a": 1})
    assert plugin.calls == 3, f"expected 3 attempts, got {plugin.calls}"


async def test_retry_raises_after_exhausted():
    """3次都失败 - retry 应 raise 最后一次异常."""
    plugin = _AlwaysFailPlugin()
    try:
        await _put_kv_with_retry(plugin, "key", {"a": 1})
        assert False, "should have raised"
    except TimeoutError as e:
        assert "always fail" in str(e)


def test_retry_attempts_constant():
    """验证默认 retry 次数是 3."""
    assert KV_RETRY_ATTEMPTS == 3, f"expected 3, got {KV_RETRY_ATTEMPTS}"


# ============================================================
# Runner
# ============================================================

if __name__ == "__main__":
    failures = 0
    tests = [
        test_retry_succeeds_after_transient_failure,
        test_retry_raises_after_exhausted,
        test_retry_attempts_constant,
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