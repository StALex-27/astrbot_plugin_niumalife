"""
钓鱼命令逻辑：/钓鱼 /钓鱼 取消 /鱼塘

注意：没有 /钓鱼 收 —— 中鱼由 tick 系统自动通知用户。
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_FISHING
from ...modules.constants import ITEMS
# 9/6: 用于精确构造 session_key (Pattern 10: 通知跟随发起会话)
# 2 点 = 父包 src 同级, src/commands -> src/ui/message_sender
from ..ui.message_sender import _extract_session_key
from ...src.fishing import fishing_manager as _fm
_fm._ensure_loaded()
FISHING_SPOTS = _fm.FISHING_SPOTS
from ...src.fishing.fishing_manager import get_spot, format_weight, get_fishing_skill_level  # 9/8: 紧凑重量格式 + 解锁等级检查
from ..data.user_view import get_fish_caught, get_biggest_catch, get_fish_title


LOCAL_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)


def _resolve_rod(user: dict) -> tuple[str, dict]:
    """从 equipped_items 拿鱼竿 ID 和 effects (含附魔词条)。无鱼竿返回 ('竹竿', default_effects)。"""
    equipped = user.get("equipped_items", {})
    rod_entry = equipped.get("fishing_rod")
    if isinstance(rod_entry, dict) and rod_entry.get("id"):
        # 9/5: 用装备 entry 的 effects (含 rarity_mult 词条)
        return rod_entry.get("id", "竹竿"), rod_entry.get("effects", {})
    rod_id = "竹竿"
    rod = ITEMS.get(rod_id, {})
    return rod_id, rod.get("effects", {})


def _resolve_bait(user: dict) -> tuple[str, dict]:
    """兼容旧接口: 返回第一个饵 (bait_slots[0] 或 inventory 第一个 bait)"""
    slots = _resolve_bait_slots(user)
    if slots:
        return slots[0]
    return "空手", {}


def _resolve_bait_slots(user: dict) -> list[tuple[str, dict]]:
    """9/4晚: 多槽饵料解析 - 返回 [(bait_id, effects), ...] 列表

    优先读 equipped_items["bait_slots"] (列表), 兼容旧 "bait" (单)
    """
    equipped = user.get("equipped_items", {})
    # 9/4: 新结构 bait_slots (list)
    if isinstance(equipped.get("bait_slots"), list):
        slots = []
        for slot in equipped["bait_slots"]:
            if isinstance(slot, dict):
                bid = slot.get("id", "")
                if bid:
                    slots.append((bid, slot.get("effects", {})))
        if slots:
            return slots
    # 兼容旧: "fishing_bait" 单字段 (9/7 加前缀)
    legacy = equipped.get("fishing_bait", {})
    if isinstance(legacy, dict) and legacy.get("id"):
        bid = legacy["id"]
        return [(bid, ITEMS.get(bid, {}).get("effects", {}))]
    # 兜底: inventory 第一个 fishing_bait/fishing_lure subcategory
    for it in user.get("inventory", []):
        item_id = it.get("id") if isinstance(it, dict) else None
        if not item_id:
            continue
        info = ITEMS.get(item_id, {})
        if info.get("subcategory") in ("fishing_bait", "fishing_lure"):
            return [(item_id, info.get("effects", {}))]
    return []


def _resolve_hook_slots(user: dict) -> list[tuple[str, dict]]:
    """9/4晚: 多槽鱼钩解析 - 返回 [(hook_id, effects), ...] 列表

    优先读 equipped_items["hook_slots"] (列表), 兼容旧 "hook" (单)
    """
    equipped = user.get("equipped_items", {})
    if isinstance(equipped.get("hook_slots"), list):
        slots = []
        for slot in equipped["hook_slots"]:
            if isinstance(slot, dict):
                hid = slot.get("id", "")
                if hid:
                    slots.append((hid, slot.get("effects", {})))
        if slots:
            return slots
    # 兼容旧: "fishing_hook" 单字段 (9/7 加前缀)
    legacy = equipped.get("fishing_hook", {})
    if isinstance(legacy, dict) and legacy.get("id"):
        hid = legacy["id"]
        return [(hid, ITEMS.get(hid, {}).get("effects", {}))]
    return []


# 9/7: 老 slot 名兼容 (line/hook/float/reel/bait/lure/waders → fishing_*)
_LEGACY_SLOT_ALIAS = {
    "line": "fishing_line",
    "hook": "fishing_hook",
    "float": "fishing_float",
    "reel": "fishing_reel",
    "bait": "fishing_bait",
    "lure": "fishing_lure",
    "waders": "fishing_waders",
}


def _resolve_gear_slot(user: dict, slot: str) -> tuple[str, dict]:
    """9/3: 解析渔具任意槽位. 未装备返回 ('', {}).

    9/7: 兼容老 slot 名 (line/hook 等 → fishing_line/fishing_hook)
    """
    equipped = user.get("equipped_items", {})
    slot_entry = equipped.get(slot, {})
    if not slot_entry:
        # 试兼容老 slot 名
        legacy_key = _LEGACY_SLOT_ALIAS.get(slot)
        if legacy_key:
            slot_entry = equipped.get(legacy_key, {})
    if not isinstance(slot_entry, dict) or not slot_entry.get("id"):
        return "", {}
    # 9/5: 优先用装备 entry 的 effects (含附魔词条)
    item_id = slot_entry.get("id", "")
    effects = slot_entry.get("effects") or ITEMS.get(item_id, {}).get("effects", {})
    return item_id, effects


async def run_fishing_show_spots_logic(user, sender=None, event=None):
    """显示钓鱼主页 (9/8 重构: 6 渔具栏 + 风险提示 + 钓鱼状态 + 两列水域)

    9/6: 改用 sender.send_card() 替代内部 try/except + renderer.render_fishing_spots(...) 调用。
    现在构造完整 data dict 传给 sender, sender 内部调 renderer._render(CardType.FISHING_SPOTS, data)。
    9/8: 加 6 渔具栏 + 断线断竿风险 + 必备装备缺失警告 + 钓鱼状态 + 两列水域
    """
    # 9/8: 钓鱼中检查
    is_fishing = user.get("status") == UserStatus.FISHING
    action = user.get("action_detail", {}) if is_fishing else {}

    from ...src.fishing.fishing_manager import get_fishing_skill_level, get_fishing_skill_progress, calc_break_risk_from_hook
    skill_lvl = get_fishing_skill_level(user)
    skill_progress = get_fishing_skill_progress(user)  # 9/8: 经验/升级进度
    gold = user.get("gold", 0)

    # 9/8: 6 渔具解析 (按 6 栏: 竿/线/轮/漂/钩/饵)
    gear_slots = []
    gear_defs = [
        ("fishing_rod", "🎣 鱼竿", True),    # 必备
        ("fishing_line", "🪢 鱼线", True),   # 必备
        ("fishing_reel", "🎡 鱼轮", False),
        ("fishing_float", "🪩 浮漂", False),
        ("fishing_hook", "🪝 鱼钩", True),   # 必备
        ("fishing_bait", "🪱 鱼饵", False),  # 饵可选
    ]
    equipped = user.get("equipped_items", {})
    # 钩/饵特殊: list 容器
    hook_slots = _resolve_hook_slots(user)
    bait_slots = _resolve_bait_slots(user)

    # 钩 (取第一个)
    if hook_slots:
        hook_id, hook_eff = hook_slots[0]
    else:
        hook_id, hook_eff = "无", {}

    # 饵 (取第一个)
    if bait_slots:
        bait_id, bait_eff = bait_slots[0]
    else:
        bait_id, bait_eff = "无", {}

    for slot_key, slot_label, required in gear_defs:
        if slot_key == "fishing_hook":
            slot_id, slot_eff = hook_id, hook_eff
        elif slot_key == "fishing_bait":
            slot_id, slot_eff = bait_id, bait_eff
        else:
            slot_entry = equipped.get(slot_key, {})
            if not isinstance(slot_entry, dict) or not slot_entry.get("id"):
                # 兼容老 slot
                legacy_key = _LEGACY_SLOT_ALIAS.get(slot_key.replace("fishing_", ""))
                if legacy_key:
                    slot_entry = equipped.get(legacy_key, {})
            if isinstance(slot_entry, dict) and slot_entry.get("id"):
                slot_id = slot_entry["id"]
                slot_eff = slot_entry.get("effects", {}) or ITEMS.get(slot_id, {}).get("effects", {})
            else:
                slot_id, slot_eff = ("无" if not required else "缺"), {}

        # 风险提示
        load_max = slot_eff.get("load_capacity_max", 0)
        risk_note = ""
        if load_max > 0:
            if load_max >= 100:
                risk_note = f"承重 {load_max}kg"
            elif load_max >= 50:
                risk_note = f"承重 {load_max}kg 中"
            else:
                risk_note = f"承重 {load_max}kg 易断"
        elif slot_key == "fishing_bait":
            risk_note = "无"

        gear_slots.append({
            "label": slot_label,
            "name": slot_id,
            "required": required,
            "risk": risk_note,
            "missing": not slot_id or slot_id in ("无", "缺", "空手"),
        })

    # 9/8: 缺失必备装备警告
    missing_required = [g["label"] for g in gear_slots if g["required"] and g["missing"]]

    # 9/8: 断竿断线风险 (按鱼钩 size_class 范围算)
    rod_eff = equipped.get("fishing_rod", {}).get("effects", {}) if isinstance(equipped.get("fishing_rod"), dict) else {}
    line_eff = equipped.get("fishing_line", {}).get("effects", {}) if isinstance(equipped.get("fishing_line"), dict) else {}
    rod_max = rod_eff.get("load_capacity_max", 2)
    line_max = line_eff.get("load_capacity_max", 1)
    risk_info = calc_break_risk_from_hook(hook_eff, rod_max, line_max)
    break_risk = risk_info["level"]
    hook_max_kg = risk_info["hook_max_kg"]
    risk_reason = risk_info["reason"]

    # 钓鱼状态信息
    fishing_status = None
    if is_fishing and action:
        from ...modules.tick import TICK_TYPE_FISHING
        spot_id = action.get("spot_id", "")
        spot_name = FISHING_SPOTS.get(spot_id, {}).get("name", spot_id)
        start_ts = action.get("start_ts", "")
        ticks_done = action.get("ticks_done", 0)
        max_ticks = action.get("max_ticks", 30)
        fishing_status = {
            "spot_name": spot_name,
            "spot_emoji": FISHING_SPOTS.get(spot_id, {}).get("emoji", "🎣"),
            "ticks_done": ticks_done,
            "max_ticks": max_ticks,
            "progress_pct": int(ticks_done / max_ticks * 100) if max_ticks else 0,
        }

    # 构建水域数据
    spots_data = []
    for sid, spot in FISHING_SPOTS.items():
        if spot.get("unlock_level", 1) > skill_lvl:
            lock = f" 🔒 需要 Lv.{spot.get('unlock_level', 1)}"
            locked = True
        else:
            lock = ""
            locked = False
        fee = spot.get("license_fee", 0)
        base_rate = int(spot.get("success_rate", 0)*100)
        spots_data.append({
            "emoji": spot.get("emoji", "🪣"),
            "name": spot.get("name", sid),
            "desc": spot.get("desc", ""),
            "base_rate": base_rate,
            "fee": fee,
            "locked": locked,
            "unlock_level": spot.get("unlock_level", 1),
        })

    # 9/8: 钓鱼称号
    fish_title = user.get("fishing", {}).get("fish_title", "") or ""

    # 纯文本降级版本
    if is_fishing:
        lines = ["═══════════════════════════", "    「 🎣 钓 鱼 中 」", "═══════════════════════════"]
    else:
        lines = ["═══════════════════════════", "    「 🎣 钓 鱼 」", "═══════════════════════════"]
    if is_fishing and fishing_status:
        lines.append(f"\n⏱️  正在: {fishing_status['spot_emoji']} {fishing_status['spot_name']}")
        lines.append(f"   进度: {fishing_status['ticks_done']}/{fishing_status['max_ticks']} ({fishing_status['progress_pct']}%)")
    # 9/8: 技能等级 (fallback 不显示 exp 数值, 与卡片一致)
    lines.append(f"\n📊 Lv.{skill_progress['level']}")
    if missing_required:
        lines.append(f"\n⚠️ 缺少必备: {', '.join(missing_required)}")
    elif break_risk != "无":
        lines.append(f"\n🔧 风险: {risk_reason}")
    lines.append("\n─────────── 渔 具 ───────────")
    for g in gear_slots:
        marker = "❗" if g["required"] and g["missing"] else "  "
        lines.append(f"{marker}{g['label']}: {g['name']} ({g['risk']})")
    lines.append("\n─────────── 水域列表 ───────────")
    for sid, spot in FISHING_SPOTS.items():
        fee_str = f"  ({spot.get('license_fee', 0)}金)" if spot.get("license_fee", 0) > 0 else ""
        lines.append(f"{spot.get('emoji', '🪣')}{spot.get('name', sid)}{fee_str} | {int(spot.get('success_rate', 0)*100)}%")
    lines.append("\n═══════════════════════════")
    lines.append("📝 /钓鱼 <水域名> 开始钓鱼")
    lines.append("📝 /钓鱼 取消 收竿")
    fallback_text = "\n".join(lines)

    # 9/6: 改用 sender.send_card()
    if sender and event:
        from ...modules.templates import CardType
        data = {
            "user_id": str(event.get_sender_id()),
            "nickname": user.get("nickname", "玩家"),
            "avatar_url": f"https://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=100&img_type=png",
            "skill_level": skill_lvl,
            "skill_progress": skill_progress,  # 9/8: 经验/升级
            "gold": gold,
            "gear_slots": gear_slots,
            "missing_required": missing_required,
            "break_risk": break_risk,
            "hook_max_kg": hook_max_kg,
            "risk_reason": risk_reason,
            "rod_max": rod_max,
            "line_max": line_max,
            "is_fishing": is_fishing,
            "fishing_status": fishing_status,
            "fish_title": fish_title,  # 9/8: 钓鱼称号
            "spots": spots_data,
        }
        async for r in sender.send_card(
            event, CardType.FISHING_SPOTS, data,
            fallback_text=fallback_text,
        ):
            yield r
    else:
        yield fallback_text


async def run_fishing_start_logic(
    user, spot_id: str, store, group_id: str = "", session_key: str = ""
) -> str:
    """开始钓鱼（设置 action_detail，让 tick 接管）。

    Args:
        session_key: 9/6 完整 session_key (platform|session_type|group:xxx)
            tick 推送通知时按此 key 查缓存 event, 不再 fallback 到 _infer_event。
            留空时回退到旧行为 (start_group_id=group_id)。
    """
    spot = get_spot(spot_id)
    if not spot:
        return f"❌ 未知水域：{spot_id}\n输入 /钓鱼 查看水域列表"

    # 9/8: 解锁等级检查 (按玩家钓鱼等级)
    skill_lvl = get_fishing_skill_level(user)
    spot_unlock = spot.get("unlock_level", 1)
    if spot_unlock > skill_lvl:
        return (
            f"🔒 钓鱼等级不足！\n"
            f"水域「{spot.get('name', spot_id)}」需要 Lv.{spot_unlock}，你当前 Lv.{skill_lvl}\n"
            f"💡 继续钓鱼积累经验提升等级"
        )

    # === 体力消耗（按水域 tier + 装备减免）===
    base_strength_cost = spot.get("strength_cost", 1)  # 池塘默认 1
    rod_id, rod_eff = _resolve_rod(user)
    # 9/4晚: 多槽鱼钩 + 多槽饵料
    hook_slots = _resolve_hook_slots(user)
    bait_slots = _resolve_bait_slots(user)
    hook_id = hook_slots[0][0] if hook_slots else ""
    hook_eff = hook_slots[0][1] if hook_slots else {}
    bait_id = bait_slots[0][0] if bait_slots else "空手"
    bait_eff = bait_slots[0][1] if bait_slots else {}
    # 9/3: 鱼线/鱼钩/浮漂/鱼轮都参与减免 (duration_reduce)
    line_id, line_eff = _resolve_gear_slot(user, "fishing_line")
    float_id, float_eff = _resolve_gear_slot(user, "fishing_float")
    reel_id, reel_eff = _resolve_gear_slot(user, "fishing_reel")
    # 鱼竿/鱼饵/鱼线/鱼钩/浮漂/鱼轮 的 duration_reduce 累加 (单位 tick 折成体力)
    strength_reduce = (rod_eff.get("duration_reduce", 0) + bait_eff.get("duration_reduce", 0) + line_eff.get("duration_reduce", 0) + hook_eff.get("duration_reduce", 0) + float_eff.get("duration_reduce", 0) + reel_eff.get("duration_reduce", 0)) * 0.1
    final_cost = max(0, int(base_strength_cost - strength_reduce))
    current_strength = user.get("attributes", {}).get("strength", 0)
    if current_strength < final_cost:
        return (
            f"❌ 体力不足！{spot_id} 需要 {final_cost} 体力，你只有 {current_strength}\n"
            f"提示: 吃东西 / 休息可恢复体力"
        )

    if spot.get("license_fee", 0) > 0:
        # 9/4: 检查付费通行证 (2小时内同水域免入场费)
        now_fee = datetime.now(LOCAL_TZ)
        pass_data = user.get("fishing_pass", {})
        if not isinstance(pass_data, dict):
            pass_data = {}
            user["fishing_pass"] = pass_data
        spot_pass_expire = pass_data.get(spot_id)
        fee_charged = False
        remaining_min = 0  # 9/4: 默认 0 用于消息显示
        if spot_pass_expire:
            try:
                expire_dt = datetime.fromisoformat(spot_pass_expire)
                if now_fee < expire_dt:
                    # 通行证有效, 免入场费
                    remaining = expire_dt - now_fee
                    remaining_min = int(remaining.total_seconds() // 60)
                    logger.info(f"[fishing_pass] 用户 {user.get('user_id', '?')} 通行证有效 ({spot_id}, 剩余 {remaining_min}min)")
                else:
                    # 通行证过期, 清除
                    del pass_data[spot_id]
                    # 需付费
                    if user.get("gold", 0) < spot["license_fee"]:
                        return (
                            f"❌ 金币不足，需要 {spot['license_fee']} 金币才能入场\n"
                            f"💡 付费后可 2 小时内免费重钓"
                        )
                    user["gold"] -= spot["license_fee"]
                    fee_charged = True
            except (ValueError, TypeError):
                del pass_data[spot_id]
        else:
            # 无通行证, 需付费
            if user.get("gold", 0) < spot["license_fee"]:
                return (
                    f"❌ 金币不足，需要 {spot['license_fee']} 金币才能入场\n"
                    f"💡 付费后可 2 小时内免费重钓"
                )
            user["gold"] -= spot["license_fee"]
            fee_charged = True
        if fee_charged:
            # 设置通行证 (now + 2h)
            pass_data[spot_id] = (now_fee + timedelta(hours=2)).isoformat()
            user["fishing_pass"] = pass_data
            remaining_min = 120  # 9/4: 刚开通通行证, 有效期 2h
            logger.info(f"[fishing_pass] 用户 {user.get('user_id', '?')} 购买通行证: {spot_id} until {pass_data[spot_id]}")

    duration = spot.get("duration_ticks", 60)
    reduce_ticks = (rod_eff.get("duration_reduce", 0) + bait_eff.get("duration_reduce", 0) +
                    line_eff.get("duration_reduce", 0) + hook_eff.get("duration_reduce", 0) +
                    float_eff.get("duration_reduce", 0) + reel_eff.get("duration_reduce", 0))
    actual_ticks = max(20, duration - reduce_ticks)

    now = datetime.now(LOCAL_TZ)

    # 扣体力
    user["attributes"]["strength"] = max(0, current_strength - final_cost)

    # 记录发起群（确保 tick 中鱼时能找到）
    groups = user.setdefault("groups", [])
    if group_id and group_id not in groups:
        groups.append(group_id)

    # 9/6: 完整 session_key 优先; 缺省时回退到 group_id (兼容旧数据)
    detail = ActionDetail.create(
        action_type=TICK_TYPE_FISHING,
        hours=actual_ticks // 60,
        start_time=now,
        spot_id=spot_id,
        spot_emoji=spot.get("emoji", "🪣"),
        rod_id=rod_id,
        # 9/4晚: 多槽鱼钩 + 多槽饵料
        hook_slots=[hid for hid, _ in hook_slots],
        bait_slots=[bid for bid, _ in bait_slots],
        hook_id=hook_id,  # 兼容旧 ActionDetail schema (第一个)
        bait_id=bait_id,  # 兼容旧
        # 9/3: 渔具其他槽
        line_id=line_id,
        float_id=float_id,
        # 9/3晚: 鱼轮 (钓鱼经验加成 + rare_bonus + duration_reduce)
        reel_id=reel_id,
        session_key=session_key,  # 9/6: 完整 session_key
        start_group_id=group_id if not session_key else "",  # 9/6: 旧字段保留作兼容
        strength_cost=final_cost,  # 钓鱼体力消耗
    )
    # create() 内部 planned_ticks = hours * 60，我们覆盖为实际 tick
    detail["planned_ticks"] = actual_ticks

    user["status"] = UserStatus.FISHING
    user["current_action"] = TICK_TYPE_FISHING
    user["action_detail"] = detail
    await store.update_user(str(user.get("user_id", "")), user)

    # 9/4: 通行证状态
    if spot.get("license_fee", 0) > 0:
        pass_data = user.get("fishing_pass", {})
        if isinstance(pass_data, dict) and spot_id in pass_data:
            pass_info = f"\n🎫 通行证有效 (剩余 {remaining_min} 分钟)，本场免入场费"
        else:
            pass_info = f"\n🎫 通行证已开通 (有效期 2 小时)"
    else:
        pass_info = ""

    return (
        f"🎣 开始在 {spot.get('emoji', '')} {spot_id} 钓鱼！\n\n"
        f"🎣 鱼竿: {rod_id}\n"
        f"🪱 鱼饵: {bait_id}\n"
        f"⏰ 最长等待: {actual_ticks} 分钟\n"
        f"🎯 基础成功率: {int(spot.get('success_rate', 0)*100)}%\n"
        f"💰 入场费: {spot.get('license_fee', 0)} 金币\n"
        f"💪 体力消耗: {final_cost}{pass_info}\n\n"
        f"中鱼会在群里 @ 你"
    )


async def run_fishing_cancel_logic(user, store) -> str:
    """取消钓鱼（无补偿，下次开始需重新付费）。"""
    if user.get("status") != UserStatus.FISHING:
        return "你并没有在钓鱼"

    user["status"] = UserStatus.FREE
    user["current_action"] = None
    user["action_detail"] = None
    await store.update_user(str(user.get("user_id", "")), user)
    return "🎣 收竿了。江湖再见，下次再战。"


async def run_fishing_logic(event: AstrMessageEvent, store, sender=None):
    """钓鱼命令入口：分发到 show_spots / start / cancel / status.

    9/6: 改用 sender (替代 renderer)。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    if not user:
        yield event.plain_result("📋 你还没注册！先 /签到")
        return

    parts = event.message_str.strip().split()
    cmd = parts[1] if len(parts) > 1 else None

    # 如果正在钓鱼中：
    # - 无参数 → 显示当前进度
    # - "取消" → 收竿
    # - 其他 → 拒绝（防止覆盖进行中的钓鱼）
    if user.get("status") == UserStatus.FISHING:
        if cmd is None:
            # 9/8: 改走渲染卡片 (show spots 主页), 失败时 fallback 进度文本
            async for r in run_fishing_show_spots_logic(user, sender=sender, event=event):
                yield r
        elif cmd == "取消":
            msg = await run_fishing_cancel_logic(user, store)
            yield event.plain_result(msg)
        else:
            yield event.plain_result(
                "🎣 你正在钓鱼中！\n"
                "📝 /钓鱼 查看当前进度\n"
                "📝 /钓鱼 取消 收竿"
            )
        event.stop_event()
        return

    # 空闲状态
    if cmd == "取消":
        yield event.plain_result("你并没有在钓鱼")
        event.stop_event()
        return

    if cmd is None:
        # 9/6: 改用 sender.send_card() 显示水域列表 (run_fishing_show_spots_logic 现在是 async generator)
        async for r in run_fishing_show_spots_logic(user, sender=sender, event=event):
            yield r
        event.stop_event()
        return

    # 开始钓鱼（记录发起群，tick 中鱼时只在原群 @ 用户）
    group_id = event.get_group_id() if not event.is_private_chat() else ""
    # 9/6: 拼完整 session_key 让 tick 能精确定位缓存 event
    session_key = _extract_session_key(event) or ""
    msg = await run_fishing_start_logic(user, cmd, store, group_id=group_id, session_key=session_key)
    yield event.plain_result(msg)
    event.stop_event()


async def _show_fishing_progress(user: dict) -> str:
    """显示当前钓鱼进度。"""
    detail = user.get("action_detail", {}) or {}
    data = detail.get("data", {})
    spot_id = data.get("spot_id", "未知水域")
    rod_id = data.get("rod_id", "竹竿")
    bait_id = data.get("bait_id", "空手")

    from datetime import datetime
    from ...src.fishing.fishing_manager import FISHING_SPOTS
    spot = FISHING_SPOTS.get(spot_id, {})
    spot_emoji = spot.get("emoji", "🪣")
    planned = detail.get("planned_ticks", 30)

    start_str = detail.get("start_time", "")
    try:
        start = datetime.fromisoformat(start_str)
        elapsed_ticks = int((datetime.now(LOCAL_TZ) - start).total_seconds() // 60)
    except (ValueError, TypeError):
        elapsed_ticks = 0
    remaining = max(0, planned - elapsed_ticks)
    pct = min(100, int(elapsed_ticks / planned * 100)) if planned > 0 else 0

    return (
        f"🎣 正在 {spot_emoji} {spot_id} 钓鱼中\n\n"
        f"🎣 鱼竿: {rod_id}    🪱 鱼饵: {bait_id}\n"
        f"⏰ 剩余: {remaining} 分钟 (已过 {elapsed_ticks}/{planned})\n"
        f"📊 进度: [{'█' * (pct//5)}{'░' * (20-pct//5)}] {pct}%\n\n"
        f"💡 中鱼会自动通知你\n"
        f"📝 /钓鱼 取消 收竿"
    )


async def run_fish_dex_logic(event: AstrMessageEvent, store, sender):
    """鱼塘图鉴.

    9/6: 改用 sender.send_card() (替代 try/except + yield image_result/plain_result 样板).
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    if not user:
        yield event.plain_result("📋 你还没注册！先 /签到")
        event.stop_event()
        return

    from ...src.fishing.fishing_manager import FISHES
    _fm._ensure_loaded()  # 确保 FISHES 已加载

    from ...modules.templates import CardType
    from ...data.user_view import view_for_fish_dex_card
    # 9/6: ViewSpec 应用 - 改用 view_for_fish_dex_card 拿齐 data
    data = view_for_fish_dex_card(user, FISHES)
    data["user_id"] = user_id  # sender 需要
    # fallback 文本沿用 view 返回的字段
    caught = data["fish_caught"]
    biggest = data["biggest_catch"]
    title = data["fish_title"]
    # 9/6: 改用 sender.send_card() + fallback_text 纯文本降级
    fallback_lines = [
        "═══════════════════════════",
        "  🎣 「 鱼 塘 图 鉴 」",
        "═══════════════════════════",
        f"\n📊 收集进度: {len(caught)}/{len(FISHES)}",
    ]
    for fname, info in FISHES.items():
        cnt = caught.get(fname, 0)
        mark = "✅" if cnt > 0 else "🔒"
        fallback_lines.append(f"  {mark} {info.get('emoji','🐟')} {fname} (x{cnt})")
    if biggest:
        weight_str = format_weight(biggest.get("weight", 0))  # 9/8: 紧凑格式
        fallback_lines.append(f"\n🏆 最大单条: {biggest.get('fish','')} {weight_str}")
    if title:
        fallback_lines.append(f"🏅 称号: {title}")
    async for r in sender.send_card(
        event, CardType.FISH_DEX, data,
        fallback_text="\n".join(fallback_lines),
    ):
        yield r
    event.stop_event()
