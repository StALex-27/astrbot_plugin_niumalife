"""
日报辅助函数：从 modules.user 导入以避免循环依赖。
这里只做一层薄薄 re-export，方便 daily_report.py 解耦 modules.user 的内部细节。
"""
from ...modules.user import (
    update_lifetime_stat,
    update_daily_stat,
    get_today_key,
    cleanup_old_daily_stats,
    init_daily_stats,
)

__all__ = [
    "update_lifetime_stat",
    "update_daily_stat",
    "get_today_key",
    "cleanup_old_daily_stats",
    "init_daily_stats",
]
