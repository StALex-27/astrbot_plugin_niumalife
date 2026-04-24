"""
签到相关指令
签到、签到统计、我的buff
"""

import random
from datetime import datetime, timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent

from modules.checkin import (
    get_luck_rating, get_streak_reward, roll_lucky_drop,
    format_checkin_report, get_next_streak_threshold
)
from modules.buff import create_buff


LOCAL_TZ = timezone(timedelta(hours=8))


def register_checkin_commands(plugin):
    """注册签到相关指令"""
    
    @filter.command("签到")
    async def checkin(event: AstrMessageEvent):
        """每日签到"""
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n输入「我要当牛马」开始游戏")
            return
        
        now = datetime.now(LOCAL_TZ)
        today_str = now.strftime("%Y-%m-%d")
        checkin = user.get("checkin", {})
        last_date = checkin.get("last_date")
        
        # 检查是否已经签到
        if last_date == today_str:
            rating = get_luck_rating(checkin.get("last_luck", 50))
            streak = checkin.get("streak", 0)
            
            try:
                result = {
                    "luck_value": checkin.get("last_luck", 50),
                    "total_gold": 0,
                    "drop_info": None
                }
                url = await plugin._renderer.render_checkin(user, event, result, already_checked=True)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result(
                    f"📋 你今天已经签到过了！\\n\\n"
                    f"{rating['emoji']} 今日欧气：{rating['name']}\\n"
                    f"🔥 连续签到：{streak} 天\\n\\n"
                    f"明天再来签到吧~"
                )
            return
        
        # 计算连续签到
        streak = checkin.get("streak", 0)
        if last_date:
            try:
                last = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
                delta_days = (now - last).days
                if delta_days == 1:
                    streak += 1
                elif delta_days == 0:
                    pass
                else:
                    streak = 1
            except:
                streak = 1
        else:
            streak = 1
        
        # 随机签到奖励
        luck_value = random.randint(1, 100)
        base_gold = luck_value
        
        # 连续签到奖励
        streak_reward = get_streak_reward(streak)
        streak_bonus = streak_reward["gold"] if streak_reward else 0
        
        # 幸运掉落
        drop = roll_lucky_drop(streak)
        drop_gold = 0
        drop_info = None
        
        if drop:
            if drop["type"] == "gold":
                drop_gold = drop["amount"]
                drop_info = f"💰 {drop_gold}金币"
            elif drop["type"] == "buff":
                buff_instance = create_buff(drop["buff_id"])
                if buff_instance:
                    buffs = checkin.get("active_buffs", [])
                    buffs.append(buff_instance)
                    checkin["active_buffs"] = buffs
                    drop_info = f"✨ 获得buff：{buff_instance['emoji']} {buff_instance['name']}"
            elif drop["type"] == "food":
                food_name, food_data = drop["food_data"]
                attrs = user["attributes"]
                attrs["satiety"] = min(100, attrs["satiety"] + food_data["restore_satiety"])
                drop_info = f"🍖 {food_name}"
            elif drop["type"] == "item":
                item_name, item_data = drop["item_data"]
                inventory = user.get("inventory", [])
                inventory.append({"id": item_data.get("id", item_name), "name": item_name, "equipped": False})
                user["inventory"] = inventory
                drop_info = f"📦 {item_name}"
            
            checkin["lucky_drops"] = checkin.get("lucky_drops", 0) + 1
        
        # 更新 luck_history
        luck_history = checkin.get("luck_history", [])
        luck_history.append(luck_value)
        if len(luck_history) > 30:
            luck_history = luck_history[-30:]
        
        # 计算总金币
        total_gold = base_gold + streak_bonus + drop_gold
        
        # 更新用户数据
        user["gold"] += total_gold
        user["checkin"] = {
            "last_date": today_str,
            "last_luck": luck_value,
            "streak": streak,
            "total_days": checkin.get("total_days", 0) + 1,
            "total_gold": checkin.get("total_gold", 0) + total_gold,
            "lucky_drops": checkin.get("lucky_drops", 0),
            "active_buffs": checkin.get("active_buffs", []),
            "luck_history": luck_history,
        }
        plugin._store.update_user(user_id, user)
        
        # 添加记录
        user.setdefault("records", []).append({
            "type": "签到",
            "detail": f"欧气{luck_value}，连续签到{streak}天",
            "gold_change": total_gold,
            "time": now.isoformat(),
        })
        plugin._store.update_user(user_id, user)
        
        # 生成报告
        report = format_checkin_report(luck_value, base_gold, streak, streak_reward, drop, total_gold)
        
        # 添加下一步提示
        next_threshold = get_next_streak_threshold(streak)
        if next_threshold:
            days_left = next_threshold[0] - streak
            report += f"\\n🌟 再签到 {days_left} 天可获得 {next_threshold[1]['name']} (+{next_threshold[1]['gold']}金币)"
        
        if drop_info:
            report += f"\\n{drop_info}"
        
        try:
            result = {
                "luck_value": luck_value,
                "total_gold": total_gold,
                "streak_bonus": streak_bonus,
                "drop_info": drop_info
            }
            url = await plugin._renderer.render_checkin(user, event, result, already_checked=False)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(report)
    
    @filter.command("我的buff")
    async def my_buffs(event: AstrMessageEvent):
        """查看当前生效的buff"""
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        
        from modules.buff import BuffManager
        valid_buffs = [b for b in active_buffs if not BuffManager.is_expired(b)]
        
        try:
            url = await plugin._renderer.render_buff_list(user, event)
            yield event.image_result(url)
        except Exception:
            lines = ["━━━━━━━━━━━━━━", "「 我 的 BUFF 」", "━━━━━━━━━━━━━━"]
            if not valid_buffs:
                lines.append("暂无生效的 Buff")
                lines.append("通过签到或活动获取吧~")
            else:
                for i, buff in enumerate(valid_buffs, 1):
                    lines.append(f"{i}. {buff['emoji']} {buff['name']}: {buff['desc']}")
            lines.append("━━━━━━━━━━━━━━")
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("签到统计")
    async def checkin_stats(event: AstrMessageEvent):
        """查看签到统计"""
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        checkin = user.get("checkin", {})
        luck_history = checkin.get("luck_history", [])
        total_days = checkin.get("total_days", 0)
        total_gold = checkin.get("total_gold", 0)
        lucky_drops = checkin.get("lucky_drops", 0)
        max_streak = checkin.get("streak", 0)
        
        # 统计各等级次数
        super_lucky = lucky = normal = unlucky = super_unlucky = 0
        for luck in luck_history:
            if luck >= 90:
                super_lucky += 1
            elif luck >= 70:
                lucky += 1
            elif luck >= 40:
                normal += 1
            elif luck >= 20:
                unlucky += 1
            else:
                super_unlucky += 1
        
        try:
            url = await plugin._renderer.render_checkin_stats(user, event)
            yield event.image_result(url)
        except Exception:
            lines = [
                "━━━━━━━━━━━━━━",
                f"「 签 到 统 计 」",
                "━━━━━━━━━━━━━━",
                f"📅 总签到: {total_days} 天",
                f"💰 累计金币: {total_gold}",
                f"🎁 幸运掉落: {lucky_drops} 次",
                f"🏆 最高连续: {max_streak} 天",
                "━━━━━━━━━━━━━━",
                "📊 欧气统计:",
                f"  🤑 超级欧皇: {super_lucky} 次",
                f"  😄 欧皇: {lucky} 次",
                f"  😐 普通人: {normal} 次",
                f"  😣 非酋: {unlucky} 次",
                f"  💀 超级非酋: {super_unlucky} 次",
                "━━━━━━━━━━━━━━",
            ]
            yield event.plain_result("\\n".join(lines))
