"""
MessageDispatcher - 统一管理卡片渲染 + 缓存 + 消息发送。

设计目标:
1. 统一 url="" 降级逻辑, 命令层不用再 if/else
2. 持久化缓存 (写到本地 JSON), AstrBot 重启后不丢失
3. 统一日志格式, 排查问题一处查
4. 缓存 key 跨用户复用 (不含 avatar/user_id)
5. 命中率统计

用法:
    dispatcher = MessageDispatcher(plugin)

    async for msg in dispatcher.send_card(
        event, CardType.SHOP, data,
        fallback_text="🏪 商店渲染失败, 请重试"
    ):
        yield msg
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, AsyncGenerator

from ...modules.templates import get_card_template, CardType

# 懒加载 (plugins 目录外测试时不报 ImportError)
_html_renderer = None


def _get_html_renderer():
    global _html_renderer
    if _html_renderer is None:
        from astrbot.core import html_renderer
        _html_renderer = html_renderer
    return _html_renderer


# === 本地 Chromium (绕过 AstrBot 网络层) ===
_CHROME_PATH = "/home/alex/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome"
_LOCAL_RENDER_TIMEOUT = 10.0

# 各卡片类型的推荐渲染高度 (full_page 模式用)
# 实际高度由 PIL 二次裁剪, 这里只是给 chrome 一个初始高度避免空白 3000px
_CARD_HEIGHTS = {
    "profile": 700,
    "backpack": 1200,
    "shop": 1200,
    "fishing_card": 700,
    "status": 600,
    "checkin": 700,
    "food_list": 800,
    "residence": 700,
    "my_jobs": 700,
    "course_list": 700,
    "fish_dex": 1200,
    "job_list": 900,
    "job_pool": 700,
    "job_complete": 800,
    "course_start": 600,
    "job_start": 600,
    "food": 600,
    "buff_list": 700,
    "entertainment_list": 700,
    "housing_list": 700,
    "daily_report": 800,
    "my_stats": 700,
    "stock_market": 1000,
    "stock_holdings": 800,
    "help": 800,
    "error": 500,
    "success": 500,
    "generic": 500,
}


class LocalRenderer:
    """本地 Chromium 直接渲染 HTML -> PNG (调 Chrome DevTools Protocol 命令行模式)。

    比 AstrBot 内置 html_renderer 快 10-20 倍 (0.4s vs 7-12s)。
    不依赖 playwright Python 包, 只用系统 chrome 二进制 + Jinja2。
    """

    def __init__(self, chrome_path: str = _CHROME_PATH):
        self.chrome_path = chrome_path
        # Playwright 自带 Chromium, 不需要外部 chrome 路径
        self._enabled = True

    async def render(self, tmpl_str: str, tmpl_data: dict,
                     width: int = 380, height: int = 500,
                     full_page: bool = False, card_type: str = None) -> str:
        """渲染 Jinja2 模板 -> PNG, 返回本地文件路径 (Playwright 全页截图)。

        Args:
            tmpl_str: Jinja2 模板字符串
            tmpl_data: 模板数据
            width/height: 视口大小 (full_page 时 height 用于初始化)
            full_page: True = 截整页 (用 page.evaluate 拿 scrollHeight)
            card_type: 卡片类型, 仅用于日志

        Returns:
            PNG 文件路径 (失败返 "")
        """
        if not self._enabled:
            return ""

        # 1. 渲染 Jinja2 模板 -> HTML 字符串
        try:
            from jinja2 import Environment, select_autoescape
            env = Environment(autoescape=select_autoescape(["html", "xml"]))
            tmpl = env.from_string(tmpl_str)
            html = tmpl.render(**tmpl_data)
        except Exception as e:
            _log.warning(f"[LocalRenderer] Jinja2 模板渲染失败: {type(e).__name__}: {e}")
            return ""

        # 3. Playwright 渲染 + 截图
        png_path = ""
        html_path = ""
        try:
            from playwright.async_api import async_playwright
            import tempfile as _tf
            with _tf.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
                f.write(html)
                html_path = f.name
            png_path = html_path.replace(".html", ".png")
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                )
                try:
                    # 步骤 1: 用大 viewport 让内容自由展开
                    initial_height = max(height, 3000) if full_page else height
                    context = await browser.new_context(
                        viewport={"width": width, "height": initial_height},
                        device_scale_factor=2,
                    )
                    page = await context.new_page()
                    await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle", timeout=5000)
                    # 调试: 报告真实高度
                    body_h = await page.evaluate("document.body.scrollHeight")
                    doc_h = await page.evaluate("document.documentElement.scrollHeight")
                    _log.warning(
                        f"[LocalRenderer] 渲染 {card_type}: body={body_h}px html={doc_h}px "
                        f"viewport={height}px -> {png_path}"
                    )

                    if full_page:
                        # 步骤 2: 重设 viewport 为内容实际高度 (避免 body 被 viewport 撑高)
                        actual_h = max(body_h, 200)
                        await page.set_viewport_size({"width": width, "height": actual_h})
                        # 重新计算 body 高度 (新 viewport 后)
                        body_h2 = await page.evaluate("document.body.scrollHeight")
                        doc_h2 = await page.evaluate("document.documentElement.scrollHeight")
                        _log.warning(
                            f"[LocalRenderer]   resize 后: body={body_h2}px html={doc_h2}px"
                        )

                    await page.screenshot(path=png_path, full_page=full_page, type="png")
                finally:
                    await browser.close()
        except Exception as e:
            _log.warning(f"[LocalRenderer] Playwright 渲染失败: {type(e).__name__}: {e}")
            if png_path:
                Path(png_path).unlink(missing_ok=True)
            return ""
        finally:
            # 清理临时 HTML
            if html_path:
                try:
                    Path(html_path).unlink(missing_ok=True)
                except Exception as e:

                    import logging as __l

                    __l.getLogger(__name__).warning(f"[render] {type(e).__name__}: {e}")
                    pass

        if not Path(png_path).exists():
            _log.warning(f"[LocalRenderer] Playwright 截图未生成: {png_path}")
            return ""

        _log.debug(f"[LocalRenderer] 渲染成功 ({card_type or 'unknown'}): {png_path}")
        return png_path


# === 配置 ===
_RENDER_TIMEOUT = 12.0  # 渲染超时 (秒)
_CACHE_TTL = 600  # 缓存 10 分钟 (原来是 5 分钟, 延长)
_CACHE_MAX = 512  # 缓存项数上限 (原来是 256, 翻倍)
_CACHE_FILE = Path("/home/alex/data/niumalife_cache/render_cache.json")

# 缓存 key 排除字段 (每个用户不同, 不应作为 key)
_KEY_EXCLUDE = {"avatar_url", "user_id_short", "nickname"}

_log = logging.getLogger(__name__)


class RenderCache:
    """持久化渲染缓存 (进程内 LRU + 磁盘 JSON)。"""

    def __init__(self, cache_file: Path = _CACHE_FILE, ttl: int = _CACHE_TTL, max_size: int = _CACHE_MAX):
        self._file = cache_file
        self._ttl = ttl
        self._max = max_size
        self._mem: dict = {}
        self._hits = 0
        self._misses = 0
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                now = time.time()
                # 加载时过滤掉过期项
                for k, v in raw.items():
                    if isinstance(v, dict) and v.get("expire_at", 0) > now:
                        self._mem[k] = v
                _log.info(f"[Dispatcher] 缓存加载: {len(self._mem)} 项 (来自 {self._file})")
            except Exception as e:
                _log.warning(f"[Dispatcher] 缓存加载失败, 重置: {e}")
                self._mem = {}

    def _persist(self):
        """持久化到磁盘 (异步写时不阻塞主流程)。"""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._mem, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._file)
        except Exception as e:
            _log.warning(f"[Dispatcher] 缓存写入失败: {e}")

    def get(self, key: str) -> Optional[str]:
        self._load()
        item = self._mem.get(key)
        if not item:
            return None
        if item.get("expire_at", 0) < time.time():
            self._mem.pop(key, None)
            return None
        self._hits += 1
        return item.get("url", "")

    def put(self, key: str, url: str):
        if not url:
            return
        if len(self._mem) >= self._max:
            # 简化 LRU: 清掉 20% 最旧的
            items = sorted(self._mem.items(), key=lambda x: x[1].get("expire_at", 0))
            for k, _ in items[:int(self._max * 0.2)]:
                self._mem.pop(k, None)
        self._mem[key] = {
            "url": url,
            "expire_at": time.time() + self._ttl,
            "ct": int(time.time()),
        }
        self._misses += 1
        # 写入磁盘 (节流: 每 30s 最多一次)
        if not hasattr(self, "_last_persist"):
            self._last_persist = 0
        if time.time() - self._last_persist > 30:
            self._last_persist = time.time()
            self._persist()

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._mem),
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total else "n/a",
        }

    def clear(self, card_type: Optional[str] = None):
        if card_type is None:
            self._mem.clear()
        else:
            prefix = f"{card_type}:"
            self._mem = {k: v for k, v in self._mem.items() if not k.startswith(prefix)}
        self._persist()


class MessageDispatcher:
    """统一渲染 + 缓存 + 发送管理器。"""

    def __init__(self, plugin=None):
        self.plugin = plugin
        self._cache = RenderCache()
        # 本地 Chromium 渲染 (绕过 AstrBot 网络层, 0.4s vs 7-12s)
        self._local = LocalRenderer()
        # 兼容旧 _render 接口的常量
        self.DEFAULT_WIDTH = 380
        self.DEFAULT_HEIGHT = 500
        self.MAX_HEIGHT = 800

    @property
    def local_renderer_enabled(self) -> bool:
        """本地 Chromium 是否可用。"""
        return self._local._enabled

    # === 渲染 ===
    async def _do_render(self, card_type: str, data: dict, height: int = None, full_page: bool = False) -> str:
        """渲染: 优先本地 Chromium, 失败 fallback 远程 AstrBot API."""
        template = get_card_template(card_type)
        if not template:
            template = get_card_template(CardType.GENERIC)
        render_height = height or self.DEFAULT_HEIGHT

        # === 优先: 本地 Chromium ===
        if self._local._enabled:
            try:
                path = await self._local.render(
                    template, data,
                    width=self.DEFAULT_WIDTH, height=render_height,
                    full_page=full_page, card_type=card_type,
                )
                if path:
                    # 直接返回本地路径 - AstrBot Image.fromFileSystem() 处理
                    return path
            except Exception as e:
                _log.warning(f"[Dispatcher] 本地渲染失败, 切远程: {type(e).__name__}: {e}")

        # === Fallback: AstrBot 网络层 ===
        renderer = _get_html_renderer()
        try:
            url = await asyncio.wait_for(
                renderer.render_custom_template(
                    template, data, return_url=True,
                    options={
                        "type": "png", "quality": None,
                        "full_page": full_page,
                        "clip": {"x": 0, "y": 0, "width": self.DEFAULT_WIDTH, "height": render_height},
                        "scale": "device", "device_scale_factor_level": "ultra",
                    }
                ),
                timeout=_RENDER_TIMEOUT,
            )
            return url or ""
        except asyncio.TimeoutError:
            _log.warning(f"[Dispatcher] {card_type} 渲染超时 (>{_RENDER_TIMEOUT}s)")
            return ""
        except Exception as e:
            _log.warning(f"[Dispatcher] {card_type} 渲染异常: {type(e).__name__}: {e}")
            return ""

    @staticmethod
    def _file_to_data_url(path: str) -> str:
        """本地 PNG 文件转 base64 data URL, 供 event.image_result() 使用."""
        import base64
        try:
            data = Path(path).read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception as e:
            _log.warning(f"[Dispatcher] base64 转换失败: {e}")
            return ""

    @staticmethod
    def cache_key(card_type: str, data: dict) -> str:
        """根据 card_type + 稳定字段生成缓存 key。"""
        cacheable = {k: v for k, v in data.items() if k not in _KEY_EXCLUDE}
        try:
            payload = json.dumps(cacheable, sort_keys=True, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            payload = repr(cacheable)
        return hashlib.md5(f"{card_type}:{payload}".encode("utf-8")).hexdigest()

    async def render_card(self, card_type: str, data: dict, height: int = None,
                          full_page: bool = False) -> str:
        """渲染卡片, 自动走缓存。"""
        key = self.cache_key(card_type, data)
        cached = self._cache.get(key)
        if cached:
            _log.debug(f"[Dispatcher] cache HIT {card_type}")
            return cached

        _log.debug(f"[Dispatcher] cache MISS {card_type}, rendering...")
        url = await self._do_render(card_type, data, height, full_page)
        if url:
            self._cache.put(key, url)
        return url

    # === 发送 ===
    async def send_card(self, event, card_type: str, data: dict,
                        height: int = None, full_page: bool = False,
                        fallback_text: Optional[str] = None) -> AsyncGenerator:
        """渲染 + 发送卡片 (async generator)。url 为空时降级纯文本。

        Args:
            event: AstrMessageEvent
            card_type: CardType.xxx
            data: 渲染数据 dict
            height: 渲染高度 (full_page=False 时使用)
            full_page: 是否让 html_renderer 自适应高度
            fallback_text: 渲染失败时的降级文本。None = 不发文本

        Yields:
            event.image_result(url) 或 event.plain_result(text)
        """
        url = await self.render_card(card_type, data, height, full_page)
        if url.startswith("data:image/"):
            # 本地渲染的 PNG, 用 chain_result 避免 AstrBot 当文件路径处理
            from astrbot.core.message.components import Image
            b64 = url.split(",", 1)[1]
            yield event.chain_result([Image.fromBase64(b64)])
        elif url:
            yield event.image_result(url)
        elif fallback_text is not None:
            _log.info(f"[Dispatcher] {card_type} 降级为纯文本 (user={event.get_sender_id()})")
            yield event.plain_result(fallback_text)
        else:
            _log.warning(f"[Dispatcher] {card_type} 渲染失败且无 fallback (user={event.get_sender_id()})")

    async def send_image_or_text(self, event, url: str, fallback_text: Optional[str] = None) -> AsyncGenerator:
        """不发渲染 (url 已知), 仅做安全发送 + 降级。

        给已有 url 的命令用 (如 tick 通知已经渲染过, 复用 url)。
        支持 data: URL (本地 Chromium 渲染) - 自动转 base64 chain_result。
        """
        if url.startswith("data:image/"):
            # 本地渲染的 PNG, 用 chain_result 避免 AstrBot 当文件路径处理
            from astrbot.core.message.components import Image
            b64 = url.split(",", 1)[1]
            yield event.chain_result([Image.fromBase64(b64)])
        elif url:
            yield event.image_result(url)
        elif fallback_text is not None:
            yield event.plain_result(fallback_text)

    # === 缓存管理 ===
    def cache_stats(self) -> dict:
        return self._cache.stats()

    def invalidate_cache(self, card_type: Optional[str] = None):
        """手动清缓存。card_type=None 清全部。"""
        self._cache.clear(card_type)


# 全局单例 (每个 plugin 持有自己的实例)
_dispatcher: Optional[MessageDispatcher] = None


def get_dispatcher(plugin=None) -> MessageDispatcher:
    """获取 MessageDispatcher 单例。"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MessageDispatcher(plugin)
    return _dispatcher


 
 
 
 
 
