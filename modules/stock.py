"""
股票系统模块
包含股票趋势、股票事件触发等
"""
import random
from typing import Optional


class StockTrend:
    """股票趋势枚举"""
    RISING = "rising"      # 上涨
    FALLING = "falling"    # 下跌
    STABLE = "stable"      # 稳定


# 股票事件类型
STOCK_EVENTS = {
    "暴涨": {"change": 0.15, "msg": "📈 {} 传来利好消息，股价暴涨！"},
    "大涨": {"change": 0.08, "msg": "📈 {} 业绩增长，股价大涨！"},
    "小涨": {"change": 0.03, "msg": "📊 {} 股价小幅上涨"},
    "横盘": {"change": 0.0, "msg": "➖ {} 股价保持稳定"},
    "小跌": {"change": -0.03, "msg": "📉 {} 股价小幅下跌"},
    "大跌": {"change": -0.08, "msg": "📉 {} 业绩下滑，股价大跌！"},
    "暴跌": {"change": -0.15, "msg": "🚨 {} 传来重大利空，股价暴跌！"},
}


def trigger_stock_event(stock_name: str, current_price: float) -> tuple[float, str]:
    """触发股票随机事件
    
    Args:
        stock_name: 股票名称
        current_price: 当前价格
    
    Returns:
        tuple[float, str]: (新价格, 事件消息)
    """
    # 事件权重：横盘最常见，暴涨暴跌最少见
    event_weights = {
        "暴涨": 0.02,
        "大涨": 0.08,
        "小涨": 0.20,
        "横盘": 0.30,
        "小跌": 0.20,
        "大跌": 0.08,
        "暴跌": 0.02,
    }
    
    # 根据权重选择事件
    events = list(event_weights.keys())
    weights = list(event_weights.values())
    chosen_event = random.choices(events, weights=weights)[0]
    
    event_info = STOCK_EVENTS[chosen_event]
    change_rate = event_info["change"]
    new_price = current_price * (1 + change_rate)
    
    # 限制价格范围（1-10000）
    new_price = max(1.0, min(10000.0, new_price))
    
    return new_price, event_info["msg"].format(stock_name)


def get_stock_trend(price_history: list[float]) -> str:
    """根据价格历史判断趋势
    
    Args:
        price_history: 价格历史列表
    
    Returns:
        str: 趋势类型
    """
    if len(price_history) < 2:
        return StockTrend.STABLE
    
    first = price_history[0]
    last = price_history[-1]
    change_rate = (last - first) / first
    
    if change_rate > 0.05:
        return StockTrend.RISING
    elif change_rate < -0.05:
        return StockTrend.FALLING
    else:
        return StockTrend.STABLE


def format_stock_info(stock_data: dict) -> str:
    """格式化股票信息显示
    
    Args:
        stock_data: 股票数据
    
    Returns:
        str: 格式化的股票信息
    """
    name = stock_data.get("name", "未知")
    code = stock_data.get("code", "")
    price = stock_data.get("price", 0)
    trend = stock_data.get("trend", StockTrend.STABLE)
    
    trend_symbol = {"rising": "📈", "falling": "📉", "stable": "➖"}.get(trend, "➖")
    
    return f"{trend_symbol} {name}({code}) ¥{price:.2f}"