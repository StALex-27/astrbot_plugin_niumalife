"""
用户数据操作模块
包含 DataStore、用户数据初始化/迁移等函数
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .constants import INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS


# 用户状态常量
class UserStatus:
    FREE = "空闲"
    WORKING = "工作中"
    SLEEPING = "睡眠中"
    LEARNING = "学习中"
    ENTERTAINING = "娱乐中"


class DataStore:
    """数据存储管理器"""
    
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._users_file = data_dir / "users.json"
        self._user_locks: dict[str, asyncio.Lock] = {}
    
    def _load_users(self) -> dict:
        if self._users_file.exists():
            with open(self._users_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_users(self, users: dict):
        with open(self._users_file, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    
    def get_user(self, user_id: str) -> Optional[dict]:
        users = self._load_users()
        user_data = users.get(user_id)
        if user_data:
            # 迁移旧用户数据（检查是否需要迁移）
            if "checkin" not in user_data or "active_buffs" not in user_data.get("checkin", {}):
                user_data = migrate_user_data(user_data)
                # 保存迁移后的数据
                self.update_user(user_id, user_data)
        return user_data
    
    def create_user(self, user_id: str, nickname: str) -> dict:
        """创建新用户"""
        users = self._load_users()
        user_data = {
            "user_id": user_id,
            "nickname": nickname,
            "status": UserStatus.FREE,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "gold": INITIAL_GOLD,
            "attributes": INITIAL_ATTRIBUTES.copy(),
            "skills": INITIAL_SKILLS.copy(),
            "residence": "桥下",
            "inventory": [],
            "stock_holdings": {},
            "achievements": [],
            "records": [],
            "locked_until": None,
            "current_action": None,
            "action_detail": None,
            # 签到相关
            "checkin": {
                "last_date": None,       # 上次签到日期 (YYYY-MM-DD)
                "streak": 0,             # 连续签到天数
                "total_days": 0,         # 总签到天数
                "total_gold": 0,         # 累计签到金币
                "lucky_drops": 0,        # 幸运掉落次数
                "active_buffs": [],      # 当前生效的临时buffs
            },
        }
        users[user_id] = user_data
        self._save_users(users)
        return user_data
    
    def update_user(self, user_id: str, user_data: dict):
        users = self._load_users()
        users[user_id] = user_data
        self._save_users(users)
    
    def get_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]


def migrate_inventory(user_data: dict) -> dict:
    """迁移库存数据
    
    旧格式: {"inventory": ["item_name"]} 或 {"inventory": [{"id": "item_001", "name": "破旧T恤"}]}
    新格式: {"inventory": [{"id": "item_001", "name": "破旧T恤", "equipped": false}]}
    
    Args:
        user_data: 用户数据
    
    Returns:
        dict: 迁移后的用户数据
    """
    inventory = user_data.get("inventory", [])
    new_inventory = []
    for item in inventory:
        # 跳过无效项
        if item is None:
            continue
        # 字符串格式: "item_name" -> {"name": "item_name", "equipped": False}
        if isinstance(item, str):
            new_inventory.append({"id": item, "name": item, "equipped": False})
        # 字典格式，确保 equipped 字段
        elif isinstance(item, dict):
            if "equipped" not in item:
                item["equipped"] = False
            new_inventory.append(item)
    
    user_data["inventory"] = new_inventory
    return user_data


def migrate_user_data(user_data: dict) -> dict:
    """执行所有用户数据迁移
    
    Args:
        user_data: 用户数据
    
    Returns:
        dict: 迁移后的用户数据
    """
    # 确保 attributes 字段存在且为字典
    if "attributes" not in user_data or not isinstance(user_data.get("attributes"), dict):
        user_data["attributes"] = INITIAL_ATTRIBUTES.copy()
    
    # 确保 gold 字段存在且为数字
    if "gold" not in user_data or not isinstance(user_data.get("gold"), (int, float)):
        user_data["gold"] = INITIAL_GOLD
    
    # 迁移库存
    user_data = migrate_inventory(user_data)
    
    # 迁移技能
    from .skills import migrate_skills
    user_data = migrate_skills(user_data)
    
    # 确保必要字段存在
    if "stock_holdings" not in user_data:
        user_data["stock_holdings"] = {}
    if "achievements" not in user_data:
        user_data["achievements"] = []
    if "records" not in user_data:
        user_data["records"] = []
    if "inventory" not in user_data:
        user_data["inventory"] = []
    if "skills" not in user_data or not isinstance(user_data.get("skills"), dict):
        user_data["skills"] = INITIAL_SKILLS.copy()
    if "residence" not in user_data:
        user_data["residence"] = "桥下"
    if "status" not in user_data:
        user_data["status"] = UserStatus.FREE
    
    # 迁移签到系统 (v0.0.6+)
    if "checkin" not in user_data or not isinstance(user_data.get("checkin"), dict):
        user_data["checkin"] = {
            "last_date": None,
            "streak": 0,
            "total_days": 0,
            "total_gold": 0,
            "lucky_drops": 0,
            "active_buffs": [],
        }
    else:
        # 确保所有字段都存在
        checkin = user_data["checkin"]
        for key in ["last_date", "streak", "total_days", "total_gold", "lucky_drops", "active_buffs"]:
            if key not in checkin:
                checkin[key] = 0 if key != "last_date" and key != "active_buffs" else (None if key == "last_date" else [])
    
    return user_data