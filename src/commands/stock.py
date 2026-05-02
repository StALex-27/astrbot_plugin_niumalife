"""
股市命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.stock import STOCKS, STOCK_CODE_TO_NAME, is_trading_hour


LOCAL_TZ_STOCK = timezone(timedelta(hours=8))


async def run_stock_logic(event: AstrMessageEvent, store, parser, get_kv_data):
    """股市命令逻辑"""
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)
    
    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return
    
    _, args = parser.parse(event)
    
    if not args:
        now = datetime.now(LOCAL_TZ_STOCK)
        trading = is_trading_hour(now.hour)
        status = "📈 交易中" if trading else "⏸️ 休盘中"
        
        lines = ["═══════════════════════════", f"【 股市行情 】{status}", "═══════════════════════════"]
        lines.append(f"{'代码':<8} {'名称':<8} {'价格':>8}  {'涨跌幅':>8}")
        lines.append("-" * 42)
        
        stocks_data = []
        for name, info in STOCKS.items():
            code = info["code"]
            price_key = f"stock_price:{name}"
            open_key = f"stock_open:{name}"
            current_price = await get_kv_data(price_key, info["base_price"])
            open_price = await get_kv_data(open_key, info["base_price"])
            
            change = (current_price - open_price) / open_price * 100 if open_price > 0 else 0
            if change > 0:
                change_str = f"🔺+{change:.2f}%"
            elif change < 0:
                change_str = f"🔻{change:.2f}%"
            else:
                change_str = f"➖ 0.00%"
            
            stocks_data.append((abs(change), name, code, current_price, change_str))
        
        stocks_data.sort(key=lambda x: x[0], reverse=True)
        
        for _, name, code, price, change_str in stocks_data:
            lines.append(f"{code:<8} {name:<8} ¥{price:>7.2f}  {change_str}")
        
        lines.append("═══════════════════════════")
        lines.append("操作: /股市 买/卖 代码 数量")
        yield event.plain_result("\n".join(lines))
        return
    
    action = args[0]
    code = args[1].upper() if len(args) > 1 else None
    amount = int(args[2]) if len(args) > 2 else 1
    
    if action == "买" and code:
        from ...modules.stock import trade_stock
        stock_name = STOCK_CODE_TO_NAME.get(code)
        if not stock_name:
            yield event.plain_result(f"📋 无效股票代码: {code}\n使用 /股市 查看代码")
            return
        price_key = f"stock_price:{stock_name}"
        current_price = await get_kv_data(price_key, STOCKS[stock_name]["base_price"])
        success, msg = trade_stock(user, stock_name, code, amount, current_price, "buy")
        if success:
            await store.update_user(user_id, user)
        yield event.plain_result(msg)
    elif action == "卖" and code:
        from ...modules.stock import trade_stock
        stock_name = STOCK_CODE_TO_NAME.get(code)
        if not stock_name:
            yield event.plain_result(f"📋 无效股票代码: {code}\n使用 /股市 查看代码")
            return
        price_key = f"stock_price:{stock_name}"
        current_price = await get_kv_data(price_key, STOCKS[stock_name]["base_price"])
        success, msg = trade_stock(user, stock_name, code, amount, current_price, "sell")
        if success:
            await store.update_user(user_id, user)
        yield event.plain_result(msg)
    elif action == "持股":
        holdings = user.get("stock_holdings", {})
        if not holdings:
            yield event.plain_result("📋 你目前没有持股")
        else:
            lines = ["═══════════════════════════", "【 我的持股 】", "═══════════════════════════"]
            total_profit = 0
            for name, info in holdings.items():
                code = STOCKS[name]["code"]
                price_key = f"stock_price:{name}"
                open_key = f"stock_open:{name}"
                current_price = await get_kv_data(price_key, STOCKS[name]["base_price"])
                open_price = await get_kv_data(open_key, STOCKS[name]["base_price"])
                cost = info["avg_price"] * info["amount"]
                value = current_price * info["amount"]
                profit = value - cost
                profit_pct = profit / cost * 100 if cost > 0 else 0
                change = (current_price - open_price) / open_price * 100 if open_price > 0 else 0
                profit_str = f"+{profit:.0f}" if profit >= 0 else f"{profit:.0f}"
                change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
                total_profit += profit
                lines.append(f"{code} {name}: {info['amount']}股")
                lines.append(f"  成本¥{info['avg_price']:.2f} | 现价¥{current_price:.2f} | 今日{change_str}")
                lines.append(f"  盈亏: {profit_str}({profit_pct:+.1f}%)")
            lines.append("═══════════════════════════")
            total_str = f"+{total_profit:.0f}" if total_profit >= 0 else f"{total_profit:.0f}"
            lines.append(f"📊 总盈亏: {total_str}金币")
            yield event.plain_result("\n".join(lines))
    else:
        yield event.plain_result("📈 股市操作:\n═══════════════════════════\n• /股市 - 查看行情\n• /股市 买 代码 数量\n• /股市 卖 代码 数量\n• /股市 持股\n═══════════════════════════")
