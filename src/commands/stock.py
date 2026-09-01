"""
股市命令逻辑
"""
from datetime import datetime, timezone, timedelta

from astrbot.api.event import AstrMessageEvent

from ...modules.stock import STOCKS, STOCK_CODE_TO_NAME, is_trading_hour
from ...modules.renderer import CardRenderer

LOCAL_TZ_STOCK = timezone(timedelta(hours=8))
_card_renderer = CardRenderer()


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
            
            stocks_data.append({
                "name": name,
                "code": code,
                "price": f"{current_price:.2f}",
                "change_str": change_str,
                "change_val": change,
            })
        
        stocks_data.sort(key=lambda x: x["change_val"], reverse=True)
        
        for s in stocks_data:
            del s["change_val"]
        
        try:
            card_url = await _card_renderer.render_stock_market(stocks_data, user, event, status)
            yield event.image_result(card_url)
        except RuntimeError as e:
            if "All endpoints failed" in str(e):
                lines = [f"📈 {user.get('nickname', '未知')} 的股票行情"]
                for s in stocks_data:
                    lines.append(f"{s['name']}({s['code']}) ¥{s['price']} {s['change_str']}")
                lines.append(f"\n💰 金币: {int(user.get('gold', 0))}")
                lines.append("使用 /股市 买/卖 代码 数量")
                yield event.plain_result("\n".join(lines))
            else:
                raise
    
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
            try:
                card_url = await _card_renderer.render_stock_holdings([], user, event, 0)
                yield event.image_result(card_url)
            except RuntimeError as e:
                if "All endpoints failed" in str(e):
                    yield event.plain_result("📊 你目前没有持股")
                else:
                    raise
        else:
            holdings_data = []
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
                
                holdings_data.append({
                    "name": name,
                    "code": code,
                    "amount": info["amount"],
                    "cost_price": f"{info['avg_price']:.2f}",
                    "current_price": f"{current_price:.2f}",
                    "profit": profit,
                    "profit_str": profit_str,
                    "profit_pct_str": f"{profit_pct:+.1f}%",
                    "today_change": change,
                    "today_change_str": change_str,
                })
            
            try:
                card_url = await _card_renderer.render_stock_holdings(holdings_data, user, event, int(total_profit))
                yield event.image_result(card_url)
            except RuntimeError as e:
                if "All endpoints failed" in str(e):
                    lines = ["📊 你的持股："]
                    for h in holdings_data:
                        lines.append(f"{h['name']}({h['code']}) x{h['amount']} 成本¥{h['cost_price']} 当前¥{h['current_price']} 盈亏:{h['profit_str']}({h['profit_pct_str']})")
                    profit_str = f"+{total_profit:.0f}" if total_profit >= 0 else f"{total_profit:.0f}"
                    lines.append(f"总盈亏: {profit_str}")
                    yield event.plain_result("\n".join(lines))
                else:
                    raise
    else:
        yield event.plain_result("📈 股市操作:\n═══════════════════════════\n• /股市 - 查看行情\n• /股市 买 代码 数量\n• /股市 卖 代码 数量\n• /股市 持股\n═══════════════════════════")
