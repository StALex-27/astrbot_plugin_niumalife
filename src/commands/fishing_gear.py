"""
/渔具 命令逻辑 (9/3 渔具双轨制)
- /渔具          → 显示 5 槽装备状态 + 套装效果
- /渔具 装 <背包序号/名字>  → 装备
- /渔具 卸 <栏位中文/英文> → 卸下
"""
import logging
from typing import AsyncGenerator, Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.item import (
    ITEMS, RARITY_COLORS, RARITY_NAMES, SLOTS, SLOT_EMOJI,
    FISHING_GEAR_SLOTS,
    get_equipped_items, equip_item, unequip_item,
    calc_equipped_effects, format_item_effects,
    add_to_inventory,
)


# 9/4晚: 物品名显示 - 含稀有度前缀 (普通不加)
def _format_item_name(entry: dict, with_rarity: bool = True) -> str:
    """entry 可以是 equipped item dict 或 inventory entry"""
    item_id = entry.get("id", "")
    name = entry.get("name") or ITEMS.get(item_id, {}).get("name", item_id)
    if not with_rarity:
        return name
    rarity = entry.get("rarity", "common")
    if rarity == "common":
        return name
    rarity_cn = RARITY_NAMES.get(rarity, rarity)
    return f"{rarity_cn}{name}"


def _resolve_inventory_target(inventory: list, target: str) -> tuple[Optional[int], Optional[dict]]:
    """9/4晚: 在背包中按 target 找匹配的 entry

    支持:
    - 数字 → 背包序号
    - 物品 ID (如 "竹竿")
    - 物品 原始名 (如 "竹竿")
    - 物品 显示名 (如 "传说竹竿" 含稀有度前缀)

    匹配优先级:
    1. 数字 → 背包序号
    2. 显示名完全匹配 (含稀有度前缀 - 用户输 "传说竹竿")
    3. ID/原始名匹配 - 多个同名时高稀有度优先

    Returns:
        (index, inventory_entry) 或 (None, None)
    """
    # 1. 数字 → 背包序号
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(inventory):
            return idx, inventory[idx]
    # 2. 显示名完全匹配 (含稀有度前缀) - 只匹配非普通物品
    # 避免 "竹竿" 命中普通竹竿显示名 (与 ID 匹配冲突)
    for i, inv_item in enumerate(inventory):
        if inv_item.get("rarity", "common") != "common" and _format_item_name(inv_item) == target:
            return i, inv_item
    # 3. ID/原始名匹配 - 多个同名时高稀有度优先
    from ...modules.entry_lib import RARITY_RANK
    matches = []
    for i, inv_item in enumerate(inventory):
        inv_id = inv_item.get("id", "")
        if inv_id == target or ITEMS.get(inv_id, {}).get("name") == target:
            matches.append((i, inv_item))
    if matches:
        # 按 rarity 排序, 高稀有度优先
        matches.sort(key=lambda x: RARITY_RANK.get(x[1].get("rarity", "common"), 0), reverse=True)
        return matches[0]
    return None, None


async def run_fishing_gear_logic(event: AstrMessageEvent, store, parser, sender=None):
    """渔具管理命令逻辑.

    9/6: 改用 sender.send_card() 替代 try/except + yield image_result/plain_result 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    _, args = parser.parse(event)
    inventory = user.get("inventory", [])
    sub = (args[0] if args else "").strip()

    # 9/4: 把 equipped 提到顶部, 多个分支需要
    equipped = get_equipped_items(user)

    # === 无参数: 显示渔具状态 ===
    if not args:
        # equipped 已在外层定义
        # 9/3晚: 看 6 个渔具栏位 (鱼竿/鱼线/鱼钩/浮漂/鱼饵/鱼轮)
        gear_slots = ["fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_bait", "fishing_reel"]
        lines = ["━━━━━━━━━━━━━━", "【 🎣 渔 具 】", "━━━━━━━━━━━━"]

        # 构建 gear_slots 数据 (供 renderer 使用)
        gear_slot_data = []
        for slot in gear_slots:
            emoji = SLOT_EMOJI.get(slot, "📦")
            slot_name = SLOTS.get(slot, slot)
            # 9/4: hook 走 hook_slots 列表 (多钩), 其他走单槽
            if slot == "fishing_hook":
                hook_slots = equipped.get("hook_slots", [])
                if not isinstance(hook_slots, list) or not hook_slots:
                    lines.append(f"{emoji}{slot_name}: 空 (鱼竿钩数 0)")
                    gear_slot_data.append({
                        "emoji": emoji,
                        "name": slot_name,
                        "item_id": "",
                        "effect": "",
                    })
                    continue
                # 显示所有鱼钩
                hook_names = []
                hook_effects = []
                for hs in hook_slots:
                    if not hs:
                        continue
                    hid = hs.get("id", "")
                    hdef = ITEMS.get(hid, {})
                    # 9/4晚: 显示带稀有度前缀
                    hook_names.append(_format_item_name(hs))
                    he = hs.get("effects", {})
                    hook_effects.append(_summarize_effects("fishing_hook", he))
                lines.append(f"{emoji}{slot_name}: {' + '.join(hook_names)} (×{len(hook_names)})")
                if hook_effects:
                    lines.append(f"   └ {' / '.join(e for e in hook_effects if e)}")
                gear_slot_data.append({
                    "emoji": emoji,
                    "name": slot_name,
                    "item_id": f"{len(hook_names)}个: {' + '.join(hook_names)}",
                    "effect": " / ".join(e for e in hook_effects if e),
                })
                continue
            # 9/7: 鱼饵同样走 bait_slots 列表 (多饵), 修复"卸下鱼饵后渔具还显示鱼饵" bug
            if slot == "fishing_bait":
                bait_slots = equipped.get("bait_slots", [])
                if not isinstance(bait_slots, list) or not bait_slots:
                    lines.append(f"{emoji}{slot_name}: 空")
                    gear_slot_data.append({
                        "emoji": emoji,
                        "name": slot_name,
                        "item_id": "",
                        "effect": "",
                    })
                    continue
                # 显示所有鱼饵 (9/7: 加上数量显示, 消耗性显示剩余数)
                bait_names = []
                bait_effects = []
                for bs in bait_slots:
                    if not bs:
                        continue
                    bid = bs.get("id", "")
                    qty = bs.get("quantity")
                    is_consumable = bs.get("consumable", False)
                    name_with_qty = _format_item_name(bs)
                    if is_consumable and qty is not None and qty > 0:
                        name_with_qty += f" (×{qty})"
                    bait_names.append(name_with_qty)
                    be = bs.get("effects", {})
                    bait_effects.append(_summarize_effects("fishing_bait", be))
                lines.append(f"{emoji}{slot_name}: {' + '.join(bait_names)} (×{len(bait_names)})")
                if bait_effects:
                    lines.append(f"   └ {' / '.join(e for e in bait_effects if e)}")
                gear_slot_data.append({
                    "emoji": emoji,
                    "name": slot_name,
                    "item_id": f"{len(bait_names)}个: {' + '.join(bait_names)}",
                    "effect": " / ".join(e for e in bait_effects if e),
                })
                continue
            item = equipped.get(slot)
            if item:
                item_id = item.get("id", "")
                item_def = ITEMS.get(item_id, {})
                # 9/4晚: rarity 优先从 entry 读 (附魔后 entry 有新 rarity)
                rarity = item.get("rarity", item_def.get("rarity", "common"))
                color = RARITY_COLORS.get(rarity, "⚪")
                # 简略效果描述
                eff = item.get("effects", {})
                eff_summary = _summarize_effects(slot, eff)
                # 9/4晚: 显示带稀有度前缀的物品名
                display_name = _format_item_name(item)
                # 9/6: 描述 (附魔后 entry 的 description 优先, 缺则用 item_def)
                desc_text = item.get("description") or item_def.get("description", "")
                lines.append(f"{emoji}{slot_name}: {color}{display_name}")
                if eff_summary:
                    lines.append(f"   └ {eff_summary}")
                if desc_text:
                    lines.append(f"   📖 {desc_text}")
                gear_slot_data.append({
                    "emoji": emoji,
                    "name": slot_name,
                    "item_id": display_name,
                    "effect": eff_summary,
                    "desc": desc_text,
                })
            else:
                lines.append(f"{emoji}{slot_name}: 空")
                gear_slot_data.append({
                    "emoji": emoji,
                    "name": slot_name,
                    "item_id": "",
                    "effect": "",
                    "desc": "",
                })

        # 套装效果聚合
        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 套装综合效果 】")
        effects = _calc_gear_effects(user)
        if effects:
            lines.append(format_item_effects(effects))
        else:
            lines.append("无")

        # 9/4凌晨: 承载力 + 鱼钩 size_class 权重 + 食性
        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 🎯 承载与断线 】")
        capacity = _calc_gear_capacity(user)
        size_zh = {"micro": "微型", "small": "小型", "medium": "中型", "large": "大型", "shark": "鲨鱼级", "whale": "鲸级", "monster": "巨物"}
        diet_zh = {"carnivore": "肉食", "herbivore": "素食", "omnivore": "杂食"}
        lines.append(f"杆承重: {capacity['fishing_rod']}kg (超过断竿)")
        lines.append(f"线承重: {capacity['fishing_line']}kg (超过断线)")
        if capacity['size_weights']:
            weights_str = " ".join(f"{size_zh.get(s, s)}{int(p*100)}%" for s, p in capacity['size_weights'].items())
            lines.append(f"鱼钩尺寸权重: {weights_str}")
        else:
            lines.append("鱼钩尺寸: 无限制")
        if capacity['target_diet']:
            diet_str = "/".join(str(diet_zh.get(d) or d) for d in capacity['target_diet'])
            lines.append(f"鱼钩食性: {diet_str}")
        lines.append("━━━━━━━━━━━━")
        lines.append(f"鱼重超过杆承重会断竿, 超过线承重会断线")

        # 背包可用渔具
        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 背包可装备 】")
        # 9/4: 用 slot 字段代替不一致的 subcategory
        # 9/7 命名统一: 全部加 fishing_ 前缀
        gear_slots_set = {"fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_bait", "fishing_reel", "fishing_lure"}
        found = []
        inv_gear_data = []
        for i, item in enumerate(inventory, 1):
            item_id = item.get("id", "")
            item_def = ITEMS.get(item_id, {})
            if item_def.get("slot") in gear_slots_set:
                # 9/4晚: rarity 优先从 entry 读 (附魔后 entry 有新 rarity)
                rarity = item.get("rarity", item_def.get("rarity", "common"))
                color = RARITY_COLORS.get(rarity, "⚪")
                slot_name = SLOTS.get(item_def.get("slot", ""), "?")
                display_name = _format_item_name(item)
                # 9/6: 描述 (entry 优先)
                desc_text = item.get("description") or item_def.get("description", "")
                found.append((i, item_id, color, slot_name, display_name, desc_text))
                # 收集 renderer 数据
                # 9/7 命名统一: 全部加 fishing_ 前缀
                ITEM_EMOJI = {"fishing_rod": "🎣", "fishing_line": "🪢", "fishing_hook": "🪝", "fishing_float": "🎈", "fishing_bait": "🪱", "fishing_reel": "🎡", "fishing_lure": "🎏"}
                inv_gear_data.append({
                    "emoji": ITEM_EMOJI.get(item_def.get("slot", ""), "📦"),
                    "name": display_name,
                    "slot_zh": slot_name,
                    "idx": str(i),
                    "desc": desc_text,
                })
        if found:
            for idx, item_id, color, slot_name, display_name, desc_text in found:
                line = f"{idx}. {color}{display_name} [{slot_name}]"
                if desc_text:
                    line += f"\n     📖 {desc_text}"
                lines.append(line)
        else:
            lines.append("(背包内没有渔具)")

        lines.append("━━━━━━━━━━━━━━")
        lines.append("【 指令说明 】")
        lines.append("/渔具 装 <名字/序号> - 装备")
        lines.append("/渔具 卸 <栏位> - 卸下")
        lines.append("例: /渔具 装 竹竿  或  /渔具 卸 鱼竿")

        # 9/6: 改用 sender.send_card() (CardType.FISHING_GEAR 渲染模板 + view_for_fishing_gear_card)
        from ..data.user_view import view_for_fishing_gear_card
        diet_zh_map = {"carnivore": "肉食", "herbivore": "素食", "omnivore": "杂食"}
        diet_zh = "/".join(diet_zh_map.get(d, str(d)) for d in capacity.get('target_diet', []) if d) or "不限"
        data = view_for_fishing_gear_card(user, capacity=capacity, diet_zh=diet_zh)
        # 9/6 v9.5: caller 已构造 gear_slot_data (lines 104-169), 覆盖 view 默认的空 list
        data["gear_slots"] = gear_slot_data
        data["inventory_gear"] = inv_gear_data
        data["inventory_gear_count"] = len(inv_gear_data)
        data["effects"] = effects
        # 9/7: 整数显示字段
        data["effects"]["fishing_bonus_pct_int"] = int(effects.get("fishing_bonus_pct", 0))
        data["effects"]["rare_bonus_pct_int"] = int(effects.get("rare_bonus_pct", 0))
        async for r in sender.send_card(
            event, "fishing_gear", data, fallback_text="\n".join(lines),
        ):
            yield r
        return

    # === 卸下 ===
    if sub in ("卸", "卸下", "unequip"):
        if len(args) < 2:
            yield event.plain_result("📋 格式: /渔具 卸 <栏位或物品名>\n例: /渔具 卸 鱼竿  或  /渔具 卸 海夕  或  /渔具 卸 传说海夕")
            return
        target = args[1]
        # 9/4: 先按物品名匹配 (查 equipped 全部槽), 再按栏位名
        target_slot = None
        target_hook_index = None  # 多钩时定位具体槽
        target_bait_index = None  # 多饵时定位具体槽
        # 检查是否在 hook_slots 列表里 (按 ID 或 显示名)
        hook_slots = equipped.get("hook_slots", [])
        for i, hs in enumerate(hook_slots):
            if not hs:
                continue
            if hs.get("id") == target or hs.get("name") == target or _format_item_name(hs) == target:
                target_slot = "fishing_hook"
                target_hook_index = i
                break
        # 检查是否在 bait_slots 列表里 (按 ID 或 显示名)
        bait_slots = equipped.get("bait_slots", [])
        if not target_slot:
            for i, bs in enumerate(bait_slots):
                if not bs:
                    continue
                if bs.get("id") == target or bs.get("name") == target or _format_item_name(bs) == target:
                    target_slot = "fishing_bait"
                    target_bait_index = i
                    break
        # 检查单槽装备
        if not target_slot:
            for slot_key, slot_data in equipped.items():
                if not isinstance(slot_data, dict) or not slot_data:
                    continue
                if slot_data.get("id") == target or slot_data.get("name") == target:
                    target_slot = slot_key
                    break
        # 否则按栏位名解析
        if not target_slot:
            slot = FISHING_GEAR_SLOTS.get(target, target)
            if slot and slot in FISHING_GEAR_SLOTS.values():
                target_slot = slot
        if not target_slot:
            yield event.plain_result(f"📋 没找到: {target}\n栏位: 鱼竿/鱼线/鱼钩/浮漂/鱼饵/鱼轮\n或输入已装备物品名")
            return
        # 多钩槽特殊处理: 从 hook_slots 移除并加背包
        if target_slot == "fishing_hook" and target_hook_index is not None:
            removed = hook_slots.pop(target_hook_index)
            equipped["hook_slots"] = hook_slots
            user["equipped_items"] = equipped
            inventory.append({
                "id": removed.get("id"),
                "name": removed.get("name"),
            })
            user["inventory"] = inventory
            await store.update_user(user_id, user)
            yield event.plain_result(f"✅ 已卸下 {removed.get('name', removed.get('id'))}")
            return
        # 9/4晚: 多饵槽特殊处理 - 拟饵/消耗饵都从 bait_slots 移除
        if target_slot == "fishing_bait" and target_bait_index is not None:
            removed = bait_slots.pop(target_bait_index)
            equipped["bait_slots"] = bait_slots
            user["equipped_items"] = equipped
            # 拟饵: 卸下回到背包 (quantity=null, 视为无限)
            # 消耗饵: 如果还有剩余 quantity, 退回背包
            if removed.get("consumable") and removed.get("quantity"):
                # 有剩余消耗饵 → 退回背包
                add_to_inventory(user, removed.get("id"), removed["quantity"])
            else:
                # 拟饵 (不消耗) 或消耗饵用光 → 加 1 个 entry
                # 9/4晚: 保留 rarity/rarity_mult (附魔后的拟饵)
                inventory.append({
                    "id": removed.get("id"),
                    "name": removed.get("name"),
                    "category": removed.get("category") or ITEMS.get(removed.get("id"), {}).get("category"),
                    "type": removed.get("type") or ITEMS.get(removed.get("id"), {}).get("type"),
                    "slot": removed.get("slot") or ITEMS.get(removed.get("id"), {}).get("slot"),
                    "consumable": removed.get("consumable", False),
                    "rarity": removed.get("rarity", "common"),
                    "rarity_mult": removed.get("rarity_mult", 1.0),
                })
            user["inventory"] = inventory
            await store.update_user(user_id, user)
            # 9/4晚: 显示带稀有度前缀的物品名
            display_name = _format_item_name(removed)
            yield event.plain_result(f"✅ 已卸下 {display_name}")
            return
        # 9/4晚: 多饵槽按栏位名卸下 - bait_slots 卸所有饵料 (消耗饵保留剩余 quantity)
        if target_slot == "fishing_bait":
            bait_slots_list = equipped.get("bait_slots", [])
            if not bait_slots_list:
                yield event.plain_result("⚠️ 该栏位没有装备")
                return
            removed_names = []
            for removed in bait_slots_list:
                if removed.get("consumable") and removed.get("quantity"):
                    add_to_inventory(user, removed.get("id"), removed["quantity"])
                else:
                    # 9/4晚: 保留 rarity/rarity_mult (附魔后的拟饵)
                    inventory.append({
                        "id": removed.get("id"),
                        "name": removed.get("name"),
                        "category": removed.get("category") or ITEMS.get(removed.get("id"), {}).get("category"),
                        "type": removed.get("type") or ITEMS.get(removed.get("id"), {}).get("type"),
                        "slot": removed.get("slot") or ITEMS.get(removed.get("id"), {}).get("slot"),
                        "consumable": removed.get("consumable", False),
                        "rarity": removed.get("rarity", "common"),
                        "rarity_mult": removed.get("rarity_mult", 1.0),
                    })
                # 9/4晚: 显示带稀有度前缀的物品名
                removed_names.append(_format_item_name(removed))
            equipped["bait_slots"] = []
            user["equipped_items"] = equipped
            user["inventory"] = inventory
            await store.update_user(user_id, user)
            yield event.plain_result(f"✅ 已卸下 {', '.join(removed_names)}")
            return
        # 单槽卸下
        success, msg = unequip_item(user, target_slot)
        if success:
            await store.update_user(user_id, user)
            yield event.plain_result(f"✅ {msg}")
        else:
            yield event.plain_result(f"⚠️ {msg}")
        return

    # === 装备 ===
    if sub in ("装", "装备", "wear", "equip"):
        if len(args) < 2:
            yield event.plain_result("📋 格式: /渔具 装 <名字/序号>\n例: /渔具 装 竹竿  或  /渔具 装 传说竹竿")
            return
        target = args[1]
        # 9/4晚: 用 _resolve_inventory_target 支持序号/ID/原始名/显示名
        idx, inv_item = _resolve_inventory_target(inventory, target)
        if inv_item is None:
            yield event.plain_result(f"📋 背包中没有: {target}")
            return
        item_id = inv_item.get("id", "")
        # 检查是否是渔具 (slot 字段更可靠, subcategory 命名不一致: 鱼线用 line / 鱼竿用 fishing_rod)
        slot_check = ITEMS.get(item_id, {}).get("slot", "")
        if slot_check not in {"fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_bait", "fishing_reel"}:
            yield event.plain_result(f"⚠️ {item_id} 不是渔具, 请用 /装备 命令")
            return
        success, msg, item_info = equip_item(user, item_id)
        if success:
            await store.update_user(user_id, user)
            # 9/4晚: 显示带稀有度前缀的物品名
            display_name = _format_item_name(item_info) if isinstance(item_info, dict) else item_id
            eff = item_info.get("effects", {}) if isinstance(item_info, dict) else {}
            eff_summary = _summarize_effects(item_info.get("slot", ""), eff) if isinstance(item_info, dict) else ""
            yield event.plain_result(f"✅ {msg}\n装备: {display_name}\n效果: {eff_summary or '无'}")
        else:
            yield event.plain_result(f"⚠️ {msg}")
        return

    # 未知子命令
    yield event.plain_result(
        "📋 渔具命令用法:\n"
        "/渔具           - 查看渔具状态\n"
        "/渔具 装 <名字>  - 装备\n"
        "/渔具 卸 <栏位>  - 卸下\n"
        "例: /渔具 装 竹竿"
    )


def _summarize_effects(slot: str, effects: dict) -> str:
    """简化渔具效果描述"""
    if not effects:
        return ""
    if slot == "fishing_rod":
        # 鱼竿: 基础中鱼率提升
        parts = []
        if effects.get("fishing_bonus"):
            parts.append(f"中鱼率+{effects['fishing_bonus']*100:.0f}%")
        if effects.get("rare_bonus"):
            parts.append(f"稀有+{effects['rare_bonus']*100:.0f}%")
        if effects.get("min_size_bonus"):
            parts.append(f"尺寸+{effects['min_size_bonus']*100:.0f}%")
        if effects.get("duration_reduce"):
            parts.append(f"时间-{effects['duration_reduce']}tick")
        return " / ".join(parts) if parts else ""
    if slot == "fishing_line":
        # 鱼线: 提升上鱼最大重量 (min_size_bonus) + 承受力
        parts = []
        if effects.get("min_size_bonus"):
            parts.append(f"上鱼重量+{effects['min_size_bonus']*100:.0f}%")
        if effects.get("break_strength"):
            parts.append(f"承受{effects['break_strength']}kg")
        return " / ".join(parts) if parts else ""
    if slot == "fishing_hook":
        # 鱼钩: 限制上鱼种类 + 提升某些种类概率
        parts = []
        if effects.get("rare_bonus"):
            parts.append(f"稀有+{effects['rare_bonus']*100:.0f}%")
        if effects.get("min_size_bonus") and effects["min_size_bonus"] >= 0:
            parts.append(f"尺寸+{effects['min_size_bonus']*100:.0f}%")
        elif effects.get("min_size_bonus"):
            parts.append(f"尺寸{effects['min_size_bonus']*100:.0f}%")
        return " / ".join(parts) if parts else ""
    if slot == "fishing_float":
        # 浮漂: 基础概率提高尺寸
        parts = []
        if effects.get("fishing_bonus"):
            parts.append(f"中鱼+{effects['fishing_bonus']*100:.0f}%")
        if effects.get("sensitivity"):
            parts.append(f"灵敏度{effects['sensitivity']}")
        if effects.get("night_vision"):
            parts.append("夜视")
        if effects.get("auto_detect"):
            parts.append("自探测")
        return " / ".join(parts) if parts else ""
    if slot == "fishing_bait":
        # 鱼饵: 调整上鱼种类池
        parts = []
        if effects.get("rare_bonus"):
            parts.append(f"稀有+{effects['rare_bonus']*100:.0f}%")
        habitat_filter = effects.get("habitat_filter", [])
        if habitat_filter:
            parts.append(f"水域:{'/'.join(habitat_filter)}")
        fish_bonus = effects.get("fish_bonus", {})
        if fish_bonus:
            top_fish = sorted(fish_bonus.items(), key=lambda x: -x[1])[:2]
            parts.append("加成:" + ",".join(f"{f}+{int(p*100)}%" for f, p in top_fish))
        return " / ".join(parts) if parts else ""
    if slot == "fishing_reel":
        # 鱼轮: 钓鱼经验加成 + 缩短时长 + 稀有率 + 自动收竿
        parts = []
        # 9/4晚: 适配 _pct 后缀 (pct 直接显示百分比)
        exp_bonus_pct = effects.get("exp_bonus_pct", 0)
        if exp_bonus_pct:
            parts.append(f"经验+{exp_bonus_pct:.0f}%")
        elif effects.get("exp_bonus"):
            parts.append(f"经验+{effects['exp_bonus']*100:.0f}%")
        if effects.get("duration_reduce"):
            parts.append(f"时间-{effects['duration_reduce']}tick")
        if effects.get("rare_bonus"):
            parts.append(f"稀有+{effects['rare_bonus']*100:.0f}%")
        if effects.get("auto_reel"):
            parts.append("自动收竿")
        return " / ".join(parts) if parts else ""
    return ""


def _calc_gear_effects(user: dict) -> dict:
    """聚合渔具 6 槽位 effects, 返回给 roll_catch 用"""
    equipped = get_equipped_items(user)
    # 9/3晚: 加 reel 槽
    gear_slots = ["fishing_rod", "fishing_line", "fishing_hook", "fishing_float", "fishing_bait", "fishing_reel"]
    merged = {}
    for slot in gear_slots:
        item = equipped.get(slot)
        if not item:
            continue
        eff = item.get("effects", {})
        for k, v in eff.items():
            if isinstance(v, (int, float)):
                merged[k] = merged.get(k, 0) + v
            elif k == "habitat_filter" or k == "fish_bonus":
                # 鱼钩/鱼饵特殊字段, 直接覆盖 (取鱼饵的 filter 优先, 因为鱼钩一般没 filter)
                merged[k] = v
            else:
                merged[k] = v
    return merged


def _calc_gear_capacity(user: dict) -> dict:
    """9/6: 计算渔具承载范围 (kg) + 鱼钩圈定的桶

    承载公式 (9/6 重设): 鱼竿 load_capacity_max 和 鱼线 load_capacity_max 独立计算
              不再累加. 鱼重超过任一承载 → 独立判定断竿/断线
    鱼竿断竿: 鱼重 > 竿载 → 按超载%概率断竿 (损坏装备)
    鱼线断线: 鱼重 > 线载 → 按超载%概率断线 (失鱼)
    通用断线/断竿概率 (9/6 重设):
      超载 0-10% → 30% 概率断
      超载 10-20% → 60% 概率断
      超载 20-30% → 90% 概率断
      超载 >30% → 100% 概率断
    判定顺序: 先断线 → 线断了则不判定断竿
    默认值 (无装备): 竹竿 2kg + 棉线 1kg
    """
    equipped = get_equipped_items(user)
    # 鱼竿 load (默认竹竿 2kg)
    rod_item = equipped.get("fishing_rod", {})
    rod_eff = rod_item.get("effects", {}) if rod_item else {}
    rod_load = rod_eff.get("load_capacity_max", 2)
    # 鱼线 load (默认棉线 1kg)
    line_item = equipped.get("fishing_line", {})
    line_eff = line_item.get("effects", {}) if line_item else {}
    line_load = line_eff.get("load_capacity_max", 1)
    # 鱼钩 target_size_weights + target_diet (9/4: size_class 权重抽样)
    hook_item = equipped.get("fishing_hook", {})
    hook_eff = hook_item.get("effects", {}) if hook_item else {}
    size_weights = hook_eff.get("target_size_weights", {})
    target_diet = hook_eff.get("target_diet", [])

    return {
        "fishing_rod": rod_load,
        "fishing_line": line_load,
        "size_weights": size_weights,
        "target_diet": target_diet,
    }