"""
每日结算与日报生成
从 main.py 抽出，承担：
- 每日结算（房租扣款 / 累计金币 / 清理过期 daily_stats）
- 群组日报推送（基于订阅）
- 个人日报推送（基于用户 settings）

依赖：
- plugin: 提供 get_kv_data / put_kv_data / config / _store（UserRepository）
- UserRepository：用户数据 CRUD
- group_repo：可选，群组配置访问（这里直接走 plugin 的 get_kv_data，复用现有 KV key）

保持对调用方签名稳定：NiumaLife._do_daily_settlement() 仍存在，改为委托。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.star import StarTools
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession

if TYPE_CHECKING:
    pass

LOCAL_TZ = timezone(timedelta(hours=8))

GROUP_CONFIG_PREFIX = "group_config:"
DEFAULT_GROUP_CONFIG = {
    "enabled": False,
    "daily_report_hour": 23,
    "daily_report_minute": 0,
    "subscribers": [],
    "total_gold_earned": 0,
    "total_members": 0,
}
DAILY_SETTLEMENT_KV_KEY = "__daily_settlement__:last_date"


class DailyReportGenerator:
    """每日结算 + 群组日报 + 个人日报的统合执行器。

    设计原则：
    - 所有用户数据访问经由 UserRepository（上一阶段重构已落地）；
    - 所有 KV 读取（group config / settlement date / stock price）走 plugin 实例透传；
    - 单次执行内对每个用户的处理串行，但 get_all_users 已并发 gather；
    - 单个用户处理失败不阻塞其他用户（局部 try/except）。
    """

    def __init__(self, plugin, user_repo, constants_module):
        """
        Args:
            plugin: AstrBot Star 实例，提供 get_kv_data/put_kv_data/send_message_by_id/config
            user_repo: UserRepository 实例
            constants_module: modules.constants 模块（用于 STOCKS/RESIDENCES 等常量）
        """
        self._plugin = plugin
        self._store = user_repo
        self._constants = constants_module

    # ========================================================
    # 群组配置（与 main.py 历史 KV key 完全兼容）
    # ========================================================

    async def get_group_config(self, group_id: str) -> dict:
        key = f"{GROUP_CONFIG_PREFIX}{group_id}"
        config = await self._plugin.get_kv_data(key, None)
        if config is None:
            config = DEFAULT_GROUP_CONFIG.copy()
            config["subscribers"] = []
            await self._plugin.put_kv_data(key, config)
        return config

    async def save_group_config(self, group_id: str, config: dict) -> None:
        key = f"{GROUP_CONFIG_PREFIX}{group_id}"
        await self._plugin.put_kv_data(key, config)

    # ========================================================
    # 入口
    # ========================================================

    async def settle(self) -> None:
        """执行每日结算 + 推送所有订阅日报。"""
        from .user_report_helpers import (
            update_lifetime_stat,
            cleanup_old_daily_stats,
        )

        now = datetime.now(LOCAL_TZ)
        date_str = now.strftime("%Y-%m-%d")
        today_key = date_str

        # 防重复
        last_date = await self._plugin.get_kv_data(DAILY_SETTLEMENT_KV_KEY, "")
        if last_date == date_str:
            logger.info("[NiumaLife] 今日已结算,跳过")
            return

        logger.info(f"[NiumaLife] 执行每日结算: {date_str}")

        users = await self._store.get_all_users()
        RESIDENCES = self._constants.RESIDENCES

        group_users: dict[str, list] = {}
        user_groups: dict[str, list] = {}
        rent_deducted: dict[str, list] = {}
        group_gold: dict[str, int] = {}

        for user_id, user in users.items():
            try:
                today_stats = user.get("daily_stats", {}).get(today_key, {})
                gold_work = today_stats.get("gold_work", 0)
                gold_profit = today_stats.get("gold_stock_profit", 0)
                gold_loss = today_stats.get("gold_stock_loss", 0)
                net_gold = gold_work + gold_profit - gold_loss

                if net_gold > 0:
                    update_lifetime_stat(user, "total_gold_earned", net_gold)

                # 房租扣款
                residence = user.get("residence", "桥下")
                if residence != "桥下":
                    res_info = RESIDENCES.get(residence)
                    if res_info:
                        daily_rent = res_info.get("daily_rent", 0)
                        if daily_rent > 0 and user.get("gold", 0) >= daily_rent:
                            user["gold"] -= daily_rent
                            for gid in user.get("groups", []):
                                rent_deducted.setdefault(gid, []).append(
                                    (user.get("nickname", "匿名"), daily_rent, residence)
                                )
                                group_gold[gid] = group_gold.get(gid, 0) + daily_rent

                # 按群组索引
                for gid in user.get("groups", []):
                    group_users.setdefault(gid, []).append((user_id, user))
                    if net_gold > 0:
                        group_gold[gid] = group_gold.get(gid, 0) + int(net_gold)

                await self._store.update_user(user_id, user)
                cleanup_old_daily_stats(user)

            except Exception as e:
                logger.error(f"[NiumaLife] 结算用户 {user_id} 时出错: {e}")

        await self._plugin.put_kv_data(DAILY_SETTLEMENT_KV_KEY, date_str)

        # 群组日报
        await self._dispatch_group_reports(group_users, group_gold, rent_deducted, date_str, today_key)
        # 个人日报
        await self._dispatch_personal_reports(users, date_str, today_key)

        logger.info("[NiumaLife] 日报生成完成")

    # ========================================================
    # 报告推送
    # ========================================================

    async def _dispatch_group_reports(
        self,
        group_users: dict,
        group_gold: dict,
        rent_deducted: dict,
        date_str: str,
        today_key: str,
    ) -> None:
        for group_id, members in group_users.items():
            config = await self.get_group_config(group_id)
            if not config.get("enabled", False):
                continue
            subscribers = config.get("subscribers", [])
            if subscribers:
                active_in_group = [u for u in members if u[0] in subscribers]
                if not active_in_group:
                    continue

            report = self._build_group_report(
                group_id, members, group_gold.get(group_id, 0),
                rent_deducted.get(group_id, []), date_str, today_key,
            )
            try:
                platform_id = getattr(self._plugin, "_platform_id", "") or "aiocqhttp"
                grp_session = MessageSession.from_str(f"{platform_id}:GroupMessage:{group_id}")
                await StarTools.send_message(
                    grp_session,
                    MessageChain().message(report)
                )
                logger.info(f"[NiumaLife] 群 {group_id} 日报已发送")
            except Exception as e:
                logger.error(f"[NiumaLife] 群 {group_id} 日报发送失败: {e}")

    async def _dispatch_personal_reports(
        self, users: dict, date_str: str, today_key: str,
    ) -> None:
        for user_id, user in users.items():
            settings = user.get("settings", {})
            if not settings.get("sub_personal_daily", False):
                continue
            report = self._build_personal_report(user, date_str, today_key)
            try:
                platform_id = getattr(self._plugin, "_platform_id", "") or "aiocqhttp"
                priv_session = MessageSession.from_str(f"{platform_id}:PrivateMessage:{user_id}")
                await StarTools.send_message(
                    priv_session,
                    MessageChain().message(report)
                )
                logger.info(f"[NiumaLife] 用户 {user_id} 个人日报已发送")
            except Exception as e:
                logger.error(f"[NiumaLife] 用户 {user_id} 个人日报发送失败: {e}")

    # ========================================================
    # 报告文本生成（纯函数，原样搬过来）
    # ========================================================

    def _build_group_report(
        self, group_id, members, total_group_gold, rent_deducted, date_str, today_key,
    ) -> str:
        STOCKS = self._constants.STOCKS

        lines = [
            "━━━━━━━━━━━━━━",
            "【 🗞️ 牛马日报 】",
            f"📅 {date_str}",
            "━━━━━━━━━━━━━━",
            "",
            "📈 股市涨跌榜",
            "━━━━━━━━━━━━━━",
        ]

        # ---- 股市涨跌榜 ----
        stock_changes = []
        for name, info in STOCKS.items():
            base = info.get("base_price", 100)
            # 注意：这里默认 base_price 做 open，不重读 KV 以避免异步语义破坏纯文本生成；
            # 如需盘中真实 open 价，可后续注入 KV 客户端。这里保持与旧实现行为一致。
            open_price = base
            current_price = base  # 占位，旧版也是这样
            change = ((current_price - open_price) / open_price * 100) if open_price else 0.0
            stock_changes.append((name, current_price, change))

        stock_changes.sort(key=lambda x: x[2], reverse=True)
        rising = [(n, p, c) for n, p, c in stock_changes if c >= 0]
        falling = [(n, p, c) for n, p, c in stock_changes if c < 0]

        if rising:
            lines.append("↑ 涨幅榜:")
            for name, price, change in rising[:3]:
                sym = "🔺" if change > 0 else "➖"
                lines.append(f" {sym} {name} {change:+.2f}% ¥{price:.2f}")
        if falling:
            lines.append("↓ 跌幅榜:")
            for name, price, change in falling[:3]:
                lines.append(f" 🔻 {name} {change:.2f}% ¥{price:.2f}")

        # ---- 金币榜 ----
        lines.extend([
            "",
            "💰 今日金币榜 (Top5)",
            "━━━━━━━━━━━━━━",
        ])
        user_earnings = []
        for _, user in members:
            today_stats = user.get("daily_stats", {}).get(today_key, {})
            work_gold = today_stats.get("gold_work", 0)
            stock_pnl = today_stats.get("gold_stock_profit", 0) - today_stats.get("gold_stock_loss", 0)
            total = work_gold + stock_pnl
            user_earnings.append((user.get("nickname", "匿名"), total))
        user_earnings.sort(key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, (name, gold) in enumerate(user_earnings[:5]):
            medal = medals[i] if i < 3 else f"{i+1}."
            sign = "+" if gold >= 0 else ""
            lines.append(f" {medal} {name} {sign}{gold}金币")

        # ---- 打工榜 ----
        lines.extend([
            "",
            "📊 今日打工榜 (Top3)",
            "━━━━━━━━━━━━━━",
        ])
        user_work = []
        for _, user in members:
            today_stats = user.get("daily_stats", {}).get(today_key, {})
            hours = today_stats.get("work_hours", 0)
            count = today_stats.get("work_count", 0)
            if hours > 0:
                user_work.append((user.get("nickname", "匿名"), hours, count))
        user_work.sort(key=lambda x: x[1], reverse=True)
        for i, (name, hours, count) in enumerate(user_work[:3]):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            lines.append(f" {medal} {name} {hours:.1f}h ({count}次)")

        # ---- 房租 ----
        if rent_deducted:
            lines.extend([
                "",
                "📝 今日房租支出",
                "━━━━━━━━━━━━━━",
            ])
            for name, amount, res in rent_deducted[:5]:
                lines.append(f" {name}: -{amount}金 ({res})")

        # ---- 本群 ----
        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            f"🏠 群成员: {len(members)}人",
            f"💰 群累计赚取: {total_group_gold:,}金币",
            "━━━━━━━━━━━━━━",
        ])
        report_hour = getattr(self._plugin.config, 'daily_report_hour', 23)
        report_min = getattr(self._plugin.config, 'daily_report_minute', 0)
        lines.append(f"⏰ 每日 {report_hour:02d}:{report_min:02d} 自动生成")

        return "\n".join(lines)

    def _build_personal_report(self, user: dict, date_str: str, today_key: str) -> str:
        STOCKS = self._constants.STOCKS

        lines = [
            "━━━━━━━━━━━━━━",
            "【 📋 个人日报 】",
            f"📅 {date_str}",
            "━━━━━━━━━━━━━━",
        ]

        today = user.get("daily_stats", {}).get(today_key, {})
        lifetime = user.get("lifetime_stats", {})

        work_gold = today.get("gold_work", 0)
        stock_profit = today.get("gold_stock_profit", 0)
        stock_loss = today.get("gold_stock_loss", 0)
        spent = today.get("gold_spent", 0)
        net = work_gold + stock_profit - stock_loss

        lines.extend([
            "",
            "💵 今日收支",
            "━━━━━━━━━━━━━━",
            f" 工作收入: +{work_gold}金币",
            f" 股票盈亏: {'+' if stock_profit >= 0 else ''}{stock_profit-stock_loss}金币",
            f" 消费支出: -{spent}金币",
            f" 净收益: {'+' if net >= 0 else ''}{net}金币",
            "",
            "📊 今日活动",
            "━━━━━━━━━━━━━━",
            f" 工作: {today.get('work_hours', 0):.1f}h ({today.get('work_count', 0)}次)",
            f" 学习: {today.get('learn_hours', 0):.1f}h",
            f" 娱乐: {today.get('entertain_count', 0)}次",
            f" 股票交易: {today.get('stock_trades', 0)}次",
        ])

        holdings = user.get("stock_holdings", {})
        if holdings:
            lines.extend([
                "",
                "📈 持仓状况",
                "━━━━━━━━━━━━━━",
            ])
            for name, hold in holdings.items():
                code = STOCKS.get(name, {}).get("code", "?")
                amount = hold.get("amount", 0)
                avg = hold.get("avg_price", 0)
                lines.append(f" {code} {name}: {amount}股 (成本¥{avg:.2f})")

        lines.extend([
            "",
            "🏆 累计成就",
            "━━━━━━━━━━━━━━",
            f" 累计赚取: {int(lifetime.get('total_gold_earned', 0)):,}金币",
            f" 最高金币: {int(lifetime.get('peak_gold', 0)):,}金币",
            f" 累计工作: {lifetime.get('total_work_hours', 0):.0f}h",
            f" 股票盈亏: {'+' if lifetime.get('total_stock_profit', 0) >= 0 else ''}{int(lifetime.get('total_stock_profit', 0)):,}金币",
            "",
            "━━━━━━━━━━━━━━",
            f"💳 当前余额: {user.get('gold', 0):,}金币",
            "━━━━━━━━━━━━━━",
        ])
        return "\n".join(lines)
