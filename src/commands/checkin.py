"""
签到命令逻辑
"""
import random
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.checkin import get_luck_rating, get_streak_reward, roll_lucky_drop, get_checkin_grade
from ...modules.constants import MAX_ATTRIBUTE


LOCAL_TZ = timezone(timedelta(hours=8))

# 签到卡片渲染超时（秒）—— 防止 t2i 服务卡死时阻塞整个命令
_RENDER_TIMEOUT = 30.0


# 9/4凌晨: 新玩家默认渔具 (袖钩 + 竹竿 + 棉线) - 让玩家开箱就能钓鱼
_STARTER_FISHING_GEAR = {
    "fishing_hook": "袖钩",       # micro30/small70 (默认初始钩)
    "fishing_rod": "竹竿",  # 承载 1.5kg
    "fishing_line": "棉线",         # 承载 0.5kg
}


async def _grant_starter_fishing_gear(store, user_id: str) -> list[str]:
    """新玩家注册时赠送默认渔具, 直接装备上

    Returns:
        赠送的物品名称列表 (用于通知)
    """
    from ...modules.constants import ITEMS  # 避免循环导入
    user = await store.get_user(user_id)
    if not user:
        return []
    inventory = user.setdefault("inventory", [])
    equipped_items = user.setdefault("equipped_items", {})
    granted = []
    for slot, item_id in _STARTER_FISHING_GEAR.items():
        item_info = ITEMS.get(item_id)
        if not item_info:
            continue
        # 加到背包 (如果还没有)
        if not any(inv.get("id") == item_id for inv in inventory):
            inventory.append({"id": item_id, "name": item_id, "equipped": True})
        # 装备到对应槽位
        equipped_items[slot] = item_info
        granted.append(item_id)
    await store.update_user(user_id, user)
    return granted


async def run_checkin_logic(event: AstrMessageEvent, store, sender):
    """签到命令逻辑（含自动注册）.

    9/6: 改用 sender.send_card() 替代 2 处 try/except + yield image_result/plain_result 样板。
    sender 内部统一: 渲染成功发图, 渲染超时/异常 fallback 文本。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    # 自动注册
    is_new_user = False
    if not user:
        nickname = event.get_sender_name()
        user = await store.create_user(user_id, nickname)
        is_new_user = True
        # 9/4凌晨: 新玩家赠送默认渔具 (袖钩 + 竹竿 + 棉线)
        await _grant_starter_fishing_gear(store, user_id)

    now = datetime.now(LOCAL_TZ)
    today_str = now.strftime("%Y-%m-%d")
    checkin_data = user.get("checkin", {})
    last_date = checkin_data.get("last_date")

    # 今日已签到
    if last_date == today_str:
        # 9/6: 改用 sender.send_card() (CardType.CHECKIN + already=True 模板分支)
        # 注: data 字段对齐 renderer.render_checkin 内部组装 (nickname/luck_emoji/luck_desc/gold/streak/...)
        already_checkin = checkin_data
        streak = already_checkin.get("streak", 0)
        last_luck = already_checkin.get("last_luck", 50)
        rating = get_luck_rating(last_luck)
        luck_emoji = rating.get("emoji", "🎲")
        luck_name = rating.get("name", "普通人")
        luck_desc = rating.get("desc", "")
        data = {
            "user_id": user_id,
            "nickname": user.get("nickname", "未知"),
            "luck_emoji": luck_emoji,
            "luck_name": luck_name,
            "luck_desc": luck_desc,
            "gold": 0,
            "streak": streak,
            "streak_bonus": None,
            "drop": "",
            "already": True,
            "is_new_user": False,
        }
        fallback_text = (
            f"📋 你今天已经签到过了！\n\n"
            f"🔥 连续签到：{streak} 天\n"
            f"🎲 今日欧气：{last_luck}\n\n"
            f"明天再来签到吧~"
        )
        async for r in sender.send_card(
            event, "checkin", data,
            fallback_text=fallback_text,
            render_timeout=_RENDER_TIMEOUT,
        ):
            yield r
        return

    # 计算连续签到
    streak = checkin_data.get("streak", 0) if last_date else 0
    if last_date:
        try:
            last = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
            delta_days = (now - last).days
            streak = streak + 1 if delta_days == 1 else 1
        except Exception as e:

            import logging as __l

            __l.getLogger(__name__).warning(f"[render] {type(e).__name__}: {e}")
            streak = 1
    else:
        streak = 1

    # 计算奖励
    luck_value = random.randint(1, 100)
    base_gold = luck_value
    streak_reward = get_streak_reward(streak)
    streak_bonus = streak_reward["gold"] if streak_reward else 0

    drop = roll_lucky_drop(streak)
    drop_gold = 0
    drop_info = None

    if drop:
        if drop["type"] == "gold":
            drop_gold = drop["amount"]
            drop_info = f"💰 {drop_gold}金币"
        elif drop["type"] == "buff":
            from ...modules.buff import create_buff
            buff_instance = create_buff(drop["buff_id"])
            if buff_instance:
                buffs = checkin_data.get("active_buffs", [])
                buffs.append(buff_instance)
                checkin_data["active_buffs"] = buffs
                drop_info = f"✨ {buff_instance['emoji']} {buff_instance['name']}"
        elif drop["type"] == "food":
            food_name, food_data = drop["food_data"]
            # 食物进背包（用户可自己 /吃），不直接应用属性
            attrs = user["attributes"]
            inventory = user.setdefault("inventory", [])
            existing = next(
                (it for it in inventory
                 if it.get("id") == food_name and it.get("type") != "fish"),
                None,
            )
            if existing:
                existing["quantity"] = existing.get("quantity", 1) + 1
            else:
                inventory.append({
                    "id": food_name,
                    "name": food_name,
                    "type": "food",
                    "quantity": 1,
                    "emoji": food_data.get("emoji", "🍖"),
                })
            # 食物效果提示（按体力>精力>饱食>健康>心情顺序）
            food_eff = food_data.get("effects", {})
            attr_parts = []
            for k in ("strength", "energy", "satiety", "health", "mood"):
                v = food_eff.get(k, 0)
                if v:
                    attr_parts.append(f"+{v}{ {'strength':'💪体','energy':'⚡精','satiety':'🍖饱','health':'❤健','mood':'😊心'}.get(k, k) }")
            drop_info = f"🍖 {food_name} ({' '.join(attr_parts)})" if attr_parts else f"🍖 {food_name}"
        elif drop["type"] == "item":
            # roll_lucky_drop 也会产出道具（ITEMS 里的非食物）—— 加入 inventory
            item_name, item_data = drop["item_data"]
            inventory = user.setdefault("inventory", [])
            existing = next(
                (it for it in inventory
                 if it.get("id") == item_name and it.get("type") != "fish"),
                None,
            )
            if existing:
                existing["quantity"] = existing.get("quantity", 1) + 1
            else:
                inventory.append({
                    "id": item_name,
                    "name": item_name,
                    "type": "item",
                    "quantity": 1,
                    "emoji": item_data.get("emoji", "📦"),
                })
            drop_info = f"📦 {item_name}"
        checkin_data["lucky_drops"] = checkin_data.get("lucky_drops", 0) + 1

    total_gold = base_gold + streak_bonus + drop_gold
    user["gold"] += total_gold
    luck_history = checkin_data.get("luck_history", [])
    luck_history.append(luck_value)
    if len(luck_history) > 30:
        luck_history = luck_history[-30:]

    user["checkin"] = {
        "last_date": today_str,
        "last_luck": luck_value,
        "streak": streak,
        "total_days": checkin_data.get("total_days", 0) + 1,
        "total_gold": checkin_data.get("total_gold", 0) + total_gold,
        "lucky_drops": checkin_data.get("lucky_drops", 0),
        "active_buffs": checkin_data.get("active_buffs", []),
        "luck_history": luck_history,
    }

    # 更新累计签到天数
    from ...modules.user import update_lifetime_stat
    update_lifetime_stat(user, "checkin_days", 1)

    await store.update_user(user_id, user)

    # 9/6: 改用 sender.send_card() (CardType.CHECKIN 渲染模板, 30s 超时保护)
    grade_info, fortune_text = get_checkin_grade(luck_value)
    rating = get_luck_rating(luck_value)
    r_emoji = rating.get("emoji", "🎲") if isinstance(rating, dict) else "🎲"
    r_name = rating.get("name", "普通人") if isinstance(rating, dict) else "普通人"
    data = {
        "user_id": user_id,
        "nickname": user.get("nickname", "未知"),
        "luck_emoji": grade_info.get("emoji", r_emoji) if grade_info else r_emoji,
        "luck_name": grade_info.get("name", r_name) if grade_info else r_name,
        "luck_desc": fortune_text,
        "gold": total_gold,
        "streak": streak,
        "streak_bonus": streak_bonus,
        "drop": drop_info or "",
        "already": False,
        "is_new_user": is_new_user,
    }
    lines = ["✅ 签到成功！"]
    if is_new_user:
        lines.append("🎉 注册成功！")
    lines.append(f"{data['luck_emoji']} {data['luck_name']}")
    lines.append(f"💰 +{total_gold}金币 (基础{luck_value}+连续{streak_bonus})")
    lines.append(f"🔥 连续签到: {streak}天")
    if drop_info:
        lines.append(f"🎁 {drop_info}")
    fallback_text = "\n\n".join(lines)
    async for r in sender.send_card(
        event, "checkin", data,
        fallback_text=fallback_text,
        render_timeout=_RENDER_TIMEOUT,
    ):
        yield r