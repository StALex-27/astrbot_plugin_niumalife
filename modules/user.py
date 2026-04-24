"""
用户数据操作模块
包含 DataStore、用户数据初始化/迁移等函数
重构: 使用 AstrBot KV 存储替代 JSON 文件，解决并发竞态问题
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..main import NiumaLife

from .constants import INITIAL_GOLD, INITIAL_ATTRIBUTES, INITIAL_SKILLS


# 用户状态常量
class UserStatus:
    FREE = "空闲"
    WORKING = "工作中"
    SLEEPING = "睡眠中"
    LEARNING = "学习中"
    ENTERTAINING = "娱乐中"


# KV 存储键名前缀
USER_KEY_PREFIX = "user:"
ALL_USERS_KEY = "__all_users__"


class DataStore:
    """数据存储管理器 - 基于 AstrBot KV 存储
    
    使用 SQLite 后端，解决 JSON 文件的并发竞态问题
    每个用户独立存储，键名格式: user:{user_id}
    """
    
    def __init__(self, plugin: "NiumaLife"):
        """初始化 DataStore
        
        Args:
            plugin: 插件实例，用于访问 KV 存储方法
        """
        self._plugin = plugin
        self._all_users_key = ALL_USERS_KEY
    
    def _user_key(self, user_id: str) -> str:
        """生成用户数据键名"""
        return f"{USER_KEY_PREFIX}{user_id}"
    
    # ========================================================
    # 公开 API (异步)
    # ========================================================
    
    async def get_user(self, user_id: str) -> Optional[dict]:
        """获取用户数据
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户数据字典，不存在则返回 None
        """
        user_data = await self._plugin.get_kv_data(self._user_key(user_id), None)
        if user_data:
            # 迁移旧用户数据（检查是否需要迁移）
            if "checkin" not in user_data or "active_buffs" not in user_data.get("checkin", {}):
                user_data = migrate_user_data(user_data)
                await self.update_user(user_id, user_data)
        return user_data
    
    async def create_user(self, user_id: str, nickname: str) -> dict:
        """创建新用户
        
        Args:
            user_id: 用户ID
            nickname: 用户昵称
        
        Returns:
            新用户数据字典
        """
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
            "equipped_items": {},  # {slot: {id, name, effects}}
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
        
        # 存储用户数据
        await self._plugin.put_kv_data(self._user_key(user_id), user_data)
        
        # 更新全局用户索引
        await self._add_to_index(user_id)
        
        return user_data
    
    async def update_user(self, user_id: str, user_data: dict):
        """更新用户数据
        
        Args:
            user_id: 用户ID
            user_data: 新的用户数据（完整替换）
        """
        await self._plugin.put_kv_data(self._user_key(user_id), user_data)
    
    async def delete_user(self, user_id: str):
        """删除用户
        
        Args:
            user_id: 用户ID
        """
        await self._plugin.delete_kv_data(self._user_key(user_id))
        await self._remove_from_index(user_id)
    
    async def get_all_users(self) -> dict[str, dict]:
        """获取所有用户数据
        
        Returns:
            {user_id: user_data} 字典
        """
        # 从索引获取所有用户ID
        index = await self._plugin.get_kv_data(self._all_users_key, [])
        if not index:
            return {}
        
        # 批量获取用户数据
        users = {}
        for user_id in index:
            user_data = await self._plugin.get_kv_data(self._user_key(user_id), None)
            if user_data:
                users[user_id] = user_data
        
        return users
    
    async def save(self):
        """保存所有数据（KV 存储无需手动保存，此方法保留兼容）"""
        pass
    
    # ========================================================
    # 私有方法
    # ========================================================
    
    async def _get_index(self) -> list[str]:
        """获取用户索引列表"""
        return await self._plugin.get_kv_data(self._all_users_key, [])
    
    async def _save_index(self, index: list[str]):
        """保存用户索引列表"""
        await self._plugin.put_kv_data(self._all_users_key, index)
    
    async def _add_to_index(self, user_id: str):
        """添加用户到索引"""
        index = await self._get_index()
        if user_id not in index:
            index.append(user_id)
            await self._save_index(index)
    
    async def _remove_from_index(self, user_id: str):
        """从索引移除用户"""
        index = await self._get_index()
        if user_id in index:
            index.remove(user_id)
            await self._save_index(index)
    
    # ========================================================
    # 兼容性别名 (部分同步接口保留用于快速迁移)
    # ========================================================
    
    def get_lock(self, user_id: str) -> asyncio.Lock:
        """获取用户锁（KV 存储无需锁，此方法保留兼容）"""
        return asyncio.Lock()


# ========================================================
# 数据迁移函数
# ========================================================

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
    # 迁移装备栏位系统 (v0.0.12+)
    if "equipped_items" not in user_data:
        user_data["equipped_items"] = {}
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
