"""
背包命令逻辑
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent

from ...modules.item import ITEMS, RARITY_NAMES, RARITY_COLORS, rarity_hex as rarity_color
from ...modules.templates import CardType
from ..fishing.fishing_manager import format_weight  # 9/8: 紧凑重量格式
from ._helpers import parse_filter_tokens, apply_item_filter, format_filter_label


def _format_item_name(entry: dict, with_rarity: bool = True) -> str:
    """9/4晚: 物品名显示 - 含稀有度前缀 (普通不加)"""
    item_id = entry.get("id", "")
    name = entry.get("name") or ITEMS.get(item_id, {}).get("name", item_id)
    if not with_rarity:
        return name
    rarity = entry.get("rarity", "common")
    if rarity == "common":
        return name
    rarity_cn = RARITY_NAMES.get(rarity, rarity)
    return f"{rarity_cn}{name}"


def _format_inventory_text(user: dict, items: list, filter_label: str = "") -> str:
    """背包降级纯文本格式（渲染失败时用）。"""
    gold = int(user.get('gold', 0))
    title = " 🎒 {} 的背包".format(user.get('nickname', '玩家'))
    if filter_label:
        title += f" ({filter_label})"
    lines = [
        "═══════════════════════════",
        title,
        "═══════════════════════════",
    ]
    if not items:
        lines.append("（空）")
    for it in items:
        qty = it.get('quantity', 1)
        emoji = it.get('emoji', '📦')
        name = it.get('name', '???')
        if it.get('is_fish'):
            from ..fishing.fishing_manager import length_for_size_label, format_length, format_weight
            cm = it.get('length_cm')
            if cm is None and it.get('size_label'):
                cm = length_for_size_label(it['size_label'])
            length_str = format_length(cm) if cm is not None else ""
            weight_str = format_weight(it.get('weight', 0))
            lines.append(f"  {emoji} {name}  {weight_str} {length_str}")
        elif qty > 1:
            lines.append(f"  {emoji} {name}  x{qty}")
        else:
            lines.append(f"  {emoji} {name}")
    lines.append("═══════════════════════════")
    lines.append(f"💰 金币: {gold}")
    return "\n".join(lines)


async def run_backpack_logic(event: AstrMessageEvent, store, parser=None, sender=None):
    """背包命令逻辑 — 显示用户的物品和鱼.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    sender 内部已经统一捕获 render 失败, 降级到 fallback_text。

    9/7: 新增 `/背包 <物品名>` — 显示单个物品的详情卡片。
    Args:
        parser: 可选。传入则解析 `背包 [类别] [尺寸/稀有度]` 筛选参数。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    # 解析筛选参数
    filt = {"category": None, "min_size_idx": None, "max_rarity": None}
    args = []
    if parser is not None:
        try:
            _, args = parser.parse(event)
            # 9/7: 优先尝试物品名查询 — 整段 args 拼起来匹配
            # 找到了直接走详情卡片, 不走 filter
            if args:
                from .item_detail import _resolve_item, build_item_detail_view, get_fallback_text
                query = " ".join(args).strip()
                if query:
                    result = _resolve_item(query, user)
                    if result is not None:
                        data = build_item_detail_view(user, result)
                        async for r in sender.send_card(
                            event, CardType.ITEM_DETAIL, data,
                            fallback_text=get_fallback_text(data),
                        ):
                            yield r
                        return
                    # 没找到 → 降级到 filter (让 filter error 给提示)

            filt = parse_filter_tokens(args)
            if filt.get("error"):
                yield event.plain_result(
                    f"❓ 未识别的筛选条件: {', '.join(filt['error'])}\n"
                    f"💡 类别: 鱼 / 食物 / 物品\n"
                    f"💡 尺寸: 小 / 大 / 巨 / 传说\n"
                    f"💡 稀有度: 常见 / 不凡 / 稀有 / 史诗 / 传奇"
                )
                return
        except Exception as e:

            import logging as __l

            __l.getLogger(__name__).debug(f"[backpack] {type(e).__name__}: {e}")
            pass  # parser 异常时回退到无筛选

    inventory = user.get("inventory", [])
    # 先按筛选过滤原始 items，再做 UI 适配（堆叠合并）
    from ..fishing.fishing_manager import FISHES, _ensure_loaded
    _ensure_loaded()
    inventory = apply_item_filter(inventory, filt, FISHES)

    items = []
    if inventory:
        for item in inventory:
            item_type = item.get("type", "")
            item_id = item.get("id", item.get("name", "未知"))

            # 鱼走专门格式
            if item_type == "fish":
                # 9/6: 取鱼 rarity 渲染边框/文字颜色
                fish_def = item.get("_fish_def") or FISHES.get(item.get("name", ""))
                rarity = (fish_def or {}).get("rarity", "common")
                weight_raw = item.get("weight", 0)
                items.append({
                    "name": item.get("name", item_id),
                    "emoji": "🐟",
                    "quantity": 1,
                    "is_fish": True,
                    "weight": weight_raw,
                    "weight_str": format_weight(weight_raw),  # 9/8: 紧凑格式
                    "size_label": item.get("size_label", ""),
                    "length_cm": item.get("length_cm"),
                    "rarity": rarity,
                    "rarity_color": rarity_color(rarity),
                })
                continue

            # 普通物品：堆叠合并
            existing = next(
                (it for it in items if it.get("id") == item_id and not it.get("is_fish")),
                None,
            )
            if existing:
                existing["quantity"] = existing.get("quantity", 1) + 1
                continue

            name = _format_item_name(item)
            qty = item.get("quantity", 1)
            item_info = ITEMS.get(item_id, {})
            emoji = item_info.get("emoji", "📦")
            # 9/6 修正: 优先用 inventory entry 自身的 rarity (附魔后已变)
            # fallback 到 ITEMS 字典 (未附魔的原始稀有度)
            rarity = item.get("rarity") or item_info.get("rarity", "common")

            items.append({
                "id": item_id,
                "name": name,
                "emoji": emoji,
                "quantity": qty,
                "is_fish": False,
                "rarity": rarity,
                "rarity_color": rarity_color(rarity),
            })

    filter_label = format_filter_label(filt)
    if not items and filter_label:
        yield event.plain_result(
            f"🎒 没有匹配的物品 ({filter_label})\n"
            f"💡 试试不带筛选的 /背包"
        )
        return

    # 9/7: 钓鱼状态显示 (背包顶部)
    is_fishing = bool(user.get("is_fishing", False))
    fishing_spot = user.get("fishing_spot_name", "")
    if is_fishing and not fishing_spot:
        # 兜底: 用 spot_id 反查名字
        from ..fishing.fishing_manager import get_spot
        spot_id = user.get("current_spot_id", "")
        spot_def = get_spot(spot_id) or {}
        fishing_spot = spot_def.get("name", spot_id or "未知水域")

    # 9/6: 改用 sender.send_card() (CardType.BACKPACK 渲染模板)
    data = {
        "user_id": user_id,
        "items": items,
        "nickname": user.get("nickname", "玩家"),
        "gold": int(user.get("gold", 0)),
        "filter_label": filter_label,
        "total_count": len(items),
        "is_fishing": is_fishing,
        "fishing_spot": fishing_spot,
    }
    async for r in sender.send_card(
        event, CardType.BACKPACK, data,
        fallback_text=_format_inventory_text(user, items, filter_label),
    ):
        yield r