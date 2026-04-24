"""
基础指令
注册、档案、状态、帮助
"""

from astrbot.api.event import filter, AstrMessageEvent
from modules.constants import INITIAL_GOLD


def register_basic_commands(plugin):
    """注册基础指令"""
    
    @filter.command("我要当牛马")
    async def register(event: AstrMessageEvent):
        """注册游戏账号"""
        user_id = str(event.get_sender_id())
        nickname = event.get_sender_name()
        
        existing = plugin._store.get_user(user_id)
        if existing:
            try:
                url = await plugin._renderer.render_error(
                    "已注册",
                    "你已经是牛马了！\\n使用 /档案 查看状态",
                    event
                )
                yield event.image_result(url)
            except Exception:
                yield event.plain_result("📋 你已经是牛马了！\\n使用 /档案 查看你的状态")
            return
        
        user = plugin._store.create_user(user_id, nickname)
        
        try:
            url = await plugin._renderer.render_success(
                f"🎉 欢迎加入牛马人生！\\n\\n"
                f"你将从桥下开始，通过打工赚钱、学习技能、购买房产，最终实现人生逆袭！\\n\\n"
                f"💰 金币: {INITIAL_GOLD}\\n"
                f"🏠 住所: 桥下\\n"
                f"📋 技能: 苦力 Lv.1\\n\\n"
                f"输入 /档案 查看状态\\n"
                f"输入 /帮助 查看指令",
                event
            )
            yield event.image_result(url)
        except Exception:
            yield event.plain_result(
                f"🎉 欢迎加入牛马人生！\\n\\n"
                f"你将从桥下开始，通过打工赚钱、学习技能、购买房产，最终实现人生逆袭！\\n\\n"
                f"━━━━━━━━━━━━━━\\n"
                f"「 初始状态 」\\n"
                f"💰 金币: {INITIAL_GOLD}\\n"
                f"🏠 住所: 桥下\\n"
                f"📋 技能: 苦力 Lv.1\\n"
                f"━━━━━━━━━━━━━━\\n\\n"
                f"输入 /档案 查看你的状态\\n"
                f"输入 /帮助 查看所有指令"
            )
    
    @filter.command("档案")
    async def profile(event: AstrMessageEvent):
        """查看个人档案"""
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            try:
                url = await plugin._renderer.render_error(
                    "未注册",
                    "你还没有注册！\\n输入「我要当牛马」开始游戏",
                    event
                )
                yield event.image_result(url)
            except Exception:
                yield event.plain_result("📋 你还没有注册！\\n输入「我要当牛马」开始游戏")
            return
        
        try:
            url = await plugin._renderer.render_profile(user, event)
            yield event.image_result(url)
        except Exception as e:
            output = plugin._format_profile(user)
            warnings = plugin._check_attributes_effects(user)
            if warnings:
                output += "\\n" + "\\n".join(warnings)
            yield event.plain_result(output)
    
    @filter.command("状态")
    async def status(event: AstrMessageEvent):
        """查看当前状态"""
        user_id = str(event.get_sender_id())
        user = plugin._store.get_user(user_id)
        
        if not user:
            try:
                url = await plugin._renderer.render_error(
                    "未注册",
                    "你还没有注册！\\n输入「我要当牛马」开始游戏",
                    event
                )
                yield event.image_result(url)
            except Exception:
                yield event.plain_result("📋 你还没有注册！\\n输入「我要当牛马」开始游戏")
            return
        
        try:
            url = await plugin._renderer.render_status(user, event)
            yield event.image_result(url)
        except Exception:
            lines = [
                "━━━━━━━━━━━━━━",
                "「 当 前 状 态 」",
                "━━━━━━━━━━━━━━",
                f"📋 状态: {user['status']}",
                f"💰 金币: {user['gold']}",
                f"🏠 住所: {user['residence']}",
                "━━━━━━━━━━━━━━",
                plugin._format_attributes(user["attributes"]),
                "━━━━━━━━━━━━━━",
            ]
            yield event.plain_result("\\n".join(lines))
    
    @filter.command("帮助")
    async def help(event: AstrMessageEvent):
        """显示帮助信息"""
        try:
            url = await plugin._renderer.render_help(event)
            yield event.image_result(url)
        except Exception:
            yield event.plain_result("""
━━━━━━━━━━━━━━
「 牛马人生 - 指令帮助 」
━━━━━━━━━━━━━━

📌 基础指令
/我要当牛马 - 注册游戏账号
/档案 - 查看个人档案
/状态 - 查看当前状态
/帮助 - 查看本帮助

📌 每日签到
/签到 - 每日签到 (1-100金币+欧气评级)
/签到统计 - 查看签到累计数据
/我的buff - 查看当前生效buff

📌 工作指令
/工作列表 - 查看可接工作
/打工 <工作> <小时> - 开始工作
/取消工作 - 取消当前工作

📌 学习指令
/课程列表 - 查看可学习课程
/学习 <课程> <小时> - 开始学习
/取消学习 - 取消当前学习

📌 娱乐指令
/娱乐列表 - 查看可参与娱乐
/娱乐 <名称> <小时> - 开始娱乐
/取消娱乐 - 取消当前娱乐

📌 生活指令
/食物列表 - 查看可购买食物
/吃 <食物> - 购买食用
/睡觉 - 开始睡眠

━━━━━━━━━━━━━━
""")
