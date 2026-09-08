"""
娱乐和吃东西命令逻辑

吃命令支持的来源（按优先级）:
1. 用户背包 inventory 中 type=fish 的鱼（按 name + size 排序）
2. 用户背包 inventory 中 type=food/item 的普通物品
3. ITEMS 中 category=food 的商店食物（要花钱买）
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_ENTERTAIN
# 9/6: Pattern 10 — 从 event 拼完整 session_key
from ..ui.message_sender import _extract_session_key
from ...modules.constants import ENTERTAINMENTS, FOODS, ITEMS, MAX_ATTRIBUTE

# 加载鱼类数据（独立于 fishing_manager, 避免循环 import）
import json as _json
from pathlib import Path as _Path
_FISHES_DATA_PATH = _Path(__file__).resolve().parent.parent.parent / "data" / "config" / "fishes.json"
try:
    _FISHES_RAW = _json.loads(_FISHES_DATA_PATH.read_text(encoding="utf-8"))
    FISHES = {k: v for k, v in _FISHES_RAW.items() if not k.startswith("_")}
except Exception as e:

    import logging as __l

    __l.getLogger(__name__).warning(f"[render] {type(e).__name__}: {e}")
    FISHES = {}


LOCAL_TZ = timezone(timedelta(hours=8))


# 属性名 → (emoji, 中文标签)
ATTR_DISPLAY = {
    "strength": ("💪", "体力"),
    "energy": ("⚡", "精力"),
    "satiety": ("🍖", "饱食"),
    "health": ("❤", "健康"),
    "mood": ("😊", "心情"),
}


def _format_effects_line(effects: dict) -> str:
    """把 effects 字典格式化成 '+xx·+yy' 显示。自动跳过 0 值的属性。"""
    parts = []
    # 优先级顺序: 体力 > 精力 > 饱食 > 健康 > 心情
    for key in ("strength", "energy", "satiety", "health", "mood"):
        v = effects.get(key, 0)
        if v:
            emoji, label = ATTR_DISPLAY.get(key, ("?", key))
            parts.append(f"{emoji}{label} +{v}")
    return " · ".join(parts) if parts else "无效果"


def _apply_food_effects(attrs: dict, **effects) -> None:
    """把 effects 字典所有非零值应用到 attrs（原地修改）。"""
    for attr_key, val in effects.items():
        if val:
            attrs[attr_key] = min(MAX_ATTRIBUTE, attrs.get(attr_key, 0) + val)


def _format_entertainment_list() -> str:
    """格式化娱乐列表"""
    items = list(ENTERTAINMENTS.items())[:8]
    return "\n".join([f"{i}. 🎮 {n} {e.get('cost_per_hour', 0)}金/时" for i, (n, e) in enumerate(items, 1)])


def _format_user_inventory_food(user: dict) -> str:
    """列出用户背包里所有可吃的（鱼 + 食物 + 道具）"""
    lines = []
    for it in user.get("inventory", []):
        if it.get("type") == "fish":
            from ..fishing.fishing_manager import length_for_size_label, format_length, format_weight
            cm = it.get("length_cm")
            if cm is None and it.get("size_label"):
                cm = length_for_size_label(it["size_label"])
            length_str = format_length(cm) if cm is not None else ""
            weight_str = format_weight(it.get("weight", 0))
            lines.append(f"• 🐟 {it['name']} {weight_str} {length_str}")
        elif it.get("type") in ("food", "item"):
            emoji = it.get("emoji", "🍖")
            qty = it.get("quantity", 1)
            lines.append(f"• {emoji} {it['name']} x{qty}")
    return "\n".join(lines) if lines else "（背包没有可吃的）"


def _find_inventory_food(user: dict, name: str, index: int = 0) -> Optional[dict]:
    """在用户背包找指定名称的可吃物品。index 处理同名多件。
    鱼按 size_label 排序（先小后大），其他按出现顺序。
    """
    matches = []
    for it in user.get("inventory", []):
        # 9/3: 药品 (medicine) 也算可消耗, 可走 do_eat 流程
        # 兜底: 旧 buy_item 数据可能没 category/type 字段, 反查 ITEMS 补
        it_category = it.get("category") or (ITEMS.get(it.get("id") or it.get("name", ""), {}).get("category"))
        it_type = it.get("type") or (ITEMS.get(it.get("id") or it.get("name", ""), {}).get("type"))
        if it.get("name") == name and it_type in ("fish", "food", "item"):
            matches.append(it)
        elif it.get("name") == name and it_category in ("food", "medicine"):
            matches.append(it)
    if not matches:
        return None
    if it.get("type") == "fish":
        # 鱼按 weight 升序（先吃小的）
        matches.sort(key=lambda x: x.get("weight", 0))
    if index >= len(matches):
        return None
    return matches[index]


def _format_fish_meal(name: str, fish_data: dict) -> str:
    """生成吃鱼的提示文本"""
    emoji = fish_data.get("emoji", "🐟")
    weight = fish_data.get("weight", 0)
    size_label = fish_data.get("size_label", "")
    from ..fishing.fishing_manager import length_for_size_label, format_length, format_weight
    cm = fish_data.get("length_cm")
    if cm is None and size_label:
        cm = length_for_size_label(size_label, fish_data)
    length_str = format_length(cm) if cm is not None else ""
    weight_str = format_weight(weight)
    sat = fish_data.get("satiety_restore", 0)
    mood = fish_data.get("mood_restore", 0)
    desc = fish_data.get("desc", "")
    return (
        f"🍽️ 食用 {emoji} {name} ({length_str}, {weight_str})\n"
        f"饱食 +{sat}, 心情 +{mood}\n"
        f"💬 {desc}"
    )


async def run_entertain_logic(event: AstrMessageEvent, store, parser, sender):
    """娱乐命令逻辑.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    if user["status"] != UserStatus.FREE:
        yield event.plain_result(f"📋 你正在{user['status']}，无法娱乐")
        return

    _, args = parser.parse(event)

    ent_name = args[0] if len(args) >= 1 else None
    hours = int(args[1]) if len(args) >= 2 else None

    if not ent_name:
        yield event.plain_result(
            f"🎮 娱乐列表:\n━━━━━━━━━━━━━━\n{_format_entertainment_list()}\n━━━━━━━━━━━━━━\n"
            f"回复: /娱乐 名称 小时数\n例如: /娱乐 游戏 2"
        )
        return

    entertainment = ENTERTAINMENTS.get(ent_name)
    if not entertainment:
        yield event.plain_result(f"📋 不存在该娱乐：{ent_name}")
        return

    if not hours:
        hours = 2

    total_cost = entertainment.get("cost_per_hour", 0) * hours
    if user["gold"] < total_cost:
        yield event.plain_result(f"📋 金币不足！需要 {total_cost} 金币，你只有 {user['gold']} 金币")
        return

    now = datetime.now(LOCAL_TZ)
    # 9/6: Pattern 10 — tick 完成通知按此 key 查缓存 event
    session_key = _extract_session_key(event) or ""
    detail = ActionDetail.create(
        action_type=TICK_TYPE_ENTERTAIN,
        hours=hours,
        start_time=now,
        entertainment_name=ent_name,
        cost_per_hour=entertainment.get("cost_per_hour", 0),
        restore_mood=entertainment.get("restore_mood", 0),
        consume_strength=entertainment.get("consume_strength", 0),
        consume_energy=entertainment.get("consume_energy", 0),
        session_key=session_key,
    )

    user["status"] = UserStatus.ENTERTAINING
    user["current_action"] = TICK_TYPE_ENTERTAIN
    user["action_detail"] = detail
    await store.update_user(user_id, user)

    # 9/6: 改用 sender.send_card() (entertain_start 渲染模板)
    data = {
        "user_id": user_id,
        "ent_name": ent_name,
        "ent_emoji": entertainment.get("emoji", "🎮"),
        "hours": hours,
        "gain_mood": entertainment.get('restore_mood', 0) * hours,
        "consume_satiety": int(entertainment.get('consume_strength', 0) * hours),
    }
    fallback_text = (
        f"✅ 开始娱乐:\n━━━━━━━━━━━━━━\n"
        f"🎮 {ent_name} x {hours}小时\n💰 花费: {total_cost}金币\n"
        f"━━━━━━━━━━━━━━\n🎉 开始娱乐！"
    )
    async for r in sender.send_card(
        event, "entertain_start", data, fallback_text=fallback_text,
    ):
        yield r


async def run_eat_logic(event: AstrMessageEvent, store, parser, renderer):
    """吃东西命令逻辑 — 支持背包物品 + 商店食物 + 多件指定

    用法:
        /吃              → 显示背包所有可吃 + 商店食物
        /吃 鱼名        → 吃背包里 1 份同名食物
        /吃 鱼名 3      → 吃 3 份 (堆叠累扣, 不堆叠会按找到顺序吃)
        /吃 鱼名 大     → 同名最大那条 (单次)
        /吃 泡面        → 吃商店食物 (扣金币)
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先 /签到 注册")
        return

    _, args = parser.parse(event)

    # 无参数 → 列出背包 + 商店食物
    if len(args) < 1:
        inv_text = _format_user_inventory_food(user)
        # 列出商店食物（按 tier 升序）
        shop_lines = []
        for n, f in sorted(FOODS.items(), key=lambda x: (x[1].get('tier', 0), x[1].get('price', 0))):
            eff = f.get('effects', {})
            attr_str = _format_effects_line(eff)
            shop_lines.append(f"  • {f.get('emoji', '🍖')} {n} {f.get('price', 0)}金  {attr_str}")
        shop_text = "\n".join(shop_lines) if shop_lines else "（暂无可购买）"
        yield event.plain_result(
            f"🍖 你的背包可吃:\n━━━━━━━━━━━━━━\n{inv_text}\n"
            f"━━━━━━━━━━━━━━\n🏪 商店食物 (按 tier 排序):\n{shop_text}\n"
            f"━━━━━━━━━━━━━━\n📝 用法:\n"
            f"  /吃 鱼名        吃背包里同名最小鱼\n"
            f"  /吃 鱼名 2      吃第 2 条\n"
            f"  /吃 鱼名 大     吃最大那条\n"
            f"  /吃 泡面        吃商店食物（扣金币）"
        )
        return

    name = args[0]
    selector = args[1] if len(args) >= 2 else None
    # 9/3 (方案 B 升级): 群聊 /吃 X N 统一为"吃 N 份" (不管堆叠/不堆叠), 避免歧义
    # selector 解析规则:
    #   - None / "大" → 吃 1 份 (单次, 不走批量路径)
    #   - 正整数 N (>=1) → 吃 N 份 (走批量路径, effects 累加)
    batch_quantity = None
    if selector and selector.isdigit():
        try:
            q = int(selector)
            if q >= 1:
                batch_quantity = q
        except (ValueError, TypeError):
            pass

    # 1. 批量吃路径 (9/3: 群聊和 LLM 都走这里)
    if batch_quantity is not None:
        # === 批量吃路径 (9/3 新增) ===
        all_matches = []
        for inv_it in user.get("inventory", []):
            it_category = inv_it.get("category") or (ITEMS.get(inv_it.get("id") or inv_it.get("name", ""), {}).get("category"))
            it_type = inv_it.get("type") or (ITEMS.get(inv_it.get("id") or inv_it.get("name", ""), {}).get("type"))
            if inv_it.get("name") == name and it_type in ("fish", "food", "item"):
                all_matches.append(inv_it)
            elif inv_it.get("name") == name and it_category in ("food", "medicine"):
                all_matches.append(inv_it)
        if not all_matches:
            yield event.plain_result(
                f"❌ 找不到 [{name}]\n"
                f"提示: 食物名需精确匹配（试试'小鲫鱼'而不是'鱼'）"
            )
            return
        # 计算实际能吃几份 (取最大堆叠数 vs 剩余可用)
        actual_eat = min(batch_quantity, sum(it.get("quantity", 1) for it in all_matches))
        # 取第一条匹配 item 算 effects (假设同名同 effects)
        first = all_matches[0]
        itype = first.get("type")
        total_sat = total_mood = total_strength = 0
        total_effects: dict = {}
        if itype == "fish":
            fish_data = FISHES.get(first.get("name"), {})
            total_sat = fish_data.get("satiety_restore", 0) * actual_eat
            total_mood = fish_data.get("mood_restore", 0) * actual_eat
            total_strength = fish_data.get("strength", 0) * actual_eat
            emoji = fish_data.get("emoji", "🐟")
            attr_line = _format_effects_line({"satiety": total_sat, "mood": total_mood, "strength": total_strength})
            header = f"🍽️ 批量吃鱼 {emoji} {name} × {actual_eat}"
        else:
            item_data = ITEMS.get(first.get("id") or name, {})
            base_effects = item_data.get("effects", {})
            total_effects = {k: v * actual_eat for k, v in base_effects.items()}
            emoji = item_data.get("emoji", "🍖")
            attr_line = _format_effects_line(total_effects)
            header = f"🍽️ 批量吃 {emoji} {name} × {actual_eat}"
        # 扣背包 (批量)
        remaining_to_eat = actual_eat
        for inv_it in all_matches:
            if remaining_to_eat <= 0:
                break
            inv_qty = inv_it.get("quantity", 1)
            if inv_qty > remaining_to_eat:
                inv_it["quantity"] = inv_qty - remaining_to_eat
                remaining_to_eat = 0
            elif inv_qty == remaining_to_eat:
                user["inventory"].remove(inv_it)
                remaining_to_eat = 0
            else:  # inv_qty < remaining_to_eat
                user["inventory"].remove(inv_it)
                remaining_to_eat -= inv_qty
        # 应用属性
        attrs = user["attributes"]
        if itype == "fish":
            _apply_food_effects(attrs, sat=total_sat, mood=total_mood, strength=total_strength)
        else:
            _apply_food_effects(attrs, **total_effects)
        user["attributes"] = attrs
        await store.update_user(user_id, user)
        # 提示信息
        leftover = batch_quantity - actual_eat
        leftover_msg = f"\n⚠️ 想吃 {batch_quantity} 个但背包只有 {sum(it.get('quantity', 1) for it in all_matches)} 个" if leftover > 0 else ""
        yield event.plain_result(
            f"{header}\n"
            f"{attr_line}\n"
            f"━━━━━━━━━━━━━━\n"
            f"📦 背包已更新{leftover_msg}"
        )
        return

    if selector == "大":
        # 找最大那条
        all_matches = []
        for inv_it in user.get("inventory", []):
            # 9/3: 药品 (medicine) 也算可消耗
            # 兜底: 旧数据可能没 category/type 字段, 反查 ITEMS 补
            it_category = inv_it.get("category") or (ITEMS.get(inv_it.get("id") or inv_it.get("name", ""), {}).get("category"))
            it_type = inv_it.get("type") or (ITEMS.get(inv_it.get("id") or inv_it.get("name", ""), {}).get("type"))
            if inv_it.get("name") == name and it_type in ("fish", "food", "item"):
                all_matches.append(inv_it)
            elif inv_it.get("name") == name and it_category in ("food", "medicine"):
                all_matches.append(inv_it)
        if not all_matches:
            pass  # fallback 到商店
        else:
            if all_matches[0].get("type") == "fish":
                all_matches.sort(key=lambda x: x.get("weight", 0), reverse=True)
            target_item = all_matches[0]
            index = 0
    else:
        # 9/3: 无 selector 或非数字 selector, 默认单次 (index=0)
        index = 0
    # 注: 数字 selector 不再走"第 N 个"分支, 改走上面的 batch_quantity 批量路径

    inv_item = _find_inventory_food(user, name, index)

    if inv_item is not None:
        # === 吃背包物品 ===
        itype = inv_item.get("type")
        # 提前初始化（pyright 看不到 if 分支内的赋值）
        sat = 0
        mood = 0
        strength = 0
        fish_data: dict = {}
        effects: dict = {}
        if itype == "fish":
            fish_data = FISHES.get(inv_item["name"], {})
            sat = fish_data.get("satiety_restore", 0)
            mood = fish_data.get("mood_restore", 0)
            strength = fish_data.get("strength", 0)
            emoji = fish_data.get("emoji", "🐟")
            weight = inv_item.get("weight", 0)
            from ..fishing.fishing_manager import length_for_size_label, format_length, format_weight
            cm = inv_item.get("length_cm")
            if cm is None and inv_item.get("size_label"):
                cm = length_for_size_label(inv_item["size_label"], fish_data)
            length_str = format_length(cm) if cm is not None else ""
            weight_str = format_weight(weight)
            desc = fish_data.get("desc", "")
            cost = 0
            header = f"🍽️ 吃鱼 {emoji} {name} ({length_str}, {weight_str})"
            attr_line = _format_effects_line({"satiety": sat, "mood": mood, "strength": strength})
        else:
            # 普通食物 / 物品（用 ITEMS 的 effects）
            item_data = ITEMS.get(inv_item.get("id") or name, {})
            effects = item_data.get("effects", {})
            emoji = item_data.get("emoji", "🍖")
            desc = item_data.get("desc", "")
            cost = 0
            header = f"🍽️ 吃 {emoji} {name}"
            attr_line = _format_effects_line(effects)

        # 扣减背包
        if inv_item.get("quantity", 1) > 1:
            inv_item["quantity"] -= 1
        else:
            user["inventory"].remove(inv_item)

        # 应用属性
        attrs = user["attributes"]
        if itype == "fish":
            _apply_food_effects(attrs, sat=sat, mood=mood, strength=strength)
        else:
            _apply_food_effects(attrs, **effects)
        user["attributes"] = attrs

        await store.update_user(user_id, user)

        yield event.plain_result(
            f"{header}\n"
            f"{attr_line}\n"
            f"💬 {desc}\n"
            f"━━━━━━━━━━━━━━\n"
            f"📦 背包已更新"
        )
        return

    # 2. fallback 到商店食物
    food = FOODS.get(name)
    if not food:
        yield event.plain_result(
            f"❌ 找不到 [{name}]\n"
            f"提示: 食物名需精确匹配（试试'小鲫鱼'而不是'鱼'）"
        )
        return

    if user["gold"] < food["price"]:
        yield event.plain_result(f"📋 金币不足！需要 {food['price']} 金币，你只有 {user['gold']} 金币")
        return

    user["gold"] -= food["price"]
    effects = food.get("effects", {})
    attrs = user["attributes"]
    _apply_food_effects(attrs, **effects)
    user["attributes"] = attrs
    await store.update_user(user_id, user)

    yield event.plain_result(
        f"✅ 购买并食用 {food.get('emoji', '🍖')} {name}\n"
        f"💰 -{food['price']} 金币\n"
        f"{_format_effects_line(effects)}"
    )
