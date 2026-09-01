"""
钓鱼命令逻辑：/钓鱼 /钓鱼 取消 /鱼塘

注意：没有 /钓鱼 收 —— 中鱼由 tick 系统自动通知用户。
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus
from ...modules.tick import ActionDetail, TICK_TYPE_FISHING
from ...modules.constants import ITEMS
from ...src.fishing import fishing_manager as _fm
_fm._ensure_loaded()
FISHING_SPOTS = _fm.FISHING_SPOTS
from ...src.fishing.fishing_manager import get_spot


LOCAL_TZ = timezone(timedelta(hours=8))


def _resolve_rod(user: dict) -> tuple[str, dict]:
    """从 equipped_items 拿鱼竿 ID 和 effects。无鱼竿返回 ('竹竿', default_effects)。"""
    equipped = user.get("equipped_items", {})
    # 新槽位 fishing_rod，未装备时默认竹竿
    rod_id = equipped.get("fishing_rod", {}).get("id", "竹竿")
    rod = ITEMS.get(rod_id, {})
    return rod_id, rod.get("effects", {})


def _resolve_bait(user: dict) -> tuple[str, dict]:
    """从 inventory 拿第一个 fish_bait 类鱼饵。"""
    equipped = user.get("equipped_items", {})
    bait_id = equipped.get("bait", {}).get("id")
    if bait_id:
        return bait_id, ITEMS.get(bait_id, {}).get("effects", {})
    # 退而求其次：背包里找第一个 bait subcategory
    for it in user.get("inventory", []):
        item_id = it.get("id") if isinstance(it, dict) else None
        if not item_id:
            continue
        info = ITEMS.get(item_id, {})
        if info.get("subcategory") == "bait":
            return item_id, info.get("effects", {})
    # 默认虚拟"空手"（不消耗）
    return "空手", {}


async def run_fishing_show_spots_logic(user):
    """显示可钓鱼水域列表。"""
    if user.get("status") == UserStatus.FISHING:
        return (
            "🎣 你正在钓鱼中！\n"
            "输入 /钓鱼 取消 收竿"
        )

    from ...src.fishing.fishing_manager import get_fishing_skill_level
    skill_lvl = get_fishing_skill_level(user)
    gold = user.get("gold", 0)

    lines = ["═══════════════════════════", "    「 🎣 钓 鱼 」", "═══════════════════════════"]
    lines.append(f"\n📊 钓鱼技能: Lv.{skill_lvl}    💰 金币: {gold}")

    rod_id, _ = _resolve_rod(user)
    bait_id, _ = _resolve_bait(user)
    lines.append(f"🎣 鱼竿: {rod_id}    🪱 鱼饵: {bait_id}")

    lines.append("\n─────────── 水域列表 ───────────")
    for sid, spot in FISHING_SPOTS.items():
        if spot.get("unlock_level", 1) > skill_lvl + 1:
            lock = f" 🔒 需要 Lv.{spot.get('unlock_level', 1)}"
        else:
            lock = ""
        fee = spot.get("license_fee", 0)
        fee_str = f"  (入场费 {fee}金)" if fee > 0 else ""
        base_rate = int(spot.get("success_rate", 0)*100)
        lines.append(
            f"\n{spot.get('emoji', '🪣')} /钓鱼 {sid}"
            f"{fee_str}\n"
            f"   {spot.get('desc', '')} | 基础概率 {base_rate}%{lock}"
        )

    lines.append("\n═══════════════════════════")
    lines.append("📝 /钓鱼 <水域名> 开始钓鱼")
    lines.append("📝 /钓鱼 取消 收竿")
    lines.append("💡 基础概率 15~50% 每分钟，30 分钟兜底")
    return "\n".join(lines)


async def run_fishing_start_logic(user, spot_id: str, store, group_id: str = "") -> str:
    """开始钓鱼（设置 action_detail，让 tick 接管）。"""
    spot = get_spot(spot_id)
    if not spot:
        return f"❌ 未知水域：{spot_id}\n输入 /钓鱼 查看水域列表"

    if spot.get("license_fee", 0) > 0:
        if user.get("gold", 0) < spot["license_fee"]:
            return f"❌ 金币不足，需要 {spot['license_fee']} 金币才能入场"
        user["gold"] -= spot["license_fee"]

    rod_id, rod_eff = _resolve_rod(user)
    bait_id, bait_eff = _resolve_bait(user)

    duration = spot.get("duration_ticks", 60)
    reduce_ticks = rod_eff.get("duration_reduce", 0) + bait_eff.get("duration_reduce", 0)
    actual_ticks = max(20, duration - reduce_ticks)

    now = datetime.now(LOCAL_TZ)

    # 记录发起群（确保 tick 中鱼时能找到）
    groups = user.setdefault("groups", [])
    if group_id and group_id not in groups:
        groups.append(group_id)

    detail = ActionDetail.create(
        action_type=TICK_TYPE_FISHING,
        hours=actual_ticks // 60,
        start_time=now,
        spot_id=spot_id,
        spot_emoji=spot.get("emoji", "🪣"),
        rod_id=rod_id,
        bait_id=bait_id,
        start_group_id=group_id,  # 发起群
    )
    # create() 内部 planned_ticks = hours * 60，我们覆盖为实际 tick
    detail["planned_ticks"] = actual_ticks

    user["status"] = UserStatus.FISHING
    user["current_action"] = TICK_TYPE_FISHING
    user["action_detail"] = detail
    await store.update_user(str(user.get("user_id", "")), user)

    return (
        f"🎣 开始在 {spot.get('emoji', '')} {spot_id} 钓鱼！\n\n"
        f"🎣 鱼竿: {rod_id}\n"
        f"🪱 鱼饵: {bait_id}\n"
        f"⏰ 最长等待: {actual_ticks} 分钟\n"
        f"🎯 基础成功率: {int(spot.get('success_rate', 0)*100)}%\n\n"
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


async def run_fishing_logic(event: AstrMessageEvent, store):
    """钓鱼命令入口：分发到 show_spots / start / cancel / status。"""
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
            msg = await _show_fishing_progress(user)
            yield event.plain_result(msg)
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
        msg = await run_fishing_show_spots_logic(user)
        yield event.plain_result(msg)
        event.stop_event()
        return

    # 开始钓鱼（记录发起群，tick 中鱼时只在原群 @ 用户）
    group_id = event.get_group_id() if not event.is_private_chat() else ""
    msg = await run_fishing_start_logic(user, cmd, store, group_id=group_id)
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


async def run_fish_dex_logic(event: AstrMessageEvent, store, renderer):
    """鱼塘图鉴。"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    if not user:
        yield event.plain_result("📋 你还没注册！先 /签到")
        event.stop_event()
        return

    from ...src.fishing.fishing_manager import FISHES
    _fm._ensure_loaded()  # 确保 FISHES 已加载

    caught = user.get("fishing", {}).get("fish_caught", {})
    try:
        url = await renderer.render_fish_dex(user, event, caught, FISHES)
        yield event.image_result(url)
    except Exception:
        # 降级纯文本
        lines = ["═══════════════════════════", "  🎣 「 鱼 塘 图 鉴 」", "═══════════════════════════",
                 f"\n📊 收集进度: {len(caught)}/{len(FISHES)}"]
        for fname, info in FISHES.items():
            cnt = caught.get(fname, 0)
            mark = "✅" if cnt > 0 else "🔒"
            lines.append(f"  {mark} {info.get('emoji','🐟')} {fname} (x{cnt})")
        biggest = user.get("fishing", {}).get("biggest_catch", {})
        if biggest:
            lines.append(f"\n🏆 最大单条: {biggest.get('fish','')} {biggest.get('weight',0)}kg")
        title = user.get("fishing", {}).get("fish_title", "")
        if title:
            lines.append(f"🏅 称号: {title}")
        yield event.plain_result("\n".join(lines))
    event.stop_event()
