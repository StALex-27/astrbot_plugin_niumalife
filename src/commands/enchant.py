"""附魔系统 - 9/4晚

用法:
1. /使用 <附魔券> <物品> (如 /使用 普通附魔券 竹竿)
2. /附魔 <物品> <附魔券> (如 /附魔 竹竿 普通附魔券)
3. /附魔 <物品> (使用背包第一张附魔券)

附魔券概率表:
- 普通附魔券: 70%优秀,25%稀有,4%史诗,1%传说
- 优秀附魔券: 50%优秀,35%稀有,10%史诗,4%传说,1%神话
- 稀有附魔券: 30%优秀,45%稀有,15%史诗,8%传说,2%神话
- 史诗附魔券: 20%优秀,30%稀有,30%史诗,18%传说,3%神话
- 传说附魔券: 10%优秀,20%稀有,35%史诗,30%传说,5%神话
- 神话附魔券: 10%稀有,40%史诗,40%传说,10%神话
"""
import random
from typing import AsyncGenerator, Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.entry_lib import (
    RARITY_MULT_RANGE,
    resolve_effects,
)
from ...modules.item import ITEMS, RARITY_NAMES, RARITY_COLORS
from ...modules.renderer import CardRenderer  # noqa: F401  # 保留 import 兼容老代码


# 9/4晚: 附魔券概率表
ENCHANT_TABLE = {
    "normal": {
        "uncommon": 70, "rare": 25, "epic": 4, "legendary": 1,
    },
    "uncommon": {
        "uncommon": 50, "rare": 35, "epic": 10, "legendary": 4, "mythic": 1,
    },
    "rare": {
        "uncommon": 30, "rare": 45, "epic": 15, "legendary": 8, "mythic": 2,
    },
    "epic": {
        "uncommon": 20, "rare": 30, "epic": 30, "legendary": 18, "mythic": 3,
    },
    "legendary": {
        "uncommon": 10, "rare": 20, "epic": 35, "legendary": 30, "mythic": 5,
    },
    "mythic": {
        "rare": 10, "epic": 40, "legendary": 40, "mythic": 10,
    },
}


def roll_enchant(enchant_type: str) -> str:
    """根据附魔券类型抽取新稀有度"""
    table = ENCHANT_TABLE[enchant_type]
    rarities = list(table.keys())
    weights = list(table.values())
    return random.choices(rarities, weights=weights, k=1)[0]


def _is_enchantable(inventory_entry: dict) -> bool:
    """判断 inventory entry 是否可附魔 (有 rarity + bonus_pool)"""
    item_info = ITEMS.get(inventory_entry.get("id"))
    if not item_info:
        return False
    return bool(item_info.get("bonus_pool"))


def _consume_scroll(user: dict, scroll_id: str) -> bool:
    """消耗背包中 1 个附魔券"""
    inventory = user.get("inventory", [])
    for i, inv in enumerate(inventory):
        if inv.get("id") == scroll_id and inv.get("category") == "enchant":
            qty = inv.get("quantity", 1)
            if qty > 1:
                inv["quantity"] = qty - 1
            else:
                inventory.pop(i)
            user["inventory"] = inventory
            return True
    return False


def _find_inventory_entry(user: dict, target: str) -> tuple[Optional[int], Optional[dict]]:
    """在背包中找指定物品 entry, 支持序号/ID/name"""
    inventory = user.get("inventory", [])
    # 1. 尝试序号
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(inventory):
            entry = inventory[idx]
            if _is_enchantable(entry):
                return idx, entry
            return None, None
    # 2. 按 ID 或 name 匹配
    for i, inv in enumerate(inventory):
        if inv.get("id") == target or inv.get("name") == target:
            if _is_enchantable(inv):
                return i, inv
    return None, None


def _find_first_scroll(user: dict) -> Optional[str]:
    """找背包第一张附魔券 (按品质从低到高)"""
    order = ["普通附魔券", "优秀附魔券", "稀有附魔券", "史诗附魔券", "传说附魔券", "神话附魔券"]
    inventory = user.get("inventory", [])
    for scroll_id in order:
        for inv in inventory:
            if inv.get("id") == scroll_id:
                return scroll_id
    return None


async def run_enchant_logic(
    event: AstrMessageEvent,
    store,
    args: list[str],
    sender,
) -> AsyncGenerator:
    """/附魔 <物品> [附魔券]

    /附魔 竹竿
    /附魔 竹竿 普通附魔券
    /附魔 1 普通附魔券  (按序号)

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    """
    sender_id = str(event.get_sender_id())
    user = await store.get_user(sender_id)
    if not user:
        yield event.plain_result("❌ 请先发送「档案」创建用户")
        return

    if not args:
        yield event.plain_result(
            "📌 用法:\n"
            "  /附魔 <物品> (使用背包第一张附魔券)\n"
            "  /附魔 <物品> <附魔券>\n"
            "  /使用 <附魔券> <物品>"
        )
        return

    # 解析参数 (智能识别附魔券 vs 物品)
    if len(args) == 1:
        target = args[0]
        scroll_id = _find_first_scroll(user)
        if not scroll_id:
            yield event.plain_result("❌ 背包中没有附魔券，请先购买")
            return
    else:
        arg1, arg2 = args[0], args[1]
        arg1_is_scroll = arg1 in ENCHANT_TABLE
        arg2_is_scroll = arg2 in ENCHANT_TABLE

        # 检查 arg1/arg2 是否在背包且可附魔
        arg1_is_enchantable_item = False
        arg2_is_enchantable_item = False
        for inv in user.get("inventory", []):
            if inv.get("id") == arg1 or inv.get("name") == arg1:
                if _is_enchantable(inv):
                    arg1_is_enchantable_item = True
                    break
        for inv in user.get("inventory", []):
            if inv.get("id") == arg2 or inv.get("name") == arg2:
                if _is_enchantable(inv):
                    arg2_is_enchantable_item = True
                    break

        if arg1_is_scroll and arg2_is_enchantable_item:
            scroll_id, target = arg1, arg2
        elif arg2_is_scroll and arg1_is_enchantable_item:
            scroll_id, target = arg2, arg1
        elif arg1_is_scroll:
            scroll_id, target = arg1, arg2
        elif arg2_is_scroll:
            scroll_id, target = arg2, arg1
        else:
            yield event.plain_result(f"❌ 无法识别参数: {' '.join(args)}")
            return

    # 验证附魔券在背包
    inventory = user.get("inventory", [])
    scroll_entry = None
    for inv in inventory:
        if inv.get("id") == scroll_id and inv.get("category") == "enchant":
            scroll_entry = inv
            break
    if not scroll_entry:
        yield event.plain_result(f"❌ 背包中没有 {scroll_id}")
        return

    # 找物品 entry
    idx, target_entry = _find_inventory_entry(user, target)
    if idx is None or target_entry is None:
        yield event.plain_result(f"❌ 背包中找不到可附魔的「{target}」(需要是渔具或拟饵)")
        return

    # 执行附魔
    enchant_type = scroll_entry.get("enchant_type", "normal")
    old_rarity = target_entry.get("rarity", "common")
    old_rarity_mult = target_entry.get("rarity_mult", 1.0)

    # 抽新 rarity + rarity_mult
    new_rarity = roll_enchant(enchant_type)
    mult_range = RARITY_MULT_RANGE.get(new_rarity, (1.0, 1.0))
    new_rarity_mult = round(random.uniform(*mult_range), 3)

    # 9/4晚: 渲染附魔结果卡片 (含词条一览 + 基础属性)
    item_id = target_entry.get("id", "")
    item_def = ITEMS.get(item_id, {})
    new_effects = resolve_effects(item_def, new_rarity, new_rarity_mult)

    # 更新 inventory entry
    inventory[idx]["rarity"] = new_rarity
    inventory[idx]["rarity_mult"] = new_rarity_mult
    # 9/6: 把新 effects 写回 entry, 让 /渔具 等显示新词条
    inventory[idx]["effects"] = new_effects

    # 消耗附魔券
    _consume_scroll(user, scroll_id)

    user["inventory"] = inventory
    await store.update_user(sender_id, user)

    # 附魔券剩余数量
    scroll_remaining = 0
    for inv in user.get("inventory", []):
        if inv.get("id") == scroll_id:
            scroll_remaining = inv.get("quantity", 1)
            break

    # 9/6: 改用 sender.send_card() (enchant 渲染模板)
    # 模板需要 entries[]/base_attrs[], 走 view_for_enchant_card 转换 raw new_effects
    from ..data.user_view import view_for_enchant_card
    old_color = RARITY_COLORS.get(old_rarity, "⚪")
    new_color = RARITY_COLORS.get(new_rarity, "⚪")
    old_name = RARITY_NAMES.get(old_rarity, old_rarity)
    new_name = RARITY_NAMES.get(new_rarity, new_rarity)
    data = view_for_enchant_card(
        user=user,
        target_entry=target_entry,
        old_rarity=old_rarity,
        old_mult=old_rarity_mult,
        new_rarity=new_rarity,
        new_mult=new_rarity_mult,
        new_effects=new_effects,
        scroll_name=scroll_id,
        scroll_remaining=scroll_remaining,
        scroll_color=RARITY_COLORS.get(scroll_entry.get("rarity", "common"), "⚪"),
    )
    fallback_text = (
        f"✨ 附魔成功！\n"
        f"📜 {scroll_id} → {target_entry.get('name', target_entry['id'])}\n"
        f"{old_color} {old_name} (×{old_rarity_mult}) → {new_color} {new_name} (×{new_rarity_mult})"
    )
    async for r in sender.send_card(
        event, "enchant", data, fallback_text=fallback_text,
    ):
        yield r


async def run_use_logic(
    event: AstrMessageEvent,
    store,
    args: list[str],
) -> AsyncGenerator:
    """/使用 <物品> [目标] - 通用使用命令"""
    if not args:
        yield event.plain_result("📌 用法:\n  /使用 <物品> [目标]")
        return

    sender_id = str(event.get_sender_id())
    user = await store.get_user(sender_id)
    if not user:
        yield event.plain_result("❌ 请先发送「档案」创建用户")
        return

    # 判断第一参数是否为附魔券
    first_arg = args[0]
    inventory = user.get("inventory", [])
    scroll_entry = None
    for inv in inventory:
        if inv.get("id") == first_arg and inv.get("category") == "enchant":
            scroll_entry = inv
            break

    if scroll_entry:
        if len(args) < 2:
            yield event.plain_result(f"📌 /使用 {first_arg} 需要指定目标物品")
            return
        target = args[1]
        async for result in run_enchant_logic(event, store, [target, first_arg]):
            yield result
        return

    yield event.plain_result(f"❌ 「{first_arg}」不需要使用命令，或暂不支持")
