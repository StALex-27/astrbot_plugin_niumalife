"""
9/6 v9.5: 渔具别名加载器 (gear_builder)

设计变更:
- 31+ 件鱼竿直接写到 items.json (不再用 gear_templates 组合生成)
- 26+5 件鱼线直接写到 items.json (材质×型号)
- gear_templates.json 仅保留 aliases (供老鱼竿 ID 兼容)
"""
from __future__ import annotations

from typing import Optional

# 9/6: 别名表 (运行时从 gear_templates.json 加载)
ITEM_ALIASES: dict[str, str] = {}


def resolve_item_id(item_id: str) -> str:
    """将老鱼竿 ID 转为新 ID (例如 "玻璃钢竿" → "玻纤池竿").

    Args:
        item_id: 物品 ID (可能是老 ID)

    Returns:
        映射后的新 ID, 未命中别名则原样返回.
    """
    if not item_id:
        return item_id
    return ITEM_ALIASES.get(item_id, item_id)


def build_rod_items(templates: dict) -> dict[str, dict]:
    """9/6 v9.5: 不再生成鱼竿 (用户要求 31+ 件直接写到 items.json).

    Args:
        templates: gear_templates.json, 现只用于加载别名表

    Returns:
        空 dict (不生成). 业务数据全部在 items.json.
    """
    global ITEM_ALIASES
    # 只保留别名加载 (供老鱼竿 ID 兼容)
    aliases = templates.get("aliases", {})
    ITEM_ALIASES = dict(aliases)
    return {}
