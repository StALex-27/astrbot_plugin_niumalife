"""
交互式命令处理器
实现2次交互内完成操作的智能指令系统

核心指令 (11个):
- /档案 - 查看档案
- /打工 [工作名] [小时] - 工作
- /学习 [课程名] [小时] - 学习
- /娱乐 [名称] [小时] - 娱乐
- /吃 [食物名] - 吃东西
- /签到 - 每日签到 (含自动注册)
- /住 [操作] - 住所管理
- /背包 - 背包
- /股市 [操作] - 股市
- /取消 - 取消动作
- /帮助 - 帮助
"""

import random
from datetime import datetime, timezone, timedelta

from astrbot.api.event import filter, AstrMessageEvent
from ...modules.constants import JOBS, COURSES, FOODS, RESIDENCES, ENTERTAINMENTS, MAX_ATTRIBUTE
from ...modules.user import UserStatus
from ...modules.tick import TickType, ActionDetail
from ...modules.checkin import get_luck_rating, get_streak_reward, roll_lucky_drop


LOCAL_TZ = timezone(timedelta(hours=8))


def register_interactive_commands(plugin):
    """注册所有交互式命令"""
    
    # ========== 档案 ==========
    @filter.command("档案")
    async def profile(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            try:
                url = await plugin._renderer.render_error("未注册", "你还没有签到过！\\n输入 /签到 自动注册并签到", event)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result("📋 你还没有注册！\\n输入 /签到 自动注册并签到")
            return
        
        try:
            url = await plugin._renderer.render_profile(user, event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(_format_profile_text(user))
    
    # ========== 打工 ==========
    @filter.command("打工")
    async def work(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 自动注册")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法工作\\n先用 /取消 取消当前动作")
            return
        
        _, args = plugin._parser.parse(event)
        
        job_name = args[0] if len(args) >= 1 else None
        hours = None
        if len(args) >= 2:
            try:
                hours = max(1, min(8, int(args[1])))
            except ValueError:
                yield event.plain_result("📋 时长必须是1-8的数字")
                return
        
        if not job_name or not hours:
            job_list = _format_job_list()
            if not job_name:
                yield event.plain_result(
                    f"💼 工作列表:\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"{job_list}\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"回复: /打工 工作名 小时数\\n"
                    f"例如: /打工 外卖 4"
                )
            else:
                job = JOBS.get(job_name)
                if not job:
                    yield event.plain_result(f"📋 不存在该工作：{job_name}")
                    return
                yield event.plain_result(
                    f"💼 {job_name} | {job['hourly_wage']}金/时\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"请选择时长 (1-8小时)：\\n"
                    f"例如: /打工 {job_name} 4"
                )
            return
        
        job = JOBS.get(job_name)
        if not job:
            yield event.plain_result(f"📋 不存在该工作：{job_name}")
            return
        
        if not plugin._check_skill_required(user["skills"], job.get("skill_required", {})):
            skill_req = ", ".join([f"{k}Lv.{v}" for k, v in job.get("skill_required", {}).items()])
            yield event.plain_result(f"📋 技能不足！需要：{skill_req}")
            return
        
        enough, reason = plugin._check_attribute_enough(user["attributes"], job, hours)
        if not enough:
            yield event.plain_result(f"📋 {reason}")
            return
        
        expected_gold = job['hourly_wage'] * hours
        consume_strength = job['consume_strength'] * hours
        consume_energy = job['consume_energy'] * hours
        
        emoji = "💪" if job.get("type") == "体力" else "🧠"
        
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TickType.WORK,
            hours=hours,
            start_time=now,
            job_name=job_name,
            hourly_wage=job["hourly_wage"],
            consume_strength=job["consume_strength"],
            consume_energy=job["consume_energy"],
            consume_mood=job.get("consume_mood", 0),
            consume_health=job.get("consume_health", 0),
            consume_satiety=job.get("consume_satiety", 3)
        )
        
        user["status"] = UserStatus.WORKING
        user["current_action"] = TickType.WORK
        user["action_detail"] = detail
        plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_job_start(
                user, event,
                job_name=job_name,
                job_emoji=emoji,
                hours=hours,
                expected_gold=expected_gold,
                expected_exp=0,
                consume_strength=consume_strength,
                consume_energy=consume_energy,
                consume_satiety=int(job.get('consume_satiety', 3) * hours * 0.5)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(
                f"✅ 开始工作:\\n"
                f"━━━━━━━━━━━━━━\\n"
                f"{emoji} {job_name} x {hours}小时\\n"
                f"💰 预计收入: {expected_gold}金币\\n"
                f"💪 体力: -{consume_strength}\\n"
                f"⚡ 精力: -{consume_energy}\\n"
                f"━━━━━━━━━━━━━━\\n"
                f"🎉 开始工作！"
            )
    
    # ========== 学习 ==========
    @filter.command("学习")
    async def learn(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法学习\\n先用 /取消 取消当前动作")
            return
        
        _, args = plugin._parser.parse(event)
        
        course_name = args[0] if len(args) >= 1 else None
        hours = int(args[1]) if len(args) >= 2 else None
        
        if not course_name:
            yield event.plain_result(f"📚 课程列表:\\n━━━━━━━━━━━━━━\\n{_format_course_list()}\\n━━━━━━━━━━━━━━\\n回复: /学习 课程名 小时数\\n例如: /学习 编程 4")
            return
        
        course = COURSES.get(course_name)
        if not course:
            yield event.plain_result(f"📋 不存在该课程：{course_name}")
            return
        
        if not hours:
            yield event.plain_result(f"📚 {course_name} | {course.get('cost', 0)}金/时\\n━━━━━━━━━━━━━━\\n请选择时长 (1-8小时)：\\n例如: /学习 {course_name} 4")
            return
        
        attrs = user["attributes"]
        if attrs["strength"] < course.get("consume_strength", 3) * hours * 0.5:
            yield event.plain_result("📋 体力不足，无法学习")
            return
        if attrs["energy"] < course.get("consume_energy", 8) * hours * 0.5:
            yield event.plain_result("📋 精力不足，无法学习")
            return
        
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TickType.LEARN,
            hours=hours,
            start_time=now,
            course_name=course_name,
            exp_per_hour=course.get("exp_per_hour", 10),
            consume_strength=course.get("consume_strength", 3),
            consume_energy=course.get("consume_energy", 8),
            consume_mood=course.get("consume_mood", 5),
            cost=course.get("cost", 0)
        )
        
        user["status"] = UserStatus.LEARNING
        user["current_action"] = TickType.LEARN
        user["action_detail"] = detail
        plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_entertain_start(
                user, event,
                ent_name=course_name,
                ent_emoji="📚",
                hours=hours,
                gain_mood=course.get('exp_per_hour', 10) * hours,
                consume_satiety=int(course.get('consume_strength', 3) * hours)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(f"✅ 开始学习:\\n━━━━━━━━━━━━━━\\n📚 {course_name} x {hours}小时\\n📚 预计经验: {course.get('exp_per_hour', 10) * hours}\\n━━━━━━━━━━━━━━\\n🎉 开始学习！")
    
    # ========== 娱乐 ==========
    @filter.command("娱乐")
    async def entertain(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法娱乐")
            return
        
        _, args = plugin._parser.parse(event)
        
        ent_name = args[0] if len(args) >= 1 else None
        hours = int(args[1]) if len(args) >= 2 else None
        
        if not ent_name:
            yield event.plain_result(f"🎮 娱乐列表:\\n━━━━━━━━━━━━━━\\n{_format_entertainment_list()}\\n━━━━━━━━━━━━━━\\n回复: /娱乐 名称 小时数\\n例如: /娱乐 游戏 2")
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
        plugin._store.update_user(user_id, user)
        
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
            yield event.plain_result(f"✅ 开始娱乐:\\n━━━━━━━━━━━━━━\\n🎮 {ent_name} x {hours}小时\\n💰 花费: {total_cost}金币\\n━━━━━━━━━━━━━━\\n🎉 开始娱乐！")
    
    # ========== 吃 ==========
    @filter.command("吃")
    async def eat(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
        if len(args) < 1:
            yield event.plain_result(f"🍖 食物列表:\\n━━━━━━━━━━━━━━\\n{_format_food_list()}\\n━━━━━━━━━━━━━━\\n回复: /吃 食物名")
            return
        
        food_name = args[0]
        food = FOODS.get(food_name)
        
        if not food:
            yield event.plain_result(f"📋 不存在该食物：{food_name}")
            return
        
        if user["gold"] < food["price"]:
            yield event.plain_result(f"📋 金币不足！需要 {food['price']} 金币，你只有 {user['gold']} 金币")
            return
        
        user["gold"] -= food["price"]
        
        attrs = user["attributes"]
        attrs["strength"] = min(MAX_ATTRIBUTE, attrs["strength"] + food["restore_strength"])
        attrs["energy"] = min(MAX_ATTRIBUTE, attrs["energy"] + food["restore_energy"])
        attrs["mood"] = min(MAX_ATTRIBUTE, attrs["mood"] + food["restore_mood"])
        attrs["health"] = min(MAX_ATTRIBUTE, attrs["health"] + food["restore_health"])
        attrs["satiety"] = min(MAX_ATTRIBUTE, attrs["satiety"] + food["restore_satiety"])
        
        user["attributes"] = attrs
        plugin._store.update_user(user_id, user)
        
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
            yield event.plain_result(f"✅ 食用成功:\\n━━━━━━━━━━━━━━\\n🍖 {food_name}\\n💰 -{food['price']}金币\\n━━━━━━━━━━━━━━\\n🎉 食用成功！")
    
    # ========== 签到 (含自动注册) ==========
    @filter.command("签到")
    async def checkin(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        # 自动注册
        is_new_user = False
        if not user:
            nickname = event.get_sender_name()
            user = plugin._store.create_user(user_id, nickname)
            is_new_user = True
        
        now = datetime.now(LOCAL_TZ)
        today_str = now.strftime("%Y-%m-%d")
        checkin_data = user.get("checkin", {})
        last_date = checkin_data.get("last_date")
        
        # 今日已签到
        if last_date == today_str:
            try:
                result = {"luck_value": checkin_data.get("last_luck", 50), "total_gold": 0, "drop_info": None}
                url = await plugin._renderer.render_checkin(user, event, result, already_checked=True)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result(f"📋 你今天已经签到过了！\\n\\n🔥 连续签到：{checkin_data.get('streak', 0)} 天\\n🎲 今日欧气：{checkin_data.get('last_luck', 50)}\\n\\n明天再来签到吧~")
            return
        
        # 计算连续签到
        streak = checkin_data.get("streak", 0) if last_date else 0
        if last_date:
            try:
                last = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
                delta_days = (now - last).days
                streak = streak + 1 if delta_days == 1 else 1
            except:
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
                from modules.buff import create_buff
                buff_instance = create_buff(drop["buff_id"])
                if buff_instance:
                    buffs = checkin_data.get("active_buffs", [])
                    buffs.append(buff_instance)
                    checkin_data["active_buffs"] = buffs
                    drop_info = f"✨ {buff_instance['emoji']} {buff_instance['name']}"
            elif drop["type"] == "food":
                food_name, food_data = drop["food_data"]
                attrs = user["attributes"]
                attrs["satiety"] = min(MAX_ATTRIBUTE, attrs["satiety"] + food_data["restore_satiety"])
                drop_info = f"🍖 {food_name}"
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
        plugin._store.update_user(user_id, user)
        
        try:
            result = {
                "luck_value": luck_value,
                "total_gold": total_gold,
                "streak_bonus": streak_bonus,
                "drop_info": drop_info,
                "is_new_user": is_new_user,
            }
            url = await plugin._renderer.render_checkin(user, event, result, already_checked=False)
            yield event.image_result(url)
        except Exception:
            rating = get_luck_rating(luck_value)
            msg = f"✅ 签到成功！\\n\\n"
            if is_new_user:
                msg += f"🎉 注册成功！\\n\\n"
            msg += f"{rating['emoji']} {rating['name']}\\n"
            msg += f"💰 +{total_gold}金币 (基础{luck_value}+连续{streak_bonus})\\n"
            msg += f"🔥 连续签到: {streak}天\\n"
            if drop_info:
                msg += f"🎁 {drop_info}\\n"
            yield event.plain_result(msg)
    
    # ========== 住 ==========
    @filter.command("住")
    async def residence_cmd(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
        residence_name = user.get("residence", "桥下")
        res_info = RESIDENCES.get(residence_name, RESIDENCES["桥下"])
        
        if not args:
            try:
                url = await plugin._renderer.render_residence(user, event, res_info)
                yield event.image_result(url)
            except Exception:
                yield event.plain_result(
                    f"🏠 当前住所: {residence_name}\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"💪 体力恢复: +{res_info.get('strength_recovery', 2)}/时\\n"
                    f"⚡ 精力恢复: +{res_info.get('energy_recovery', 2)}/时\\n"
                    f"😴 睡眠加成: x{res_info.get('sleep_bonus', 1.0)}\\n"
                    f"━━━━━━━━━━━━━━\\n"
                    f"回复: /住 租/买 名称\\n"
                    f"例如: /住 租 公寓"
                )
            return
        
        action = args[0]
        target_name = args[1] if len(args) > 1 else None
        
        if action in ["租", "租房"] and target_name:
            target = RESIDENCES.get(target_name)
            if not target or target.get("type") == "永久":
                yield event.plain_result(f"📋 不存在该房产或不可租：{target_name}")
                return
            
            daily_rent = target.get("rent", 0)
            if user["gold"] < daily_rent:
                yield event.plain_result(f"📋 金币不足！租金 {daily_rent} 金币/天，你只有 {user['gold']} 金币")
                return
            
            user["residence"] = target_name
            user["gold"] -= daily_rent
            plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 租房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{daily_rent}金币 (日租)\\n━━━━━━━━━━━━━━\\n🎉 欢迎入住！")
        
        elif action in ["买", "买房"] and target_name:
            target = RESIDENCES.get(target_name)
            if not target or target.get("type") == "租":
                yield event.plain_result(f"📋 不存在该房产或不可买：{target_name}")
                return
            
            price = target.get("price", 0)
            if user["gold"] < price:
                yield event.plain_result(f"📋 金币不足！售价 {price} 金币，你只有 {user['gold']} 金币")
                return
            
            user["residence"] = target_name
            user["gold"] -= price
            plugin._store.update_user(user_id, user)
            yield event.plain_result(f"✅ 购房成功！\\n━━━━━━━━━━━━━━\\n🏠 {target_name}\\n💰 -{price}金币\\n━━━━━━━━━━━━━━\\n🎉 恭喜拥有房产！")
        
        else:
            lines = ["🏠 住所操作:", "━━━━━━━━━━━━━━", "• /住 - 查看当前住所", "• /住 租 名称 - 租房", "• /住 买 名称 - 买房", "━━━━━━━━━━━━━━", "可用房产:"]
            for k, v in list(RESIDENCES.items())[:5]:
                t = v.get('type', '')
                p = v.get('rent', v.get('price', 0))
                lines.append(f"• {k} ({t}-{p}金)")
            yield event.plain_result("\n".join(lines))
    
    # ========== 背包 ==========
    @filter.command("背包")
    async def backpack(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        inventory = user.get("inventory", [])
        
        if not inventory:
            yield event.plain_result(f"🎒 背包是空的！\\n\\n通过签到或购买获取物品")
            return
        
        lines = ["━━━━━━━━━━━━━━", "【 背包 】", "━━━━━━━━━━━━━━"]
        for i, item in enumerate(inventory, 1):
            equipped = " [装备中]" if item.get("equipped") else ""
            lines.append(f"{i}. {item.get('name', item.get('id', '未知'))}{equipped}")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("使用: /背包 使用/装备 序号")
        
        yield event.plain_result("\n".join(lines))
    
    # ========== 股市 ==========
    @filter.command("股市")
    async def stock_cmd(event: AstrMessageEvent):
        from modules.stock import format_stock_list, get_user_stocks, trade_stock
        
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        _, args = plugin._parser.parse(event)
        
        if not args:
            yield event.plain_result(f"📈 股市行情:\\n━━━━━━━━━━━━━━\\n{format_stock_list()}\\n━━━━━━━━━━━━━━\\n操作: /股市 买/卖 股票代码 数量")
            return
        
        action = args[0]
        code = args[1] if len(args) > 1 else None
        amount = int(args[2]) if len(args) > 2 else 1
        
        if action == "买" and code:
            success, msg = trade_stock(user, code, amount, "buy")
            if success:
                plugin._store.update_user(user_id, user)
            yield event.plain_result(msg)
        elif action == "卖" and code:
            success, msg = trade_stock(user, code, amount, "sell")
            if success:
                plugin._store.update_user(user_id, user)
            yield event.plain_result(msg)
        elif action == "持股":
            stocks = get_user_stocks(user)
            if not stocks:
                yield event.plain_result("📋 你目前没有持股")
            else:
                lines = ["━━━━━━━━━━━━━━", "【 我的持股 】", "━━━━━━━━━━━━━━"]
                for c, info in stocks.items():
                    lines.append(f"• {c}: {info['amount']}股 (成本{info['avg_price']})")
                yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result("📈 股市操作:\\n━━━━━━━━━━━━━━\\n• /股市 - 查看行情\\n• /股市 买 代码 数量\\n• /股市 卖 代码 数量\\n• /股市 持股\\n━━━━━━━━━━━━━━")
    
    # ========== 取消 ==========
    @filter.command("取消")
    async def cancel(event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n先输入 /签到 注册")
            return
        
        if user["status"] == UserStatus.FREE:
            yield event.plain_result("📋 你当前没有进行任何动作")
            return
        
        old_status = user.get("status", "动作")
        user["status"] = UserStatus.FREE
        user["locked_until"] = None
        user["current_action"] = None
        user["action_detail"] = None
        plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success(f"✅ 已取消 {old_status}，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(f"✅ 已取消 {old_status}，返回空闲状态")
    
    # ========== 帮助 ==========
    @filter.command("帮助")
    async def help_cmd(event: AstrMessageEvent):
        try:
            url = await plugin._renderer.render_help(event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("""
━━━━━━━━━━━━━━
【 牛马人生 - 指令帮助 】
━━━━━━━━━━━━━━

📌 基础
/签到 - 每日签到 (自动注册)
/档案 - 查看档案
/帮助 - 显示帮助

💼 工作
/打工 [工作名] [小时] - 开始工作
例如: /打工 外卖 4

📚 学习
/学习 [课程名] [小时] - 开始学习
例如: /学习 编程 4

🎮 娱乐
/娱乐 [名称] [小时] - 开始娱乐
例如: /娱乐 游戏 2

🍖 生活
/吃 [食物名] - 吃东西
例: /吃 泡面

🏠 住所
/住 - 查看当前住所
/住 租/买 名称 - 租房/买房

📦 其他
/背包 - 查看背包
/股市 - 股市行情
/取消 - 取消当前动作

💡 提示: 0点-8点空闲时自动睡眠
━━━━━━━━━━━━━━
""")


# ========== 辅助函数 ==========

def _format_job_list() -> str:
    return "\n".join([f"{i}. {'💪' if j.get('type')=='体力' else '🧠'} {n} {j['hourly_wage']}金/时" for i, (n, j) in enumerate(JOBS.items(), 1)])


def _format_course_list() -> str:
    return "\n".join([f"{i}. 📚 {n} {c.get('cost', 0)}金/时" for i, (n, c) in enumerate(COURSES.items(), 1)])


def _format_entertainment_list() -> str:
    items = list(ENTERTAINMENTS.items())[:8]
    return "\n".join([f"{i}. 🎮 {n} {e.get('cost_per_hour', 0)}金/时" for i, (n, e) in enumerate(items, 1)])


def _format_food_list() -> str:
    items = list(FOODS.items())[:8]
    return "\n".join([f"• {n} {f['price']}金 (+{f.get('restore_satiety', 0)}饱食)" for n, f in items])


def _format_profile_text(user: dict) -> str:
    attrs = user.get("attributes", {})
    checkin = user.get("checkin", {})
    last_luck = checkin.get("last_luck", 50)
    
    luck_emoji = "🎲"
    luck_name = "普通人"
    if last_luck >= 90:
        luck_emoji, luck_name = "🤑", "超级欧皇"
    elif last_luck >= 70:
        luck_emoji, luck_name = "😄", "欧皇"
    elif last_luck <= 10:
        luck_emoji, luck_name = "💀", "超级非酋"
    elif last_luck <= 30:
        luck_emoji, luck_name = "😣", "非酋"
    
    buffs = checkin.get("active_buffs", [])
    buff_text = f"({len(buffs)}个Buff)" if buffs else ""
    
    return (
        f"━━━━━━━━━━━━━━\\n"
        f"【 牛马档案 】\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"👤 {user.get('nickname', '未知')}\\n"
        f"💰 {user.get('gold', 0)}金币\\n"
        f"🏠 {user.get('residence', '桥下')}\\n"
        f"📋 {user.get('status', '空闲')}\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"❤️ {attrs.get('health', 0)} 💪 {attrs.get('strength', 0)}\\n"
        f"⚡ {attrs.get('energy', 0)} 😊 {attrs.get('mood', 0)}\\n"
        f"🍖 {attrs.get('satiety', 0)}\\n"
        f"━━━━━━━━━━━━━━\\n"
        f"🔥 连续签到: {checkin.get('streak', 0)}天\\n"
        f"{luck_emoji} {luck_name} {buff_text}\\n"
        f"━━━━━━━━━━━━━━"
    )
