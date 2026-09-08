"""
通用卖命令

支持格式:
    /卖                - **显示可售清单** (默认安全模式, 不执行)
    /卖 草鱼           - 卖指定名字的所有物品
    /卖 草鱼 3         - 卖 3 条
    /卖 草鱼 大        - 卖最大那条 (仅鱼)
    /卖 草鱼 小        - 卖最小那条 (仅鱼)
    /卖 蚯蚓           - 卖非鱼物品 (按库存量卖)
    /卖 蚯蚓 5         - 卖 5 条
    /卖 全部           - **显式确认后** 卖背包所有可卖物
    /卖 鱼 [大/巨/传说/稀有/史诗/传奇] - 卖所有匹配的鱼 (筛选卖, 直接执行)
    /卖 食物 [稀有/史诗/传奇]         - 卖所有匹配的食物
    /卖 物品 [...]                    - 卖所有匹配的物品

未来扩展: 通过 market.json 配置新物品类别即可, 卡片/逻辑自动适配
"""
from typing import Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.templates import get_card_template, CardType
from ...modules.item import ITEMS, RARITY_NAMES, rarity_hex as rarity_color  # 9/6: rarity 染色
from ..fishing.fishing_manager import format_weight  # 9/8: 紧凑重量格式
from ..market import (
    sell_items, sell_all_sellable, can_sell,
    calc_sell_price, _list_inventory_by_name, _remove_from_inventory,
    list_sellable_inventory, list_stock_holdings, list_other_assets,
    sell_fish_items, sell_generic_items,
)
from ._helpers import (
    parse_filter_tokens, apply_item_filter, format_filter_label, _item_rarity,
    parse_keep_token, apply_keep,
)


async def _run_sell_with_filter(event, user, store, sender, args: list, keep_spec: dict = None):
    """/卖 <类别> [尺寸/稀有度]... [留大/留小 [N]] — 筛选卖，可叠加保留。

    注: keep_spec 已在 run_sell_logic 入口抽过, 此函数直接使用.

    例:
      /卖 鱼 大                    - 卖所有"大起"的鱼
      /卖 鱼 留大                   - 卖所有鱼，留最大1条
      /卖 鱼 大 留大 1              - 大鱼中留1条最大，其余卖
      /卖 鱼 稀有 留大 2            - 稀有度≥稀有的鱼中留2条最大
    """
    user_id = str(event.get_sender_id())
    filt = parse_filter_tokens(args)
    if filt.get("error"):
        yield event.plain_result(
            f"❓ 未识别的筛选条件: {', '.join(filt['error'])}\n"
            f"💡 类别: 鱼 / 食物 / 物品\n"
            f"💡 尺寸: 小 / 大 / 巨\n"
            f"💡 稀有度 (≤含端): 常见 / 不凡 / 稀有 / 史诗 / 传奇 / 传说\n"
            f"   例: /卖 鱼 稀有 = 卖常见+不凡+稀有的鱼\n"
            f"💡 保留: 留大/留小 [数量]"
        )
        return
    if filt.get("category") is None:
        yield event.plain_result("❌ 缺少类别 (鱼/食物/物品)")
        return

    from ..fishing.fishing_manager import FISHES, _ensure_loaded
    _ensure_loaded()

    inv = user.get("inventory", [])
    matched = apply_item_filter(inv, filt, FISHES)
    matched = [it for it in matched if it.get("name") and can_sell(it["name"])]

    # 保留逻辑 — 只对鱼生效（其他物品没有 weight 概念）
    kept_items = []  # 用于在结果中告知玩家留了什么
    if keep_spec and filt["category"] == "fish":
        pre_keep_count = len(matched)
        matched, kept_items = apply_keep(matched, keep_spec)
        if not matched:
            keep_desc = f"留{'大' if keep_spec['mode'] == 'largest' else '小'} {keep_spec['count']} 条"
            yield event.plain_result(
                f"❌ 筛选后 {pre_keep_count} 条鱼，{keep_desc} 后没有可卖的了\n"
                f"💡 减少保留数量试试"
            )
            return
    elif keep_spec and filt["category"] != "fish":
        yield event.plain_result("⚠️ 保留功能仅对鱼生效，已忽略保留参数")
        keep_spec = None

    if not matched:
        yield event.plain_result(
            f"❌ 背包里没有符合条件的物品\n"
            f"筛选: {format_filter_label(filt) or '无'}"
        )
        return

    cat = filt["category"]
    sold_all = []
    total = 0
    if cat == "fish":
        from ..fishing.fishing_manager import format_length, length_for_size_label
        for fish in matched:
            weight = fish.get("weight", 0)
            price = calc_sell_price(fish["name"], weight, user)
            length_cm = fish.get("length_cm")
            if length_cm is None and fish.get("size_label"):
                length_cm = length_for_size_label(fish["size_label"], FISHES.get(fish["name"]))
            # 9/6: 取鱼 rarity 供 SELL_RESULT 卡片染色
            fish_def = fish.get("_fish_def") or FISHES.get(fish["name"], {})
            rarity = fish_def.get("rarity", "common")
            sold_all.append({
                "name": fish["name"],
                "weight": weight,
                "size_label": fish.get("size_label", ""),
                "length_str": format_length(length_cm) if length_cm is not None else "",
                "gold": price,
                "rarity": rarity,
                "rarity_color": rarity_color(rarity),
                "rarity_cn": RARITY_NAMES.get(rarity, ""),  # 9/6
            })
            _remove_from_inventory(user, fish)
            total += price
    else:
        from collections import defaultdict
        by_name = defaultdict(int)
        for it in matched:
            by_name[it["name"]] += it.get("quantity", 1)
        for name, qty in by_name.items():
            price_each = calc_sell_price(name, weight=0, user=user)
            price = price_each * qty
            # 9/6: 取物品 rarity 供 SELL_RESULT 染色
            item_def = ITEMS.get(name, {})
            rarity = item_def.get("rarity", "common")
            sold_all.append({
                "name": name, "quantity": qty, "gold": price,
                "rarity": rarity,
                "rarity_color": rarity_color(rarity),
                "rarity_cn": RARITY_NAMES.get(rarity, ""),  # 9/6
            })
            for it in list(user.get("inventory", [])):
                if it.get("name") == name and it.get("type") == cat:
                    _remove_from_inventory(user, it)
                    break
            total += price

    if total <= 0:
        yield event.plain_result(f"❌ 没有可卖的物品 (筛选: {format_filter_label(filt) or '无'})")
        return

    user["gold"] = user.get("gold", 0) + total
    lifetime = user.setdefault("lifetime_stats", {})
    lifetime["total_gold_earned"] = lifetime.get("total_gold_earned", 0) + total
    lifetime["total_sold_count"] = lifetime.get("total_sold_count", 0) + len(sold_all)
    await store.update_user(user_id, user)

    filter_label = format_filter_label(filt)
    text = _format_sell_filter_text(user, sold_all, total, filter_label, kept_items)
    # 9/6: 改用 sender.send_card()
    data = {
        "avatar_url": f"https://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=100&img_type=png",
        "user_id_short": user_id[:6],
        "nickname": user.get("nickname", "玩家"),
        "sold_records": sold_all,
        "total_gold": total,
        "total_count": len(sold_all),
        "filter_label": filter_label,
        "kept_records": [
            {
                "name": k.get("name", "?"),
                "weight": k.get("weight", 0),
                "weight_str": format_weight(k.get("weight", 0)),  # 9/8: 紧凑格式
                "size_label": k.get("size_label", ""),
                "rarity": k.get("rarity", "common"),  # 9/6: 染色
                "rarity_color": k.get("rarity_color", rarity_color("common")),
            }
            for k in kept_items
        ],
    }
    async for r in sender.send_card(
        event, CardType.SELL_RESULT, data,
        fallback_text=text,
        render_height=440,
    ):
        yield r


def _format_sell_filter_text(user: dict, sold: list[dict], total: int,
                              filter_label: str, kept_items: list = None) -> str:
    """筛选卖的纯文本结果。"""
    nickname = user.get("nickname", "玩家")
    lines = [
        f"💰 {nickname} 筛选卖结果{f' ({filter_label})' if filter_label else ''}",
        "━━━━━━━━━━━━━━━",
    ]
    for s in sold:
        if s.get("quantity"):
            lines.append(f"  • {s['name']} ×{s['quantity']} = {s['gold']} 金币")
        else:
            extra = s.get("length_str", "")
            lines.append(
                f"  • 🐟 {s['name']} {s.get('weight', 0)}kg {extra} = {s['gold']} 金币"
            )
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"💎 共 {len(sold)} 件 = {total} 金币")
    if kept_items:
        lines.append("")
        lines.append(f"🪝 保留:")
        for k in kept_items:
            lines.append(f"  • 🐟 {k.get('name', '?')} {k.get('weight', 0)}kg ({k.get('size_label', '')})")
    return "\n".join(lines)


def _format_sell_text(user: dict, sold: list[dict], total: int) -> str:
    """卖鱼结果文本 (降级用)。"""
    nickname = user.get("nickname", "玩家")
    if not sold:
        return f"💰 {nickname} 没有卖出任何物品"
    lines = [f"💰 {nickname} 交易结果:"]
    by_species = {}
    for s in sold:
        key = s["name"]
        if key not in by_species:
            by_species[key] = {"count": 0, "weight": 0.0, "gold": 0}
        by_species[key]["count"] += 1
        by_species[key]["weight"] += s.get("weight", 0)
        by_species[key]["gold"] += s["gold"]
    for name, info in by_species.items():
        lines.append(f"  • {name} ×{info['count']} = {info['gold']} 金币")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"💎 总计: {len(sold)} 件 = {total} 金币")
    return "\n".join(lines)


def _format_overview_text(user: dict, inv: list, inv_count: int, inv_gold: int,
                           stocks: list, stock_cost: int,
                           assets: list, asset_total: int) -> str:
    """可售清单文本 (降级用)。"""
    nickname = user.get("nickname", "玩家")
    lines = [f"💼 {nickname} 的可售清单", "━━━━━━━━━━━━━━━"]

    # 1. 背包可售
    if inv:
        lines.append(f"📦 背包可售 ({len(inv)} 种 / {inv_count} 件 / {inv_gold} 金币)")
        for it in inv[:8]:
            t_emoji = {"fish": "🐟", "food": "🍖", "item": "🎒"}.get(it["type"], "•")
            detail = f"{format_weight(it['weight'])}" if it["type"] == "fish" and it["weight"] else ""
            lines.append(f"  {t_emoji} {it['name']} ×{it['count']} {detail} = {it['total_gold']}G")
        if len(inv) > 8:
            lines.append(f"  ... 还有 {len(inv) - 8} 种")
    else:
        lines.append("📦 背包可售: 空")

    # 2. 股票
    if stocks:
        lines.append(f"\n📈 股票持仓 ({len(stocks)} 支 / 成本 {stock_cost}G)")
        for s in stocks[:5]:
            lines.append(f"  📊 {s['name']}({s['code']}) ×{s['quantity']} 成本 {s['cost_total']}G")
        if len(stocks) > 5:
            lines.append(f"  ... 还有 {len(stocks) - 5} 支")
        lines.append(f"  💡 详细市值请用 /股市 持股")
    else:
        lines.append(f"\n📈 股票持仓: 空")

    # 3. 其他资产
    if assets:
        lines.append(f"\n🏛️ 其他资产 ({len(assets)} 项 / {asset_total}G)")
        for a in assets:
            lines.append(f"  {a['detail']} {a['name']} = {a['sell_price']}G")
    else:
        lines.append(f"\n🏛️ 其他资产: 无")

    # 帮助
    lines.append("\n━━━━━━━━━━━━━━━")
    lines.append("💡 出售命令:")
    lines.append("  /卖 草鱼       - 卖指定名字")
    lines.append("  /卖 草鱼 3     - 卖 3 条")
    lines.append("  /卖 草鱼 大    - 卖最大那条")
    lines.append("  /卖 全部       - ⚠️ 显式确认后卖所有")

    return "\n".join(lines)


async def run_sell_logic(event: AstrMessageEvent, store, parser, sender):
    """通用卖命令逻辑.

    9/6: 改用 MessageSender.send_card() 替代 5 处散落 try/except + renderer._render 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先 /签到 注册")
        return

    _, args = parser.parse(event)

    # ============================================
    # 默认模式 (/卖 无参数): 只展示可售清单 (不执行)
    # ============================================
    if len(args) == 0:
        inv, inv_count, inv_gold = list_sellable_inventory(user)
        # 9/8: 给每条鱼加 weight_str 紧凑格式 (sell 卡片用)
        for it in inv:
            if it.get("type") == "fish":
                it["weight_str"] = format_weight(it.get("weight", 0))
        stocks, stock_cost = list_stock_holdings(user)
        assets, asset_total = list_other_assets(user)
        total_estimated = inv_gold + asset_total

        # 9/6: 改用 sender.send_card() (替代 try/except + yield image_result/plain_result 样板)
        data = {
            "avatar_url": f"https://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=100&img_type=png",
            "user_id_short": user_id[:6],
            "nickname": user.get("nickname", "玩家"),
            "inventory_items": inv,
            "inventory_count": inv_count,
            "inventory_gold": inv_gold,
            "stocks": stocks,
            "stock_cost": stock_cost,
            "assets": assets,
            "asset_total": asset_total,
            "total_estimated": total_estimated,
        }
        async for r in sender.send_card(
            event, CardType.SELL_OVERVIEW, data,
            fallback_text=_format_overview_text(
                user, inv, inv_count, inv_gold,
                stocks, stock_cost, assets, asset_total
            ),
            render_height=400,
        ):
            yield r
        return

    # ============================================
    # 入口处统一抽 keep token，让两条 sell 路径都能用
    # 例: /卖 草鱼 留大 1 / /卖 鱼 大 留大 2
    # ============================================
    keep_parse = parse_keep_token(args)
    keep_spec = keep_parse["keep"]
    args = keep_parse["remaining_args"]

    # ============================================
    # 筛选卖分支 (/卖 鱼|食物|物品 [尺寸/稀有度]...)
    # ============================================
    from ._helpers import _CATEGORY_ALIASES as _CAT
    if args and args[0] in _CAT and _CAT[args[0]] is not None and args[0] not in ("全部", "all", "全"):
        async for r in _run_sell_with_filter(event, user, store, sender, args, keep_spec):
            yield r
        return

    # ============================================
    # 执行模式 (有参数): 卖指定物品 (支持 keep token)
    # ============================================
    name_filter: Optional[str] = None
    count: Optional[int] = None
    mode: str = "all"

    if len(args) == 1:
        arg = args[0]
        if arg in ("全部", "all"):
            # 显式 /卖 全部 -> 执行售卖
            sold, total = sell_all_sellable(user)
            if not sold:
                yield event.plain_result("❌ 背包里没有可卖的物品")
                return
            user["gold"] = user.get("gold", 0) + total
            lifetime = user.setdefault("lifetime_stats", {})
            lifetime["total_gold_earned"] = lifetime.get("total_gold_earned", 0) + total
            lifetime["total_sold_count"] = lifetime.get("total_sold_count", 0) + len(sold)
            await store.update_user(user_id, user)

            # 9/6: 改用 sender.send_card()
            text = _format_sell_text(user, sold, total)
            data = {
                "avatar_url": f"https://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=100&img_type=png",
                "user_id_short": user_id[:6],
                "nickname": user.get("nickname", "玩家"),
                "sold_records": sold,
                "total_gold": total,
                "total_count": len(sold),
            }
            async for r in sender.send_card(
                event, CardType.SELL_RESULT, data,
                fallback_text=text,
                render_height=400,
            ):
                yield r
            return
        else:
            name_filter = arg
    elif len(args) >= 2:
        name_filter = args[0]
        arg2 = args[1]
        if arg2 in ("大", "biggest", "max"):
            mode = "largest"
        elif arg2 in ("小", "smallest", "min"):
            mode = "smallest"
        elif arg2.isdigit():
            count = int(arg2)
        else:
            yield event.plain_result(
                f"❌ 未知参数: {arg2}\n"
                f"用法: /卖 [物品名] [数量|最大|最小]\n"
                f"💡 可叠加: /卖 草鱼 留大 1 (留最大1条, 其余卖)"
            )
            return

    # 执行指定物品售卖
    if name_filter and not can_sell(name_filter):
        yield event.plain_result(
            f"❌ [{name_filter}] 不可卖 (不在市场表)\n"
            f"💡 提示: 玩家间交易 (PVP) 暂未开放"
        )
        return

    sold, total, err = sell_items(user, name=name_filter, count=count, mode=mode)
    if err:
        yield event.plain_result(err)
        return
    if not sold:
        yield event.plain_result(f"❌ 背包里没有 [{name_filter}]")
        return

    # 保留逻辑 — 仅对鱼生效
    kept_items = []
    if keep_spec and name_filter and any(s.get("weight") for s in sold):
        from ..fishing.fishing_manager import FISHES, _ensure_loaded
        _ensure_loaded()
        from ..fishing.fishing_manager import format_length, length_for_size_label
        # 已卖的里抽 keep 出来回填到 inventory
        to_keep = [s for s in sold if s.get("weight") is not None]
        to_keep, kept = apply_keep(to_keep, keep_spec)
        # 把 kept 重新塞回 inventory
        for k in kept:
            inv_item = {
                "type": "fish",
                "name": k.get("name"),
                "weight": k.get("weight"),
                "size_label": k.get("size_label", ""),
                "length_cm": k.get("length_cm"),
                "time": k.get("time"),
            }
            user["inventory"].append(inv_item)
            kept_items.append({
                "name": k.get("name", "?"),
                "weight": k.get("weight", 0),
                "size_label": k.get("size_label", ""),
                "rarity": k.get("rarity", "common"),  # 9/6
                "rarity_color": k.get("rarity_color", rarity_color("common")),
            })
        # 重算 sold / total
        sold = to_keep
        total = sum(s.get("gold", 0) for s in sold)
        # 也回退金币 (因为之前 sell_items 已经 add 了)
        user["gold"] = user.get("gold", 0) - sum(k.get("gold", 0) for k in kept)
        lifetime = user.setdefault("lifetime_stats", {})
        lifetime["total_sold_count"] = max(0, lifetime.get("total_sold_count", 0) - len(kept))

    if not sold:
        await store.update_user(user_id, user)  # 还要保存 inventory 恢复
        yield event.plain_result(
            f"❌ 卖完后没有可卖的 (全部被保留)\n"
            f"💡 减少保留数量"
        )
        return

    # 更新金币 + 统计
    user["gold"] = user.get("gold", 0) + total
    lifetime = user.setdefault("lifetime_stats", {})
    lifetime["total_gold_earned"] = lifetime.get("total_gold_earned", 0) + total
    lifetime["total_sold_count"] = lifetime.get("total_sold_count", 0) + len(sold)
    await store.update_user(user_id, user)

    # 9/6: 改用 sender.send_card()
    text = _format_sell_text(user, sold, total)
    if kept_items:
        text += "\n\n🪝 保留:\n" + "\n".join(
            f"  • 🐟 {k['name']} {k['weight']}kg ({k['size_label']})"
            for k in kept_items
        )
    data = {
        "avatar_url": f"https://q.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=100&img_type=png",
        "user_id_short": user_id[:6],
        "nickname": user.get("nickname", "玩家"),
        "sold_records": sold,
        "total_gold": total,
        "total_count": len(sold),
        "kept_records": kept_items,
    }
    async for r in sender.send_card(
        event, CardType.SELL_RESULT, data,
        fallback_text=text,
        render_height=440,
    ):
        yield r
