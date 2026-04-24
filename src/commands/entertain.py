"""
娱乐相关指令
娱乐列表、娱乐、取消娱乐
"""

from datetime import datetime, timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent

from modules.constants import ENTERTAINMENTS, MAX_ATTRIBUTE
from modules.user import UserStatus
from modules.tick import TickType, ActionDetail


LOCAL_TZ = timezone(timedelta(hours=8))


def register_entertain_commands(plugin):
    """注册娱乐相关指令"""
    
    @filter.command("娱乐列表")
    async def entertainment_list(event: AstrMessageEvent):
        """查看可进行的娱乐活动"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        try:
            url = await plugin._renderer.render_entertainment_list(ENTERTAINMENTS, user, event)
            yield event.image_result(url)
        except Exception:
            lines = ["━━━━━━━━━━━━━━", "「 娱 乐 列 表 」", "━━━━━━━━━━━━━━"]
            entertainment_categories = {
                "休闲": ["公园散步", "看电视", "听音乐", "玩手机"],
                "社交": ["逛商场", "看电影", "唱K", "酒吧", "聚餐"],
                "运动": ["慢跑", "健身房", "游泳", "篮球", "瑜伽", "拳击"],
                "游戏": ["网吧开黑", "手游氪金", "电玩城", "密室逃脱", "桌游吧"],
                "奢华": ["SPA按摩", "温泉度假", "高尔夫", "游艇派对", "出国旅游"],
                "极限": ["蹦极", "跳伞", "潜水", "攀岩", "赛车"],
            }
            
            for category, names in entertainment_categories.items():
                lines.append(f"\\n【{category}】")
                for name in names:
                    ent = ENTERTAINMENTS.get(name)
                    if ent:
                        lines.append(
                            f"  ◆ {name} | 💰{ent.get('cost_per_hour', 0)}金/时 | "
                            f"😊+{ent.get('restore_mood', 0)} | 💪-{ent.get('consume_strength', 0)}"
                        )
            
            lines.append("━━━━━━━━━━━━━━")
            lines.append("使用 /娱乐 <名称> <小时> 开始娱乐")
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("娱乐")
    async def start_entertain(event: AstrMessageEvent):
        """开始娱乐"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法娱乐\\n先取消当前动作")
            return
        
        _, args = plugin._parser.parse(event)
        
        if len(args) < 2:
            yield event.plain_result("📋 格式：/娱乐 <名称> <小时>\\n例如：/娱乐 公园散步 2")
            return
        
        ent_name = args[0]
        success, hours, err = plugin._parser.get_range(args, 1, 1, 8)
        if not success:
            yield event.plain_result(f"📋 {err}")
            return
        
        entertainment = ENTERTAINMENTS.get(ent_name)
        if not entertainment:
            yield event.plain_result(f"📋 不存在该娱乐：{ent_name}\\n使用 /娱乐列表 查看")
            return
        
        # 检查金币
        total_cost = entertainment.get("cost_per_hour", 0) * hours
        if user["gold"] < total_cost:
            yield event.plain_result(f"📋 金币不足！需要 {total_cost} 金币，你只有 {user['gold']} 金币")
            return
        
        # 使用ActionDetail
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TickType.ENTERTAIN,
            hours=hours,
            start_time=now,
            entertainment_name=ent_name,
            cost_per_hour=entertainment.get("cost_per_hour", 0),
            restore_mood=entertainment.get("restore_mood", 0),
            consume_strength=entertainment.get("consume_strength", 0),
            consume_energy=entertainment.get("consume_energy", 0)
        )
        
        user["status"] = UserStatus.ENTERTAINING
        user["current_action"] = TickType.ENTERTAIN
        user["action_detail"] = detail
        
        await plugin._store.update_user(user_id, user)
        
        lines = [
            "━━━━━━━━━━━━━━",
            "「 开 始 娱 乐 」",
            "━━━━━━━━━━━━━━",
            f"🎮 娱乐：{ent_name}",
            f"⏰ 时长：{hours} 小时",
            f"💰 花费：{total_cost} 金币",
            "━━━━━━━━━━━━━━",
            "「 效果预估 」",
            f"😊 心情：+{entertainment.get('restore_mood', 0) * hours}",
            f"💪 体力：-{entertainment.get('consume_strength', 0) * hours}",
            f"⚡ 精力：-{entertainment.get('consume_energy', 0) * hours}",
            "━━━━━━━━━━━━━━",
        ]
        
        try:
            url = await plugin._renderer.render_entertain_start(
                user, event,
                ent_name=ent_name,
                ent_emoji=entertainment.get("emoji", "🎮"),
                hours=hours,
                gain_mood=entertainment.get('restore_mood', 0) * hours,
                consume_satiety=int(entertainment.get('consume_strength', 0) * hours)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("取消娱乐")
    async def cancel_entertain(event: AstrMessageEvent):
        """取消娱乐"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.ENTERTAINING:
            yield event.plain_result("📋 你当前没有在娱乐")
            return
        
        user["status"] = UserStatus.FREE
        user["locked_until"] = None
        user["current_action"] = None
        user["action_detail"] = None
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success("✅ 已取消娱乐，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("📋 已取消娱乐，返回空闲状态")
