"""
交互式命令处理器 - 辅助函数
保留模块级辅助函数和单例管理器，供命令逻辑模块调用。
"""

from datetime import datetime, timezone, timedelta


LOCAL_TZ = timezone(timedelta(hours=8))

# 打工系统V2管理器单例
_job_manager = None
_favor_manager = None
_shop_manager = None

def get_job_mgr():
    global _job_manager
    if _job_manager is None:
        from ...modules.jobs import JobManager
        _job_manager = JobManager()
    return _job_manager

def get_favor_mgr():
    global _favor_manager
    if _favor_manager is None:
        from ...modules.company_favorability import CompanyFavorability
        _favor_manager = CompanyFavorability()
    return _favor_manager

def get_company_shop_mgr():
    global _shop_manager
    if _shop_manager is None:
        from ...modules.company_shop import CompanyShop
        _shop_manager = CompanyShop()
    return _shop_manager
