"""
帮助命令逻辑
"""
from astrbot.api.event import AstrMessageEvent


async def run_help_logic(event: AstrMessageEvent, renderer):
    """帮助命令逻辑"""
    try:
        url = await renderer.render_help(event)
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
/学习              - 显示推荐机构
/学习 查询      - 查看所有机构
/学习 查询#名称 - 查询机构/技能
/学习 课程名   - 开始学习
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
