"""
设置命令逻辑
"""
from astrbot.api.event import AstrMessageEvent

from ...modules.user import UserStatus


async def run_settings_logic(event: AstrMessageEvent, store, parser, get_group_config, save_group_config):
    """用户设置指令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return
    
    actual_group_id = event.get_group_id() if not event.is_private_chat() else ""
    
    if actual_group_id and actual_group_id not in user.get("groups", []):
        user.setdefault("groups", []).append(actual_group_id)
        await store.update_user(user_id, user)
    
    _, args = parser.parse(event)
    
    settings = user.setdefault("settings", {
        "sub_group_daily": False,
        "sub_personal_daily": False,
        "daily_report_hour": 23,
        "daily_report_minute": 0,
        "notification_enabled": True,
    })
    
    if not args:
        sub_group = "✅ 已开启" if settings.get("sub_group_daily") else "❌ 未开启"
        sub_personal = "✅ 已开启" if settings.get("sub_personal_daily") else "❌ 未开启"
        hour = settings.get("daily_report_hour", 23)
        minute = settings.get("daily_report_minute", 0)
        notif = "📳 开启" if settings.get("notification_enabled") else "🔕 关闭"
        
        lines = [
            "━━━━━━━━━━━━━━",
            "【 ⚙️ 个人设置 】",
            "━━━━━━━━━━━━━━",
            f"📰 群日报订阅: {sub_group}",
            f"📋 个人日报订阅: {sub_personal}",
            f"⏰ 日报时间: {hour:02d}:{minute:02d}",
            f"🔔 通知: {notif}",
            "━━━━━━━━━━━━━━",
            "━━━━━━━━━━━━━━",
            "📖 指令说明:",
            "/设置 订阅群日报 - 开启本群日报",
            "/设置 取消订阅群日报",
            "/设置 订阅个人日报 - 开启个人日报",
            "/设置 取消订阅个人日报",
            "/设置 日报时间 HH:MM - 自定义时间",
            "/设置 通知开/关",
            "━━━━━━━━━━━━━━",
        ]
        
        if actual_group_id:
            group_config = await get_group_config(actual_group_id)
            group_enabled = "✅ 已开启" if group_config.get("enabled") else "❌ 未开启"
            lines.append(f"📢 本群日报: {group_enabled}")
            lines.append("/设置 开启本群日报 - 群管理操作")
        
        yield event.plain_result("\n".join(lines))
        return
    
    action = args[0]
    
    if action == "订阅群日报":
        if not actual_group_id:
            yield event.plain_result("📋 请在群聊中使用此指令！")
            return
        settings["sub_group_daily"] = True
        group_config = await get_group_config(actual_group_id)
        if actual_group_id not in group_config.get("subscribers", []):
            group_config.setdefault("subscribers", []).append(user_id)
        await save_group_config(actual_group_id, group_config)
        await store.update_user(user_id, user)
        yield event.plain_result(f"✅ 已订阅本群日报！\n📅 每日 {settings.get('daily_report_hour',23):02d}:{settings.get('daily_report_minute',0):02d} 接收")
    
    elif action == "取消订阅群日报":
        settings["sub_group_daily"] = False
        if actual_group_id:
            group_config = await get_group_config(actual_group_id)
            if user_id in group_config.get("subscribers", []):
                group_config["subscribers"].remove(user_id)
            await save_group_config(actual_group_id, group_config)
        await store.update_user(user_id, user)
        yield event.plain_result("❌ 已取消订阅本群日报")
    
    elif action == "订阅个人日报":
        settings["sub_personal_daily"] = True
        await store.update_user(user_id, user)
        yield event.plain_result(f"✅ 已开启个人日报！\n📅 每日 {settings.get('daily_report_hour',23):02d}:{settings.get('daily_report_minute',0):02d} 私聊推送")
    
    elif action == "取消订阅个人日报":
        settings["sub_personal_daily"] = False
        await store.update_user(user_id, user)
        yield event.plain_result("❌ 已取消订阅个人日报")
    
    elif action == "日报时间" and len(args) >= 2:
        try:
            time_parts = args[1].split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError()
            settings["daily_report_hour"] = hour
            settings["daily_report_minute"] = minute
            await store.update_user(user_id, user)
            yield event.plain_result(f"✅ 日报时间已调整为 {hour:02d}:{minute:02d}")
        except (ValueError, IndexError):
            yield event.plain_result("📋 格式错误！使用: /设置 日报时间 HH:MM\n例如: /设置 日报时间 21:00")
    
    elif action == "开启本群日报":
        if not actual_group_id:
            yield event.plain_result("📋 请在群聊中使用此指令！")
            return
        group_config = await get_group_config(actual_group_id)
        group_config["enabled"] = True
        await save_group_config(actual_group_id, group_config)
        yield event.plain_result("✅ 本群已开启日报功能\n📅 每日 23:00 自动生成并发送")
    
    elif action == "关闭本群日报":
        if not actual_group_id:
            yield event.plain_result("📋 请在群聊中使用此指令！")
            return
        group_config = await get_group_config(actual_group_id)
        group_config["enabled"] = False
        await save_group_config(actual_group_id, group_config)
        yield event.plain_result("❌ 本群已关闭日报功能")
    
    elif action == "通知开":
        settings["notification_enabled"] = True
        await store.update_user(user_id, user)
        yield event.plain_result("✅ 通知已开启")
    
    elif action == "通知关":
        settings["notification_enabled"] = False
        await store.update_user(user_id, user)
        yield event.plain_result("🔕 通知已关闭")
    
    else:
        yield event.plain_result("📋 无效设置指令！\n━━━━━━━━━━━━━━\n📖 /设置 订阅群日报\n📖 /设置 取消订阅群日报\n📖 /设置 订阅个人日报\n📖 /设置 取消订阅个人日报\n📖 /设置 日报时间 HH:MM\n━━━━━━━━━━━━━━")
