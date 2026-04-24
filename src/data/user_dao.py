"""
用户数据访问对象 (DAO)
封装用户相关的所有数据操作
"""

import os
from typing import Optional, Dict, List
from datetime import datetime, timezone, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.data.json_store import JSONStore
from modules.constants import (
    INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS,
    MAX_ATTRIBUTE
)
from modules.user import UserStatus


# GMT+8 时区
LOCAL_TZ = timezone(timedelta(hours=8))


class UserDAO:
    """
    用户数据访问对象
    
    提供用户创建、查询、更新、删除等操作
    数据存储在 JSON 文件中
    """

    def __init__(self, store: JSONStore):
        """
        Args:
            store: JSON 存储实例
        """
        self.store = store
        self._users_key = 'users'

    def _init_user(self, user_id: str, nickname: str) -> dict:
        """创建新用户数据结构"""
        return {
            "user_id": user_id,
            "nickname": nickname,
            "gold": INITIAL_GOLD,
            "attributes": INITIAL_ATTRIBUTES.copy(),
            "skills": INITIAL_SKILLS.copy(),
            "status": UserStatus.FREE,
            "residence": "桥下",
            "checkin": {
                "last_date": "",
                "last_luck": 50,
                "streak": 0,
                "total_days": 0,
                "total_gold": 0,
                "lucky_drops": 0,
                "active_buffs": [],
                "luck_history": [],
            },
            "inventory": [],
            "records": [],
            "created_at": datetime.now(LOCAL_TZ).isoformat(),
        }

    def get_user(self, user_id: str) -> Optional[dict]:
        """
        获取用户数据
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户数据字典，不存在返回 None
        """
        users = self.store.get(self._users_key, {})
        return users.get(user_id)

    def get_all_users(self) -> Dict[str, dict]:
        """获取所有用户"""
        return self.store.get(self._users_key, {})

    def create_user(self, user_id: str, nickname: str) -> dict:
        """
        创建新用户
        
        Args:
            user_id: 用户ID
            nickname: 昵称
        
        Returns:
            创建的用户数据
        """
        users = self.store.get(self._users_key, {})
        
        if user_id in users:
            return users[user_id]

        user = self._init_user(user_id, nickname)
        users[user_id] = user
        self.store.set(self._users_key, users)
        
        return user

    def update_user(self, user_id: str, user_data: dict):
        """
        更新用户数据 (整体替换)
        
        Args:
            user_id: 用户ID
            user_data: 新的用户数据
        """
        users = self.store.get(self._users_key, {})
        users[user_id] = user_data
        self.store.set(self._users_key, users)

    def delete_user(self, user_id: str):
        """删除用户"""
        users = self.store.get(self._users_key, {})
        if user_id in users:
            del users[user_id]
            self.store.set(self._users_key, users)

    def user_exists(self, user_id: str) -> bool:
        """检查用户是否存在"""
        return self.get_user(user_id) is not None

    # ========== 属性操作 ==========

    def get_attribute(self, user_id: str, attr_name: str, default: int = 0) -> int:
        """获取用户属性"""
        user = self.get_user(user_id)
        if not user:
            return default
        return user.get("attributes", {}).get(attr_name, default)

    def set_attribute(self, user_id: str, attr_name: str, value: int):
        """设置用户属性"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["attributes"][attr_name] = value
        self.update_user(user_id, user)

    def update_attributes(self, user_id: str, updates: Dict[str, int]):
        """批量更新属性"""
        user = self.get_user(user_id)
        if not user:
            return
        
        attrs = user.get("attributes", {})
        for key, value in updates.items():
            attrs[key] = min(MAX_ATTRIBUTE, max(0, value))
        user["attributes"] = attrs
        self.update_user(user_id, user)

    # ========== 金币操作 ==========

    def get_gold(self, user_id: str) -> int:
        """获取金币"""
        user = self.get_user(user_id)
        return user.get("gold", 0) if user else 0

    def add_gold(self, user_id: str, amount: int):
        """添加金币 (可为负数)"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["gold"] = max(0, user.get("gold", 0) + amount)
        self.update_user(user_id, user)

    def set_gold(self, user_id: str, amount: int):
        """设置金币"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["gold"] = max(0, amount)
        self.update_user(user_id, user)

    # ========== 状态操作 ==========

    def get_status(self, user_id: str) -> str:
        """获取用户状态"""
        user = self.get_user(user_id)
        return user.get("status", UserStatus.FREE) if user else UserStatus.FREE

    def set_status(self, user_id: str, status: str):
        """设置用户状态"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["status"] = status
        self.update_user(user_id, user)

    # ========== 签到操作 ==========

    def get_checkin(self, user_id: str) -> dict:
        """获取签到数据"""
        user = self.get_user(user_id)
        return user.get("checkin", {}) if user else {}

    def update_checkin(self, user_id: str, checkin_data: dict):
        """更新签到数据"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["checkin"] = checkin_data
        self.update_user(user_id, user)

    # ========== 技能操作 ==========

    def get_skill_level(self, user_id: str, skill_name: str) -> int:
        """获取技能等级"""
        user = self.get_user(user_id)
        if not user:
            return 0
        
        skill = user.get("skills", {}).get(skill_name, {})
        if isinstance(skill, dict):
            return skill.get("level", 0)
        return int(skill) if skill else 0

    def update_skill(self, user_id: str, skill_name: str, level: int, exp: int = 0):
        """更新技能"""
        user = self.get_user(user_id)
        if not user:
            return
        
        user["skills"][skill_name] = {"level": level, "exp": exp}
        self.update_user(user_id, user)

    # ========== 记录操作 ==========

    def add_record(self, user_id: str, record_type: str, detail: str, 
                   gold_change: int = 0, extra: dict = None):
        """添加记录"""
        user = self.get_user(user_id)
        if not user:
            return
        
        record = {
            "type": record_type,
            "detail": detail,
            "gold_change": gold_change,
            "time": datetime.now(LOCAL_TZ).isoformat(),
        }
        if extra:
            record.update(extra)
        
        user.setdefault("records", []).append(record)
        self.update_user(user_id, user)

    def get_records(self, user_id: str, limit: int = 10) -> List[dict]:
        """获取最近记录"""
        user = self.get_user(user_id)
        if not user:
            return []
        
        records = user.get("records", [])
        return records[-limit:] if len(records) > limit else records
