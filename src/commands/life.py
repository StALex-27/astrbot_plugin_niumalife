"""
生活相关指令
食物列表、吃、睡觉、住所
"""

from datetime import datetime, timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent

from modules.constants import FOODS, RESIDENCES, MAX_ATTRIBUTE
from modules.user import UserStatus
from modules.tick import TickType, ActionDetail


LOCAL_TZ = timezone(timedelta(hours=8))


def register_life_commands(plugin):
    """注册生活相关指令"""
    
    @filter.command("食物列表")
    async def food_list(event: AstrMessageEvent):
        """查看食物列表"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        try:
            url = await plugin._renderer.render_food_list(FOODS, user, event)
            yield event.image_result(url)
        except Exception:
            lines = ["━━━━━━━━━━━━━━", "「 食 物 列 表 」", "━━━━━━━━━━━━━━"]
            for food_name, food in FOODS.items():
                attrs_effect = []
                if food["restore_strength"] > 0:
                    attrs_effect.append(f"体力+{food['restore_strength']}")
                if food["restore_energy"] > 0:
                    attrs_effect.append(f"精力+{food['restore_energy']}")
                if food["restore_mood"] != 0:
                    attrs_effect.append(f"心情+{food['restore_mood']}" if food["restore_mood"] > 0 else f"心情{food['restore_mood']}")
                if food["restore_health"] > 0:
                    attrs_effect.append(f"健康+{food['restore_health']}")
                attrs_str = "，".join(attrs_effect) if attrs_effect else "无"
                
                lines.append(f"【{food_name}】{food['price']}金 | 饱食+{food['restore_satiety']} | {attrs_str}")
            
            lines.append("━━━━━━━━━━━━━━")
            lines.append("使用 /吃 <食物> 购买食用")
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("吃")
    async def eat(event: AstrMessageEvent):
        """购买并食用食物"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        _, args = plugin._parser.parse(event)
        
        if len(args) < 1:
            yield event.plain_result("📋 格式：/吃 <食物>\\n例如：/吃 泡面")
            return
        
        food_name = args[0]
        food = FOODS.get(food_name)
        
        if not food:
            yield event.plain_result(f"📋 不存在该食物：{food_name}\\n使用 /食物列表 查看")
            return
        
        if user["gold"] < food["price"]:
            yield event.plain_result(f"📋 金币不足！需要 {food['price']} 金币，你只有 {user['gold']} 金币")
            return
        
        # 扣除金币
        user["gold"] -= food["price"]
        
        # 恢复属性
        attrs = user["attributes"]
        attrs["strength"] = min(MAX_ATTRIBUTE, attrs["strength"] + food["restore_strength"])
        attrs["energy"] = min(MAX_ATTRIBUTE, attrs["energy"] + food["restore_energy"])
        attrs["mood"] = min(MAX_ATTRIBUTE, attrs["mood"] + food["restore_mood"])
        attrs["health"] = min(MAX_ATTRIBUTE, attrs["health"] + food["restore_health"])
        old_satiety = attrs["satiety"]
        attrs["satiety"] = min(MAX_ATTRIBUTE, attrs["satiety"] + food["restore_satiety"])
        
        # 饱食过度惩罚
        if attrs["satiety"] > MAX_ATTRIBUTE:
            attrs["health"] = max(0, attrs["health"] - 1)
            attrs["satiety"] = MAX_ATTRIBUTE
        
        user["attributes"] = attrs
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_eat(
                user, event,
                food_name=food_name,
                food_emoji=food.get("emoji", "🍖"),
                restore_health=food.get("restore_health", 0),
                restore_strength=food.get("restore_strength", 0),
                restore_energy=food.get("restore_energy", 0),
                restore_mood=food.get("restore_mood", 0)
            )
            yield event.image_result(url)
        except Exception:
            lines = [
                "━━━━━━━━━━━━━━",
                "「 使 用 食 物 」",
                "━━━━━━━━━━━━━━",
                f"🍖 食用了：{food_name}",
                f"💰 金币：-{food['price']} → 剩余 {user['gold']}",
                f"🍖 饱食：{old_satiety:.0f} → {attrs['satiety']:.0f}",
                "━━━━━━━━━━━━━━",
            ]
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("睡觉")
    async def sleep(event: AstrMessageEvent):
        """开始睡眠"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法睡觉")
            return
        
        _, args = plugin._parser.parse(event)
        
        success, hours, err = plugin._parser.get_range(args, 0, 1, 24)
        if not success:
            yield event.plain_result(f"📋 {err}")
            return
        
        residence = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence, RESIDENCES["桥下"])
        sleep_bonus = res_info["sleep_bonus"]
        
        # 使用ActionDetail
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TickType.SLEEP,
            hours=hours,
            start_time=now,
            sleep_bonus=sleep_bonus,
            residence=residence
        )
        
        user["status"] = UserStatus.SLEEPING
        user["current_action"] = TickType.SLEEP
        user["action_detail"] = detail
        
        await plugin._store.update_user(user_id, user)
        
        lines = [
            "━━━━━━━━━━━━━━",
            "「 开 始 睡 眠 」",
            "━━━━━━━━━━━━━━",
            f"📋 时长：{hours} 小时",
            f"🏠 住所：{residence} (睡眠加成 x{sleep_bonus})",
            "━━━━━━━━━━━━━━",
            "「 恢复预估 」",
            f"💪 体力：+{res_info['strength_recovery'] * hours * sleep_bonus * 1.5:.0f}",
            f"⚡ 精力：+{res_info['energy_recovery'] * hours * sleep_bonus * 1.5:.0f}",
            f"😊 心情：+{res_info['mood_recovery'] * hours * sleep_bonus:.0f}",
            f"❤️ 健康：+{res_info['health_recovery'] * hours * sleep_bonus:.0f}",
            "━━━━━━━━━━━━━━",
            "💡 睡眠饱食消耗减半",
            "━━━━━━━━━━━━━━",
        ]
        
        try:
            url = await plugin._renderer.render_sleep(
                user, event,
                hours=hours,
                residence=residence,
                sleep_bonus=sleep_bonus,
                strength_rec=int(res_info['strength_recovery'] * hours * sleep_bonus * 1.5),
                energy_rec=int(res_info['energy_recovery'] * hours * sleep_bonus * 1.5),
                mood_rec=int(res_info['mood_recovery'] * hours * sleep_bonus),
                health_rec=int(res_info['health_recovery'] * hours * sleep_bonus)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("取消睡觉")
    async def cancel_sleep(event: AstrMessageEvent):
        """取消睡眠"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.SLEEPING:
            yield event.plain_result("📋 你当前没有在睡觉")
            return
        
        user["status"] = UserStatus.FREE
        user["locked_until"] = None
        user["current_action"] = None
        user["action_detail"] = None
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success("✅ 已取消睡眠，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("📋 已取消睡眠，返回空闲状态")
    
    @filter.command("住所")
    async def residence(event: AstrMessageEvent):
        """查看当前住所"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        residence_name = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence_name, RESIDENCES["桥下"])
        
        try:
            url = await plugin._renderer.render_residence(user, event, res_info)
            yield event.image_result(url)
        except Exception:
            lines = [
                "━━━━━━━━━━━━━━",
                "「 当 前 住 所 」",
                "━━━━━━━━━━━━━━",
                f"🏠 住所：{residence_name}",
                f"📝 描述：{res_info['desc']}",
                "━━━━━━━━━━━━━━",
                "「 居住效果(每小时) 」",
                f"💪 体力恢复：+{res_info['strength_recovery']}",
                f"⚡ 精力恢复：+{res_info['energy_recovery']}",
                f"😊 心情恢复：{res_info['mood_recovery']:+d}",
                f"❤️ 健康恢复：{res_info['health_recovery']:+d}",
                f"😴 睡眠加成：x{res_info['sleep_bonus']}",
                "━━━━━━━━━━━━━━",
            ]
            yield event.plain_result("\\n".join(lines))
