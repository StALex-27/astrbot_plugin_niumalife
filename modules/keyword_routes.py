"""
牛马人生关键词路由表
注册所有可以在群聊中通过纯文触发的指令
"""
from .keyword_trigger import KeywordRoute, KeywordRouter

# 所有触发词 -> action 映射
# action 名称与 main.py 中的命令方法名一致
_KEYWORD_ROUTES = (
    # 基础动作
    KeywordRoute(keyword="档案", action="profile"),
    KeywordRoute(keyword="打工", action="work"),
    KeywordRoute(keyword="学习", action="learn"),
    KeywordRoute(keyword="娱乐", action="entertain"),
    KeywordRoute(keyword="吃", action="eat"),
    KeywordRoute(keyword="签到", action="checkin"),
    KeywordRoute(keyword="住", action="residence_cmd"),
    KeywordRoute(keyword="装备", action="equip_cmd"),
    KeywordRoute(keyword="背包", action="backpack"),
    KeywordRoute(keyword="商店", action="shop_cmd"),
    KeywordRoute(keyword="买", action="buy_cmd"),
    KeywordRoute(keyword="购买", action="buy_cmd"),
    KeywordRoute(keyword="购入", action="buy_cmd"),
    KeywordRoute(keyword="入手", action="buy_cmd"),
    KeywordRoute(keyword="股市", action="stock_cmd"),
    KeywordRoute(keyword="取消", action="cancel"),
    KeywordRoute(keyword="帮助", action="help_cmd"),

    # 委托系统
    KeywordRoute(keyword="我的委托", action="my_jobs"),
    KeywordRoute(keyword="完成委托", action="complete_job_cmd"),
    KeywordRoute(keyword="取消委托", action="cancel_job_cmd"),

    # 设置
    KeywordRoute(keyword="设置", action="settings_cmd"),

    # 钓鱼
    KeywordRoute(keyword="钓鱼", action="fishing_cmd"),
    KeywordRoute(keyword="渔具", action="fishing_gear_cmd"),
    KeywordRoute(keyword="装渔具", action="fishing_gear_cmd"),
    KeywordRoute(keyword="鱼塘", action="fish_dex_cmd"),

    # 交易
    KeywordRoute(keyword="卖", action="sell_cmd"),
    KeywordRoute(keyword="/卖", action="sell_cmd"),  # 兼容带斜杠写法

    # 附魔
    KeywordRoute(keyword="附魔", action="enchant_cmd"),
    KeywordRoute(keyword="使用", action="use_cmd"),
)

# 全局路由器实例（懒加载）
_router: KeywordRouter | None = None


def get_keyword_router() -> KeywordRouter:
    """获取关键词路由器单例"""
    global _router
    if _router is None:
        _router = KeywordRouter(routes=_KEYWORD_ROUTES)
    return _router
