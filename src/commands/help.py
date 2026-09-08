"""帮助命令逻辑"""
from astrbot.api.event import AstrMessageEvent


_HELP_FALLBACK = """
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

⚙️ 设置
/设置 - 查看当前设置
/设置 通知开 / 通知关
/设置 通知样式 smart|always|never
/设置 订阅个人日报 - 开启个人日报

💡 提示: 0点-8点空闲时自动睡眠
━━━━━━━━━━━━━━
"""


async def run_help_logic(event: AstrMessageEvent, sender):
    """帮助命令逻辑

    9/6: 改用 sender.send_card() 替代 try/except 样板。
    """
    async for r in sender.send_card(
        event, "help",
        {},  # render_help 不需要外部 data
        fallback_text=_HELP_FALLBACK,
    ):
        yield r
