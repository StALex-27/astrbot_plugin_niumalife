"""
用户仓储 (UserRepository)
封装所有用户相关的数据访问，基于 AstrBot KV 存储（SQLite 后端）。

设计原则：
- 完全兼容旧 DataStore 的公开 API（get_user / create_user / update_user / get_all_users / save / get_lock），
  main.py 与 commands/* 仅需替换构造即可完成切换，零业务改动。
- 所有写入走 put_kv_data 一处，便于将来加缓存、批量写入、迁移。
- 新增 get_user_settings / update_user_settings 等高频小操作，避免业务侧读出整份 user dict
  再写回的 read-modify-write 放大。

注意：本模块不持有 user_id -> asyncio.Lock 的真实锁（KV 已是 SQLite，无文件并发）；
get_lock() 保留返回 asyncio.Lock 以兼容旧调用方。
"""
from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING

from ...modules.constants import INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS
from ...modules.user import UserStatus, migrate_user_data

if TYPE_CHECKING:
    pass


# KV 存储键名前缀
USER_KEY_PREFIX = "user:"
ALL_USERS_KEY = "__all_users__"
# 用户设置独立存放（高频小写）—— 仍在同一 namespace
USER_SETTINGS_KEY_PREFIX = "user_settings:"


class UserRepository:
    """用户仓储，替代旧 DataStore。

    兼容性说明：
    - 旧 DataStore 由 plugin 实例调用 get_kv_data/put_kv_data/delete_kv_data（Star 基类方法）。
    - 本类持有同一个 plugin 引用，透传这些方法。
    - 新增的方法（get_user_settings / update_user_settings）走独立 KV key，
      但 settings 是 user dict 的子集，业务侧仍可从 get_user() 读到完整数据。
    """

    def __init__(self, plugin):
        """
        Args:
            plugin: AstrBot Star 实例，提供 get_kv_data / put_kv_data / delete_kv_data
        """
        self._plugin = plugin

    # ========================================================
    # 内部 key 工具
    # ========================================================

    def _user_key(self, user_id: str) -> str:
        return f"{USER_KEY_PREFIX}{user_id}"

    def _settings_key(self, user_id: str) -> str:
        return f"{USER_SETTINGS_KEY_PREFIX}{user_id}"

    # ========================================================
    # 用户主数据 CRUD
    # ========================================================

    async def get_user(self, user_id: str) -> Optional[dict]:
        """获取用户数据（含自动迁移）。"""
        user_data = await self._plugin.get_kv_data(self._user_key(user_id), None)
        if not user_data:
            return None
        # 老用户迁移：字段缺失则补全并落盘
        if "checkin" not in user_data or "active_buffs" not in user_data.get("checkin", {}):
            user_data = migrate_user_data(user_data)
            await self._plugin.put_kv_data(self._user_key(user_id), user_data)
        return user_data

    async def create_user(self, user_id: str, nickname: str) -> dict:
        """创建新用户；若已存在则返回现有数据（幂等）。"""
        existing = await self._plugin.get_kv_data(self._user_key(user_id), None)
        if existing:
            return existing

        from datetime import datetime, timezone, timedelta
        local_tz = timezone(timedelta(hours=8))

        user_data = {
            "user_id": user_id,
            "nickname": nickname,
            "status": UserStatus.FREE,
            "registered_at": datetime.now(local_tz).isoformat(),
            "gold": INITIAL_GOLD,
            "attributes": INITIAL_ATTRIBUTES.copy(),
            "skills": INITIAL_SKILLS.copy(),
            "residence": "桥下",
            "inventory": [],
            "equipped_items": {},
            "stock_holdings": {},
            "achievements": [],
            "records": [],
            "locked_until": None,
            "current_action": None,
            "action_detail": None,
            "fishing": {
                "fish_caught": {},         # {"鱼名": 总数}
                "fish_records": [],        # 钓鱼记录（含尺寸/时间）
                "total_fishing_count": 0,  # 总钓鱼次数
                "total_fishing_value": 0,  # 累计卖出金币
                "biggest_catch": {},       # {"fish": ..., "weight": ...}
                "fish_title": "",
            },
            "checkin": {
                "last_date": None,
                "streak": 0,
                "total_days": 0,
                "total_gold": 0,
                "lucky_drops": 0,
                "active_buffs": [],
            },
            "body_pressure": 0,
            "mind_pressure": 0,
            "active_debuffs": [],
            "debuff_timers": {},
            "lifetime_stats": {
                "total_gold_earned": 0,
                "total_gold_spent": 0,
                "total_work_hours": 0,
                "total_work_count": 0,
                "total_learn_hours": 0,
                "total_entertain_count": 0,
                "total_stock_trades": 0,
                "total_stock_profit": 0,
                "peak_gold": 0,
                "checkin_days": 0,
                "achievements_unlocked": 0,
                "total_fish_caught": 0,
                "biggest_fish_weight": 0,
            },
            "daily_stats": {},
            "settings": {
                "sub_group_daily": False,
                "sub_personal_daily": False,
                "daily_report_hour": 23,
                "daily_report_minute": 0,
                "notification_enabled": True,
            },
            "groups": [],
        }

        await self._plugin.put_kv_data(self._user_key(user_id), user_data)
        await self._add_to_index(user_id)
        return user_data

    async def update_user(self, user_id: str, user_data: dict) -> None:
        """整体替换用户数据（callers 负责构造完整 dict）。"""
        await self._plugin.put_kv_data(self._user_key(user_id), user_data)

    async def delete_user(self, user_id: str) -> None:
        await self._plugin.delete_kv_data(self._user_key(user_id))
        await self._remove_from_index(user_id)

    async def get_all_users(self) -> dict[str, dict]:
        """获取全部用户 {user_id: user_data}。"""
        index = await self._plugin.get_kv_data(ALL_USERS_KEY, [])
        if not index:
            return {}
        # 批量并发读取，避免 N 次串行 await
        keys = [self._user_key(uid) for uid in index]
        results = await asyncio.gather(
            *(self._plugin.get_kv_data(k, None) for k in keys),
            return_exceptions=True,
        )
        users: dict[str, dict] = {}
        for uid, data in zip(index, results):
            # data 已被 return_exceptions=True 包装：可能是 Exception | dict | None
            if isinstance(data, BaseException) or data is None:
                continue
            if not isinstance(data, dict):
                continue
            users[uid] = data
        return users

    async def save(self) -> None:
        """KV 存储无需手动 save，保留为空方法以兼容旧调用方。"""
        return None

    # ========================================================
    # 设置子集操作（新增，避免整 dict read-modify-write）
    # ========================================================

    async def get_user_settings(self, user_id: str) -> dict:
        """读取用户设置。若不存在则从 user dict 中读；再不存在则返回默认设置。"""
        # 优先读独立 key（写过的优先）
        cached = await self._plugin.get_kv_data(self._settings_key(user_id), None)
        if cached is not None:
            return cached
        # 降级从 user dict 读
        user = await self.get_user(user_id)
        if user:
            return user.get("settings", {})
        return {
            "sub_group_daily": False,
            "sub_personal_daily": False,
            "daily_report_hour": 23,
            "daily_report_minute": 0,
            "notification_enabled": True,
        }

    async def update_user_settings(self, user_id: str, settings: dict) -> None:
        """整体替换用户设置；同时回写到 user dict 保证一致。"""
        await self._plugin.put_kv_data(self._settings_key(user_id), settings)
        user = await self.get_user(user_id)
        if user is not None:
            user["settings"] = settings
            await self._plugin.put_kv_data(self._user_key(user_id), user)

    # ========================================================
    # 索引维护（私有）
    # ========================================================

    async def _add_to_index(self, user_id: str) -> None:
        index = await self._plugin.get_kv_data(ALL_USERS_KEY, [])
        if not isinstance(index, list):
            index = []
        if user_id not in index:
            index.append(user_id)
            await self._plugin.put_kv_data(ALL_USERS_KEY, index)

    async def _remove_from_index(self, user_id: str) -> None:
        index = await self._plugin.get_kv_data(ALL_USERS_KEY, [])
        if not isinstance(index, list):
            return
        if user_id in index:
            index.remove(user_id)
            await self._plugin.put_kv_data(ALL_USERS_KEY, index)

    # ========================================================
    # 兼容性：无锁占位（旧 DataStore 的 get_lock 在 KV 上无意义）
    # ========================================================

    def get_lock(self, user_id: str) -> asyncio.Lock:
        """KV 存储无并发文件冲突，保留接口返回新锁以兼容旧调用。"""
        return asyncio.Lock()
