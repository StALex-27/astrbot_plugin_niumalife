"""命令层共享辅助函数。"""
from typing import Optional


# ============================================================
# 物品筛选器（背包 / 卖鱼 菜单共用）
# ============================================================

# 类别 token → inventory item.type
_CATEGORY_ALIASES = {
    "鱼": "fish", "fish": "fish",
    "食物": "food", "food": "food", "吃的": "food",
    "物品": "item", "道具": "item", "item": "item", "装备": "item",
    "全部": None, "all": None, "全": None,
}

# 尺寸 token → size_label_index 最小阈值（仅物理尺寸词，避免与稀有度冲突）
_SIZE_ALIASES = {
    "小": 0, "普通": 0,
    "大": 1, "大鱼": 1,
    "巨": 2, "巨大": 2,
    "神话": 4, "神": 4, "max": 99,
}

# 稀有度 token → 最小阈值（稀有度按 common/uncommon/rare/epic/legendary 排序）
_RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]
_RARITY_THRESHOLDS = {
    "常见": 0, "普通": 0, "common": 0,
    "不凡": 1, "uncommon": 1,
    "稀有": 2, "rare": 2,
    "史诗": 3, "epic": 3,
    "传奇": 4, "legendary": 4, "传说": 4,
}

# 9/6: 颜色 / 中文标签 utility
# 注意: 真正的 hex 颜色定义在 modules.item.RARITY_HEX_COLORS (共享来源)
# 这里只做 import 转发, 避免重复定义
try:
    from modules.item import rarity_hex as rarity_color  # noqa: E402
except ImportError:
    # 9/6: fallback — test_sell_filter.py 直接 import 单模块时无 modules 包
    _RARITY_HEX = {
        "common": "#9e9e9e", "uncommon": "#7bed9f", "rare": "#4fc3f7",
        "epic": "#c586c0", "legendary": "#ffa726", "mythic": "#ff6b6b",
    }
    def rarity_color(rarity):  # type: ignore[no-redef]
        return _RARITY_HEX.get(rarity or "common", "#9e9e9e")


def parse_filter_tokens(tokens: list[str]) -> dict:
    """解析 `背包/卖鱼 菜单` 的筛选 token 列表。

    支持 token 顺序无关。返回:
      {
        'category': str | None,    # 'fish' / 'food' / 'item' / None
        'min_size_idx': int | None,  # size_label_index 最小值 (含)
        'max_rarity': int | None,   # _RARITY_ORDER 索引最大值 (含)
                                     # 9/6: 改 min_rarity 为 max_rarity — "稀有" 意为 "≤稀有" (包含语义)
                                     # 例: /卖 鱼 稀有 → 卖常见+不凡+稀有的鱼 (不要史诗/传奇)
      }
    未识别 token 返回 error 字段。
    """
    out: dict = {"category": None, "min_size_idx": None, "max_rarity": None}
    errors: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        low = tok.lower()
        # 类别
        if tok in _CATEGORY_ALIASES or low in _CATEGORY_ALIASES:
            out["category"] = _CATEGORY_ALIASES.get(tok) or _CATEGORY_ALIASES.get(low)
            continue
        # 尺寸
        if tok in _SIZE_ALIASES or low in _SIZE_ALIASES:
            out["min_size_idx"] = _SIZE_ALIASES.get(tok, _SIZE_ALIASES.get(low, 0))
            continue
        # 稀有度 (9/6: 改 ≤max 语义)
        if tok in _RARITY_THRESHOLDS or low in _RARITY_THRESHOLDS:
            out["max_rarity"] = _RARITY_THRESHOLDS.get(tok, _RARITY_THRESHOLDS.get(low, 0))
            continue
        errors.append(tok)
    if errors:
        out["error"] = errors
    return out


def _item_rarity(item: dict, fish_defs: dict) -> int:
    """返回物品的稀有度索引 (0-4)。鱼查 FISHES；其他固定 common (0)。"""
    if item.get("type") == "fish":
        # 懒加载: 优先用 catch 写进 item 的 fish_def (有些路径会塞), 否则查 FISHES
        fish_def = item.get("_fish_def")
        if not fish_def and fish_defs:
            fish_def = fish_defs.get(item.get("name") or item.get("id"))
        if fish_def:
            r = fish_def.get("rarity", "common")
            return _RARITY_ORDER.index(r) if r in _RARITY_ORDER else 0
    return 0


def _item_size_idx(item: dict, fish_defs: dict) -> int:
    """返回鱼 size_label 索引 (0-based)。非鱼返回 0。"""
    if item.get("type") != "fish":
        return 0
    fish_def = item.get("_fish_def")
    if not fish_def and fish_defs:
        fish_def = fish_defs.get(item.get("name") or item.get("id"))
    if not fish_def:
        return 0
    labels = fish_def.get("size_labels", [])
    label = item.get("size_label", "")
    try:
        return labels.index(label)
    except ValueError:
        return 0


def apply_item_filter(items: list[dict], filt: dict, fish_defs: dict = None) -> list[dict]:
    """按 filt 过滤 inventory 原始 item 列表。

    Args:
        items: inventory 原始 item dict 列表（type='fish'/'food'/'item'）
        filt: parse_filter_tokens 输出
        fish_defs: FISHES 字典（用于查 rarity/size_labels），可为 None
    """
    if not filt or (filt.get("category") is None and filt.get("min_size_idx") is None and filt.get("max_rarity") is None):
        return items
    cat = filt.get("category")
    min_size = filt.get("min_size_idx")
    max_rar = filt.get("max_rarity")
    out = []
    # 9/7: 装备类 (无 type 字段, 但有 id 可查 ITEMS) 需要 fallback
    from ...modules.item import ITEMS as _ITEMS_FILTER  # 查装备 category
    for it in items:
        if cat is not None:
            it_type = it.get("type") or _ITEMS_FILTER.get(it.get("id", ""), {}).get("category", "")
            if it_type != cat:
                continue
        if min_size is not None and _item_size_idx(it, fish_defs) < min_size:
            continue
        # 9/6: max_rarity (≤包含语义) — 保留 ≤max_rarity 的鱼
        if max_rar is not None and _item_rarity(it, fish_defs) > max_rar:
            continue
        out.append(it)
    return out


def format_filter_label(filt: dict) -> str:
    """把 filt 翻译成简短中文标签，用于卡片标题/页脚。"""
    parts = []
    cat = filt.get("category")
    if cat == "fish":
        parts.append("🐟 鱼")
    elif cat == "food":
        parts.append("🍖 食物")
    elif cat == "item":
        parts.append("🎒 物品")
    min_size = filt.get("min_size_idx")
    if min_size is not None:
        size_label = {0: "小", 1: "大", 2: "巨", 3: "传说", 4: "神话"}.get(min_size, f"≥L{min_size}")
        parts.append(f"📏 {size_label}起")
    max_rar = filt.get("max_rarity")
    if max_rar is not None:
        rar_label = {0: "常见", 1: "不凡", 2: "稀有", 3: "史诗", 4: "传奇"}[max_rar]
        # 9/6: ≤max 语义 — 显示 "≤稀有" 比 "稀有起" 更清晰
        parts.append(f"⭐ ≤{rar_label}")
    return " · ".join(parts) if parts else ""


# ============================================================
# 保留售出 (sell.py 用)
# ============================================================

# 保留 token: 留大/留小 [数量]
_KEEP_ALIASES = {
    "留大": "largest", "留最大": "largest", "留巨": "largest", "保留大": "largest", "剩大": "largest",
    "留小": "smallest", "留最小": "smallest", "保留小": "smallest", "剩小": "smallest",
}


def parse_keep_token(tokens: list) -> dict:
    """从 args 里抽出保留 token 和数量。

    Returns:
        {
            'keep': dict | None,  # {'mode': 'largest'|'smallest', 'count': int}
            'remaining_args': list,  # 抽完保留 token 后的剩余 args
        }
    """
    remaining = list(tokens)
    out = {"keep": None, "remaining_args": remaining}
    i = 0
    while i < len(remaining):
        tok = remaining[i]
        if tok in _KEEP_ALIASES:
            mode = _KEEP_ALIASES[tok]
            count = 1
            # 紧跟数字则取之
            if i + 1 < len(remaining) and remaining[i + 1].isdigit():
                count = int(remaining[i + 1])
                remaining.pop(i + 1)
            out["keep"] = {"mode": mode, "count": max(1, count)}
            remaining.pop(i)
            return out
        i += 1
    return out


def apply_keep(items: list, keep_spec: dict) -> tuple[list, list]:
    """按 weight 排序，留 keep_spec 指定的 N 条，返回 (要卖的, 要留的)。"""
    if not keep_spec:
        return items, []
    n = keep_spec["count"]
    if keep_spec["mode"] == "largest":
        items_sorted = sorted(items, key=lambda x: x.get("weight", 0), reverse=True)
    else:
        items_sorted = sorted(items, key=lambda x: x.get("weight", 0))
    keep = items_sorted[:n]
    sell = items_sorted[n:]
    return sell, keep


async def safe_yield_image(event, url: str, fallback_text: Optional[str] = None):
    """发图片但 url 为空时降级纯文本。

    重要: url="" 传给 event.image_result() 会让 AstrBot 把它当本地路径
    "/home/alex" 尝试打开, 触发 "[Errno 21] Is a directory"。

    Args:
        event: AstrMessageEvent
        url: 渲染返回的 url (可能是 "")
        fallback_text: 降级文本; 为 None 时不发任何东西
    """
    if url:
        yield event.image_result(url)
    elif fallback_text is not None:
        yield event.plain_result(fallback_text)
