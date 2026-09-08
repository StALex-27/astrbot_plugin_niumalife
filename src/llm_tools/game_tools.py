"""
game_tools.py — 4 只读 + 1 智能写入工具。

注册方式：在 NiumaLife 类方法上加 @filter.llm_tool(name="..."), 由 AstrBot 框架自动注册。
handler 第一个参数永远是 event (AstrMessageEvent), 框架会从当前会话上下文自动注入 user_id。

⚠️ 必须满足的条件 (来自 9/3 session 教训):
1. 每个 @filter.llm_tool 装饰的方法必须挂在 NiumaLife 类上 (不能是 free function)
2. handler 第一个参数是 event, 不是 self 或 plugin —— 框架会自动绑定 star_map[handler_module_path] 调用
3. 改文件后必须 `kill PID + restart`, watchfiles reload 不会重新注册 llm_tool (handler 重注册问题)
4. 函数 docstring 会被 docstring-parser 解析为参数描述, 必须严格遵守 Google-style (Args: / Returns:)
5. 函数返回值是 str (JSON), 不是 dict, 不能返回 None
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from astrbot.api.event import filter, AstrMessageEvent

if TYPE_CHECKING:
    from ..main import NiumaLife

_log = logging.getLogger("astrbot_plugin_niumalife.game_tools")


# ============================================================
# 工具注册入口
# ============================================================

def register_game_tools(plugin: "NiumaLife") -> None:
    """
    把所有 @filter.llm_tool 装饰的方法注册到 plugin 上。

    ⚠️ 为什么需要这一步？
    @filter.llm_tool 装饰器在模块 import 时执行, 但 handler 必须挂在 NiumaLife 实例方法上
    才能拿到 self._store 等服务。最干净的做法是在 main.py 里 @filter.llm_tool(name="...")
    直接挂在类方法上, 框架 import 时自动发现。

    这个函数保留是为了集中维护工具清单, 方便后续动态启用/禁用 (activate_llm_tool_async)。
    当前实现：直接 import 已经定义好的类方法, 加入 llm_tools 列表。

    Args:
        plugin: NiumaLife 实例 (保留用于将来动态注册, 当前是 no-op)
    """
    # @filter.llm_tool 已经在方法定义时自动注册到 llm_tools.func_list
    # 这里只打印日志方便诊断
    tools = [
        "get_player_status",
        "get_player_skills",
        "get_fishing_records",
        "get_inventory_summary",
        "execute_sell",
    ]
    _log.info(f"[game_tools] 已注册 {len(tools)} 个工具: {tools}")


# ============================================================
# 工具方法 —— 必须挂在 NiumaLife 类上 (在 main.py 里加)
# ============================================================
#
# 这些方法会被复制到 main.py NiumaLife 类内部. 这里只保留文档和单元测试用的纯函数.
# 真正的工具实现见 main.py 的 GameToolsMixin 块.

def _summarize_action_detail(detail: dict | None) -> dict | None:
    """把 action_detail (tick detail) 压缩成 LLM 友好的 summary。

    Tick detail 可能含 TickProgress 这种不可 JSON 序列化的对象, 这里只取关键字段。
    """
    if not detail:
        return None
    safe_keys = ("type", "remaining_ticks", "total_ticks", "gold_per_tick",
                 "exp_per_tick", "progress_pct", "start_time")
    return {k: detail.get(k) for k in safe_keys if k in detail}


def _ok(**fields) -> str:
    """统一 JSON 返回格式。"""
    return json.dumps(fields, ensure_ascii=False, default=str)


def _err(msg: str, **extra) -> str:
    return json.dumps({"error": msg, **extra}, ensure_ascii=False)


# ============================================================
# 纯函数 (测试用) —— 把 LLM 工具的核心逻辑抽出来便于 pytest
# ============================================================

async def _tool_get_player_status(plugin, user_id: str) -> str:
    """get_player_status 核心实现, 独立于类方法方便测试。"""
    user = await plugin._store.get_user(user_id)
    if not user:
        return _err("用户不存在, 请先发送 /签到 注册")
    attrs = user.get("attributes", {})
    return _ok(
        gold=user.get("gold", 0),
        attributes=attrs,
        status=user.get("status", "free"),
        residence=user.get("residence", "桥下"),
        current_action=user.get("current_action"),
        action_detail=_summarize_action_detail(user.get("action_detail")),
        satiety=attrs.get("satiety", 100),
    )


async def _tool_get_player_skills(plugin, user_id: str) -> str:
    """get_player_skills 核心实现。"""
    import sys
    from pathlib import Path
    _PLUGIN = Path(__file__).resolve().parent.parent.parent
    if str(_PLUGIN) not in sys.path:
        sys.path.insert(0, str(_PLUGIN))
    from modules.skills import get_skill_level, exp_to_next_level, get_skill_exp_rate
    user = await plugin._store.get_user(user_id)
    if not user:
        return _err("用户不存在")
    skills = user.get("skills", {})
    out = {}
    for k, exp in skills.items():
        rate = get_skill_exp_rate(k)
        out[k] = {
            "level": get_skill_level(exp, rate),
            "exp": exp,
            "exp_to_next": exp_to_next_level(exp, rate),
        }
    return _ok(
        skills=out,
        lifetime_peak_gold=user.get("lifetime_stats", {}).get("peak_gold", 0),
    )


async def _tool_get_fishing_records(
    plugin, user_id: str, sort_by: str = "weight", limit: int = 5
) -> str:
    """get_fishing_records 核心实现。"""
    sort_by = (sort_by or "weight").lower()
    limit = max(1, min(int(limit or 5), 50))
    user = await plugin._store.get_user(user_id)
    if not user:
        return _err("用户不存在")
    fishing = user.get("fishing", {})
    records = list(fishing.get("fish_records", []))
    if sort_by == "weight":
        records.sort(key=lambda r: r.get("weight", 0), reverse=True)
    elif sort_by == "time":
        records.sort(key=lambda r: r.get("time", ""), reverse=True)
    elif sort_by == "rarity":
        rarity_order = {"传说": 5, "传奇": 4, "史诗": 3, "稀有": 2, "不凡": 1, "常见": 0}
        records.sort(key=lambda r: rarity_order.get(r.get("rarity", "常见"), 0), reverse=True)
    return _ok(
        biggest_catch=fishing.get("biggest_catch", {}),
        fish_title=fishing.get("fish_title", ""),
        total_count=fishing.get("total_fishing_count", 0),
        total_value=fishing.get("total_fishing_value", 0),
        top_records=[
            {k: r.get(k) for k in ("fish", "weight", "length_cm", "rarity", "time")}
            for r in records[:limit]
        ],
        fish_caught_summary=fishing.get("fish_caught", {}),
    )


async def _tool_get_inventory_summary(plugin, user_id: str, category: str = "all") -> str:
    """get_inventory_summary 核心实现。"""
    import sys
    from pathlib import Path
    _PLUGIN = Path(__file__).resolve().parent.parent.parent
    if str(_PLUGIN / "src") not in sys.path:
        sys.path.insert(0, str(_PLUGIN / "src"))
    from market import list_sellable_inventory
    cat = (category or "all").lower()
    cat_map = {"fish": "fish", "food": "food", "item": "item"}
    user = await plugin._store.get_user(user_id)
    if not user:
        return _err("用户不存在")
    inv, count, gold = list_sellable_inventory(user)
    if cat != "all" and cat in cat_map:
        inv = [i for i in inv if i.get("type") == cat_map[cat]]
    # 食物类物品附加 effects 信息（让 LLM 知道哪些能恢复饱食度/健康/心情）
    items_out = []
    for i in inv:
        entry = {
            "name": i.get("name"),
            "item_id": i.get("id"),  # 显式 item_id key
            "id": i.get("id"),
            "type": i.get("type"),
            "count": i.get("count", 1),
            "weight": i.get("weight"),
            "unit_price": i.get("unit_price"),
            "value": i.get("value", 0),
        }
        # food 类型查 ITEMS 拿 effects
        if i.get("type") == "food":
            try:
                from modules.constants import ITEMS
                effects = ITEMS.get(i.get("name"), {}).get("effects", {})
                if effects:
                    entry["effects"] = effects  # 如 {"satiety": 30, "mood": 5}
                    entry["effect_summary"] = _format_food_effects(effects)
            except Exception:
                pass
        items_out.append(entry)
    return _ok(
        items=items_out,
        total_count=count,
        total_value=gold,
    )


def _format_food_effects(effects: dict) -> str:
    """格式化食物效果为人话描述, 让 LLM 决定吃什么."""
    parts = []
    for k, v in effects.items():
        k_zh = {
            "satiety": "饱食度",
            "mood": "心情",
            "stamina": "体力",
            "health": "健康",
            "max_health": "健康上限",
            "sanity": "精神",
            "hp": "生命",
        }.get(k, k)
        parts.append(f"{k_zh} {v:+g}")
    return ", ".join(parts) if parts else "无效果"


async def _tool_execute_sell(
    plugin, user_id: str, item_name: str | None, count: int | None,
    category: str | None, explicit: bool, event: AstrMessageEvent,
) -> str:
    """execute_sell 核心实现 (智能确认分流)。

    Args:
        explicit: LLM 是否声明这是玩家的明确命令。
            - True: 玩家说了 "把草鱼都卖了" / "卖3条鲤鱼" / "全卖了"
              → 直接执行, 不再询问
            - False: LLM 推测 ("要不要把杂物清一下?")
              → 必须 yield 确认卡, 等用户回复
              → 但本函数是纯函数, 不 yield; 由 main.py 的 @filter.llm_tool wrapper 决定是否 yield
    """
    # 估算 (不真改数据)
    import sys
    from pathlib import Path
    _PLUGIN = Path(__file__).resolve().parent.parent.parent
    if str(_PLUGIN / "src") not in sys.path:
        sys.path.insert(0, str(_PLUGIN / "src"))
    from market import list_sellable_inventory
    user = await plugin._store.get_user(user_id)
    if not user:
        return _err("用户不存在")

    inv, total_count, total_gold = list_sellable_inventory(user)
    if total_count == 0:
        return _err("背包是空的, 没东西可卖")

    # 过滤
    target = []
    cat_map = {"fish": "fish", "food": "food", "item": "item"}
    cat = (category or "").lower()
    if item_name:
        target = [i for i in inv if i.get("name") == item_name]
        if not target:
            return _err(f"背包里没有「{item_name}」")
    elif cat in cat_map:
        target = [i for i in inv if i.get("type") == cat_map[cat]]
        if not target:
            return _err(f"背包里没有 {cat} 类物品")
    else:
        target = inv

    # 计算预估 —— list_sellable_inventory 返回的字段是 total_gold / unit_price / count
    if count and count > 0:
        # count 限定: 按单价累加前 count 条 (鱼每条不同价, 取平均)
        flat = []
        for i in target:
            unit_p = i.get("unit_price", 0)
            for _ in range(i.get("count", 1)):
                flat.append(unit_p)
        flat = flat[:count]
        preview_gold = sum(flat)
        preview_items = target  # 给 LLM 看汇总, 实际数量在 total_count
    else:
        preview_gold = sum(i.get("total_gold", 0) for i in target)
        preview_items = target

    preview = {
        "items": [
            {
                "name": i.get("name"),
                "type": i.get("type"),
                "count": i.get("count", 1),  # 聚合后的数量, 不是 1
            }
            for i in preview_items[:20]  # 最多列 20 种给 LLM 看
        ],
        "total_count": sum(i.get("count", 1) for i in preview_items),
        "estimated_gold": preview_gold,
        "explicit": explicit,
    }

    # 智能确认分流:
    if explicit:
        # 玩家说了明确命令 → 委托给 run_sell_logic 执行
        # 但 LLM 工具不直接 yield; 返回 JSON 让 wrapper 决定
        # 这里仅返回"已执行"占位, 实际写入由 main.py wrapper 调 run_sell_logic
        return _ok(
            action="execute_directly",
            preview=preview,
            note="玩家已明确命令, wrapper 请调用 run_sell_logic 执行",
        )
    else:
        # LLM 推测 → 返回确认请求, wrapper yield 卡片等用户回复
        return _ok(
            action="need_confirm",
            preview=preview,
            note="LLM 推测意图, wrapper 请 yield 确认卡给用户",
        )
