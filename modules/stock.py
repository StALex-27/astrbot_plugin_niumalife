"""
股票系统模块 v2
包含趋势系统、事件触发、买卖交易等
"""
import json
import random
from pathlib import Path
from typing import Optional

# 延迟导入避免循环依赖
def _update_daily(user: dict, key: str, val):
    from .user import update_daily_stat, update_lifetime_stat
    update_daily_stat(user, key, val)

def _update_lifetime(user: dict, key: str, val):
    from .user import update_lifetime_stat
    update_lifetime_stat(user, key, val)

# 从 constants.py 复用单一数据源
from .constants import STOCKS

STOCK_CODE_TO_NAME = {info["code"]: name for name, info in STOCKS.items()}
STOCK_NAME_TO_CODE = {name: info["code"] for name, info in STOCKS.items()}

# 股票事件（已简化，不再用于决定价格方向）
STOCK_EVENTS = {
    "暴涨": {"change": 0.08, "msg": "📈 {} 传来利好，股价暴涨！"},
    "大涨": {"change": 0.04, "msg": "📈 {} 业绩增长，股价大涨！"},
    "小涨": {"change": 0.015, "msg": "📊 {} 股价小幅上涨"},
    "横盘": {"change": 0.0,  "msg": "➖ {} 股价保持稳定"},
    "小跌": {"change": -0.015, "msg": "📉 {} 股价小幅下跌"},
    "大跌": {"change": -0.04, "msg": "📉 {} 业绩下滑，股价大跌！"},
    "暴跌": {"change": -0.08, "msg": "🚨 {} 传来重大利空，股价暴跌！"},
}


class StockTrend:
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"


def init_stock_trend(stock_name: str, stock_info: dict) -> dict:
    """初始化一只股票的趋势数据
    
    Returns:
        dict: 趋势数据 {direction, remaining_hours, amplitude, accumulated}
    """
    amplitude = random.uniform(
        stock_info.get("trend_amplitude_min", 0.08),
        stock_info.get("trend_amplitude_max", 0.20)
    )
    direction = 1 if random.random() >= 0.5 else -1
    remaining_hours = random.randint(
        stock_info.get("trend_hours_min", 20),
        stock_info.get("trend_hours_max", 80)
    )
    return {
        "direction": direction,
        "remaining_hours": remaining_hours,
        "amplitude": amplitude,
        "accumulated": 0.0  # 已累计的趋势贡献
    }


def update_stock_price(
    stock_name: str,
    stock_info: dict,
    current_price: float,
    current_trend: dict,
    is_trading_hour: bool
) -> tuple[float, dict, str]:
    """
    更新单只股票价格
    
    公式: 价格变动 = 基础随机幅度 + 趋势贡献 + 随机事件
    
    Args:
        stock_name: 股票名称
        stock_info: 股票配置
        current_price: 当前价格
        current_trend: 当前趋势数据
        is_trading_hour: 是否在交易时段
    
    Returns:
        tuple[新价格, 新趋势, 事件消息]
    """
    if not is_trading_hour:
        # 休盘中，价格不变
        return current_price, current_trend, "⏸️ 休市中"

    volatility = stock_info.get("volatility", 0.10)
    daily_limit = stock_info.get("daily_limit", 0.10)

    # 1. 基础随机幅度: ±(volatility * 20%)  per hour
    base_random = random.uniform(-volatility * 0.2, volatility * 0.2)

    # 2. 趋势贡献: 方向 × (幅度 / 剩余小时)
    trend_contribution = 0.0
    new_trend = dict(current_trend)
    msg = ""

    if current_trend.get("remaining_hours", 0) > 0:
        remaining = current_trend["remaining_hours"]
        amplitude = current_trend["amplitude"]
        direction = current_trend["direction"]
        # 每小时贡献
        trend_contribution = direction * (amplitude / remaining) if remaining > 0 else 0.0
        # 累加到已累计贡献
        new_trend["accumulated"] = current_trend.get("accumulated", 0) + trend_contribution
        # 剩余小时-1
        new_trend["remaining_hours"] = remaining - 1
    else:
        # 趋势已结束，重新生成
        new_trend = init_stock_trend(stock_name, stock_info)

    # 3. 随机事件 (20% 概率触发)
    event_change = 0.0
    if random.random() < 0.20:
        events = list(STOCK_EVENTS.keys())
        weights = [0.02, 0.08, 0.25, 0.30, 0.25, 0.08, 0.02]
        chosen = random.choices(events, weights=weights)[0]
        event_info = STOCK_EVENTS[chosen]
        event_change = event_info["change"]
        msg = event_info["msg"].format(stock_name)
        
        # 事件有 30% 概率终结当前趋势
        if random.random() < 0.30 and current_trend.get("remaining_hours", 0) > 0:
            new_trend = init_stock_trend(stock_name, stock_info)
            msg += " (趋势被打破！)"
    else:
        msg = "📊 {} 盘中微调".format(stock_name)

    # 计算总变动率
    total_change_rate = base_random + trend_contribution + event_change
    
    # 涨跌停限制
    new_price = current_price * (1 + total_change_rate)
    base_price = stock_info.get("base_price", 100)
    upper_limit = base_price * (1 + daily_limit)
    lower_limit = base_price * (1 - daily_limit)
    new_price = max(lower_limit, min(upper_limit, new_price))

    return new_price, new_trend, msg


def is_trading_hour(now_hour: int) -> bool:
    """判断是否在交易时段 (8:00-20:00)"""
    return 8 <= now_hour < 20


def get_stock_trend(price_history: list[float]) -> str:
    """根据价格历史判断趋势"""
    if len(price_history) < 2:
        return StockTrend.STABLE
    first = price_history[0]
    last = price_history[-1]
    change_rate = (last - first) / first
    if change_rate > 0.02:
        return StockTrend.RISING
    elif change_rate < -0.02:
        return StockTrend.FALLING
    return StockTrend.STABLE


def get_stock_by_code(code: str) -> Optional[tuple[str, dict]]:
    """根据代码查找股票"""
    name = STOCK_CODE_TO_NAME.get(code.upper())
    if name:
        return name, STOCKS[name]
    return None


def format_stock_info(stock_data: dict) -> str:
    """格式化股票信息"""
    name = stock_data.get("name", "未知")
    code = stock_data.get("code", "")
    price = stock_data.get("price", 0)
    trend = stock_data.get("trend", StockTrend.STABLE)
    trend_symbol = {"rising": "📈", "falling": "📉", "stable": "➖"}.get(trend, "➖")
    return f"{trend_symbol} {name}({code}) ¥{price:.2f}"


def trade_stock(
    user: dict,
    stock_name: str,
    stock_code: str,
    amount: int,
    current_price: float,
    action: str
) -> tuple[bool, str]:
    """执行股票买卖"""
    if amount <= 0:
        return False, "📋 数量必须大于0"

    holdings = user.setdefault("stock_holdings", {})

    if action == "buy":
        total_cost = current_price * amount
        if user.get("gold", 0) < total_cost:
            return False, f"📋 金币不足！需要 {total_cost:.0f} 金币，现有 {user.get('gold', 0):.0f}"

        user["gold"] -= total_cost

        if stock_name in holdings:
            old_amount = holdings[stock_name]["amount"]
            old_avg = holdings[stock_name]["avg_price"]
            new_amount = old_amount + amount
            new_avg = (old_avg * old_amount + current_price * amount) / new_amount
            holdings[stock_name] = {"amount": new_amount, "avg_price": new_avg}
        else:
            holdings[stock_name] = {"amount": amount, "avg_price": current_price}

        # 记录统计
        _update_lifetime(user, "total_gold_spent", total_cost)
        _update_daily(user, "gold_spent", total_cost)
        _update_daily(user, "stock_trades", 1)
        _update_lifetime(user, "total_stock_trades", 1)
        
        return True, (
            f"✅ 买入成功！\n"
            f"━━━━━━━━━━━━━━\n"
            f"📈 {stock_name}({stock_code})\n"
            f"💰 买入: {amount}股 @ ¥{current_price:.2f}\n"
            f"💵 花费: {total_cost:.0f} 金币\n"
            f"💳 余额: {user['gold']:.0f} 金币\n"
            f"━━━━━━━━━━━━━━"
        )

    elif action == "sell":
        if stock_name not in holdings:
            return False, f"📋 你没有持有 {stock_name}，无法卖出"

        holding = holdings[stock_name]
        if holding["amount"] < amount:
            return False, f"📋 持股不足！你持有 {holding['amount']} 股，卖出 {amount} 股"

        total_value = current_price * amount
        profit = total_value - (holding["avg_price"] * amount)
        profit_str = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"

        user["gold"] += total_value

        remaining = holding["amount"] - amount
        if remaining <= 0:
            del holdings[stock_name]
        else:
            holding["amount"] = remaining

        # 记录统计
        if profit >= 0:
            _update_lifetime(user, "total_gold_earned", total_value)
            _update_daily(user, "gold_stock_profit", profit)
        else:
            _update_daily(user, "gold_stock_loss", abs(profit))
        _update_lifetime(user, "total_stock_profit", profit)
        _update_daily(user, "stock_trades", 1)
        _update_lifetime(user, "total_stock_trades", 1)
        
        return True, (
            f"✅ 卖出成功！\n"
            f"━━━━━━━━━━━━━━\n"
            f"📉 {stock_name}({stock_code})\n"
            f"💰 卖出: {amount}股 @ ¥{current_price:.2f}\n"
            f"💵 收入: {total_value:.0f} 金币\n"
            f"📊 盈亏: {profit_str} 金币\n"
            f"💳 余额: {user['gold']:.0f} 金币\n"
            f"━━━━━━━━━━━━━━"
        )

    return False, "📋 无效操作"


def get_user_stocks(user: dict) -> dict:
    """获取用户持股"""
    return user.get("stock_holdings", {})
