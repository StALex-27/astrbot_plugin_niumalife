"""
工作相关指令
工作列表、打工、取消工作
"""

from datetime import datetime, timezone, timedelta
from astrbot.api.event import filter, AstrMessageEvent

from modules.constants import JOBS, MAX_ATTRIBUTE
from modules.user import UserStatus
from modules.tick import TickType, ActionDetail
from modules.item import calc_equipped_effects


LOCAL_TZ = timezone(timedelta(hours=8))


def register_work_commands(plugin):
    """注册工作相关指令"""
    
    @filter.command("工作列表")
    async def job_list(event: AstrMessageEvent):
        """查看可接工作"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n输入「我要当牛马」开始游戏")
            return
        
        try:
            url = await plugin._renderer.render_job_list(JOBS, user, event)
            yield event.image_result(url)
        except Exception:
            lines = ["━━━━━━━━━━━━━━", "「 工 作 列 表 」", "━━━━━━━━━━━━━━"]
            for job_name, job in JOBS.items():
                skill_req = ", ".join([f"{k}Lv.{v}" for k, v in job["skill_required"].items()])
                lines.append(
                    f"【{job_name}】{job['type']} | {job['hourly_wage']}金/时 | "
                    f"体力消耗{job['consume_strength']} | 技能:{skill_req} | {job['difficulty']}"
                )
            lines.append("━━━━━━━━━━━━━━")
            lines.append("使用 /打工 <工作名> <小时> 开始工作")
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("打工")
    async def start_work(event: AstrMessageEvent):
        """开始工作"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！\\n输入「我要当牛马」开始游戏")
            return
        
        if user["status"] != UserStatus.FREE:
            yield event.plain_result(f"📋 你正在{user['status']}，无法工作\\n先输入 /取消工作 或 /取消睡觉")
            return
        
        _, args = plugin._parser.parse(event)
        
        if len(args) < 2:
            yield event.plain_result("📋 格式：/打工 <工作名> <小时>\\n例如：/打工 搬砖 4")
            return
        
        job_name = args[0]
        success, hours, err = plugin._parser.get_range(args, 1, 1, 8)
        if not success:
            yield event.plain_result(f"📋 {err}")
            return
        
        job = JOBS.get(job_name)
        if not job:
            yield event.plain_result(f"📋 不存在该工作：{job_name}\\n使用 /工作列表 查看可接工作")
            return
        
        if not plugin._check_skill_required(user["skills"], job["skill_required"]):
            skill_req = ", ".join([f"{k}Lv.{v}" for k, v in job["skill_required"].items()])
            yield event.plain_result(f"📋 技能不足！需要：{skill_req}")
            return
        
        enough, reason = plugin._check_attribute_enough(user["attributes"], job, hours)
        if not enough:
            yield event.plain_result(f"📋 {reason}，无法工作")
            return
        
        # 计算装备效果（减少工作时长）
        effects = calc_equipped_effects(user)
        work_time_reduce = effects.get("work_time_reduce", 0)  # 百分比
        effective_hours = hours * (1 - work_time_reduce / 100)
        
        # 使用新的ActionDetail结构
        now = datetime.now(LOCAL_TZ)
        detail = ActionDetail.create(
            action_type=TickType.WORK,
            hours=effective_hours,
            start_time=now,
            job_name=job_name,
            hourly_wage=job["hourly_wage"],
            consume_strength=job["consume_strength"],
            consume_energy=job["consume_energy"],
            consume_mood=job["consume_mood"],
            consume_health=job["consume_health"],
            consume_satiety=job["consume_satiety"]
        )
        
        user["status"] = UserStatus.WORKING
        user["current_action"] = TickType.WORK
        user["action_detail"] = detail
        
        await plugin._store.update_user(user_id, user)
        
        # 计算预计收益（包含装备加成）
        effects = calc_equipped_effects(user)
        work_income_bonus = effects.get("work_income_bonus", 0)
        
        lines = [
            "━━━━━━━━━━━━━━",
            "「 开 始 工 作 」",
            "━━━━━━━━━━━━━━",
            f"📋 工作：{job_name}",
            f"⏰ 时长：{hours} 小时",
            f"💰 预计收益：{int(job['hourly_wage'] * hours * (1 + work_income_bonus/100))} 金币",
        ]
        
        # 显示装备加成信息
        if work_time_reduce > 0 or work_income_bonus > 0:
            lines.append(f"🎒 装备加成：工作时长-{work_time_reduce:.0f}%，收入+{work_income_bonus:.0f}%")
        
        lines.append("━━━━━━━━━━━━━━")
        lines.append("「 消耗预估 」")
        lines.append(f"💪 体力：-{job['consume_strength'] * hours}")
        lines.append(f"⚡ 精力：-{job['consume_energy'] * hours}")
        lines.append(f"😊 心情：-{job['consume_mood'] * hours}")
        lines.append(f"🍖 饱食：-{int(job['consume_satiety'] * hours * 0.5)}")
        lines.append("━━━━━━━━━━━━━━")
        
        try:
            emoji = "💪" if job.get("type") == "体力" else "🧠"
            url = await plugin._renderer.render_job_start(
                user, event,
                job_name=job_name,
                job_emoji=emoji,
                hours=hours,
                expected_gold=job['hourly_wage'] * hours,
                expected_exp=0,
                consume_strength=job['consume_strength'] * hours,
                consume_energy=job['consume_energy'] * hours,
                consume_satiety=int(job['consume_satiety'] * hours * 0.5)
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("取消工作")
    async def cancel_work(event: AstrMessageEvent):
        """取消工作"""
        user_id = str(event.get_sender_id())
        user = await plugin._store.get_user(user_id)
        
        if not user:
            yield event.plain_result("📋 你还没有注册！")
            return
        
        if user["status"] != UserStatus.WORKING:
            yield event.plain_result("📋 你当前没有在进行工作")
            return
        
        user["status"] = UserStatus.FREE
        user["locked_until"] = None
        user["current_action"] = None
        user["action_detail"] = None
        await plugin._store.update_user(user_id, user)
        
        try:
            url = await plugin._renderer.render_success("✅ 已取消工作，返回空闲状态", event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("📋 已取消工作，返回空闲状态")
