"""
学习相关指令
课程列表、学习、取消学习
"""

from datetime import datetime, timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent

from modules.constants import COURSES, MAX_ATTRIBUTE
from modules.user import UserStatus
from modules.tick import TickType, ActionDetail


LOCAL_TZ = timezone(timedelta(hours=8))


def register_learn_commands(plugin):
    """注册学习相关指令"""
    
    @filter.command("课程列表")
    async def course_list(event: AstrMessageEvent):
        """查看可学习课程"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        try:
            url = await plugin._renderer.render_course_list(COURSES, user, event)
            yield event.image_result(url)
        except Exception:
            lines = ["━━━━━━━━━━━━━━", "「 课 程 列 表 」", "━━━━━━━━━━━━━━"]
            for course_name, course in COURSES.items():
                skill_req = ", ".join([f"{k}Lv.{v}" for k, v in course.get("skill_required", {}).items()])
                lines.append(
                    f"【{course_name}】{course.get('type', '通用')} | "
                    f"💰 {course.get('cost', 0)}金/时 | "
                    f"📚 经验{course.get('exp_per_hour', 10)}/时 | "
                    f"技能:{skill_req or '无'}"
                )
            lines.append("━━━━━━━━━━━━━━")
            lines.append("使用 /学习 <课程名> <小时> 开始学习")
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("学习")
    async def start_learn(event: AstrMessageEvent):
        """开始学习"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法学习\\n先输入 /取消工作 或 /取消睡觉")
            return
        
        _, args = plugin._parser.parse(event)
        
        if len(args) < 2:
            yield event.plain_result("📋 格式：/学习 <课程名> <小时>\\n例如：/学习 编程入门 4")
            return
        
        course_name = args[0]
        success, hours, err = plugin._parser.get_range(args, 1, 1, 8)
        if not success:
            yield event.plain_result(f"📋 {err}")
            return
        
        course = COURSES.get(course_name)
        if not course:
            yield event.plain_result(f"📋 不存在该课程：{course_name}\\n使用 /课程列表 查看")
            return
        
        # 检查属性
        attrs = user["attributes"]
        if attrs["strength"] < course.get("consume_strength", 3) * hours * 0.5:
            yield event.plain_result("📋 体力不足，无法学习")
            return
        if attrs["energy"] < course.get("consume_energy", 8) * hours * 0.5:
            yield event.plain_result("📋 精力不足，无法学习")
            return
        if attrs["satiety"] < 10:
            yield event.plain_result("📋 饱食度过低，先吃点东西吧")
            return
        
        # 使用ActionDetail
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
        
        await plugin._store.update_user(user_id, user)
        
        lines = [
            "━━━━━━━━━━━━━━",
            "「 开 始 学 习 」",
            "━━━━━━━━━━━━━━",
            f"📚 课程：{course_name}",
            f"⏰ 时长：{hours} 小时",
            f"📚 预计经验：{course.get('exp_per_hour', 10) * hours}",
            "━━━━━━━━━━━━━━",
            "「 消耗预估 」",
            f"💪 体力：-{int(course.get('consume_strength', 3) * hours)}",
            f"⚡ 精力：-{int(course.get('consume_energy', 8) * hours)}",
            f"😊 心情：-{course.get('consume_mood', 5) * hours}",
            "━━━━━━━━━━━━━━",
        ]
        
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
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("取消学习")
    async def cancel_learn(event: AstrMessageEvent):
        """取消学习"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.LEARNING:
            yield event.plain_result("📋 你当前没有在学习")
            return
        
        user["status"] = UserStatus.FREE
        user["locked_until"] = None
        user["current_action"] = None
        user["action_detail"] = None
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success("✅ 已取消学习，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("📋 已取消学习，返回空闲状态")
