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
    HOSPITALIZED = "住院中"


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
            "registered_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
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
            # 压力系统
            "body_pressure": 0,         # 身体疲劳 (0-100)
            "mind_pressure": 0,         # 精神压力 (0-100)
            # Debuff系统
            "active_debuffs": [],       # 当前生效的 debuff ID 列表
            "debuff_timers": {},        # {attr_name: timestamp} 属性低于阈值的时间戳
            # 累计数据（永久）
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
            },
            # 每日数据（保留30天）
            "daily_stats": {},          # {"YYYY-MM-DD": {...}}
            # 用户设置
            "settings": {
                "sub_group_daily": False,
                "sub_personal_daily": False,
                "daily_report_hour": 23,
                "daily_report_minute": 0,
                "notification_enabled": True,
            },
            # 所在群组
            "groups": [],              # ["qq_group_xxx"]
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
    # 迁移装备栏位系统
    if "equipped_items" not in user_data:
        user_data["equipped_items"] = {}
    if "skills" not in user_data or not isinstance(user_data.get("skills"), dict):
        user_data["skills"] = INITIAL_SKILLS.copy()
    if "residence" not in user_data:
        user_data["residence"] = "桥下"
    if "status" not in user_data:
        user_data["status"] = UserStatus.FREE
    # 迁移压力系统 v0.1.2
    if "body_pressure" not in user_data:
        user_data["body_pressure"] = 0
    if "mind_pressure" not in user_data:
        user_data["mind_pressure"] = 0
    if "active_debuffs" not in user_data:
        user_data["active_debuffs"] = []
    if "debuff_timers" not in user_data:
        user_data["debuff_timers"] = {}
    # 迁移日报系统 v0.1.5 (lifetime_stats)
    if "lifetime_stats" not in user_data:
        user_data["lifetime_stats"] = {
            "total_gold_earned": 0,
            "total_gold_spent": 0,
            "total_work_hours": 0,
            "total_work_count": 0,
            "total_learn_hours": 0,
            "total_entertain_count": 0,
            "total_stock_trades": 0,
            "total_stock_profit": 0,
            "peak_gold": user_data.get("gold", 0),
            "checkin_days": 0,
            "achievements_unlocked": 0,
        }
    if "daily_stats" not in user_data:
        user_data["daily_stats"] = {}
    if "settings" not in user_data:
        user_data["settings"] = {
            "sub_group_daily": False,
            "sub_personal_daily": False,
            "daily_report_hour": 23,
            "daily_report_minute": 0,
            "notification_enabled": True,
        }
    if "groups" not in user_data:
        user_data["groups"] = []
    # 迁移签到系统
    if "checkin" not in user_data or user_data.get("checkin") is None:
        # 真的没有或为 None → 重建默认结构
        user_data["checkin"] = {
            "last_date": None,
            "streak": 0,
            "total_days": 0,
            "total_gold": 0,
            "lucky_drops": 0,
            "active_buffs": [],
        }
    else:
        checkin = user_data["checkin"]

        # 旧字段名迁移（未来有字段改名时在这里添加）
        old_field_migrations = {
            # "old_name": "new_name"
        }
        for old_key, new_key in old_field_migrations.items():
            if old_key in checkin and new_key not in checkin:
                checkin[new_key] = checkin.pop(old_key)

        # 补全新字段，保留已有值
        defaults = {
            "last_date": None,
            "streak": 0,
            "total_days": 0,
            "total_gold": 0,
            "lucky_drops": 0,
            "active_buffs": [],
        }
        for key, default_val in defaults.items():
            if key not in checkin:
                checkin[key] = default_val
    
    return user_data


# ========================================================
# 统计更新辅助函数
# ========================================================

def get_today_key() -> str:
    """获取今日日期键"""
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def init_daily_stats(stats: dict) -> dict:
    """初始化今日统计数据"""
    today = get_today_key()
    if today not in stats:
        stats[today] = {
            "gold_work": 0,
            "gold_stock_profit": 0,
            "gold_stock_loss": 0,
            "gold_spent": 0,
            "work_hours": 0,
            "work_count": 0,
            "learn_hours": 0,
            "entertain_count": 0,
            "stock_trades": 0,
            "debuff_minutes": 0,
            "pressure_peaks": {"body": 0, "mind": 0},
            "buffs_earned": [],
            "checkin": False,
            "hospital_minutes": 0,
        }
    return stats


def update_daily_stat(user_data: dict, key: str, value):
    """更新每日统计
    
    Args:
        user_data: 用户数据
        key: 统计键（见 init_daily_stats）
        value: 更新的值（数字则累加，布尔则覆盖）
    """
    daily = user_data.setdefault("daily_stats", {})
    today = get_today_key()
    init_daily_stats(daily)
    stat = daily[today]
    
    if isinstance(value, bool):
        stat[key] = value
    elif isinstance(value, (int, float)):
        stat[key] = stat.get(key, 0) + value
    elif isinstance(value, list):
        stat.setdefault(key, []).extend(value)


def update_lifetime_stat(user_data: dict, key: str, value):
    """更新累计统计
    
    Args:
        user_data: 用户数据
        key: 统计键
        value: 更新的值（数字则累加）
    """
    lifetime = user_data.setdefault("lifetime_stats", {})
    if isinstance(value, (int, float)):
        lifetime[key] = lifetime.get(key, 0) + value
        # 更新峰值
        if key == "total_gold_earned":
            lifetime["peak_gold"] = max(lifetime.get("peak_gold", 0), user_data.get("gold", 0))


def cleanup_old_daily_stats(user_data: dict, keep_days: int = 30):
    """清理过期的每日统计数据
    
    Args:
        user_data: 用户数据
        keep_days: 保留天数
    """
    from datetime import datetime, timezone, timedelta
    daily = user_data.get("daily_stats", {})
    if not daily:
        return
    
    today = datetime.now(timezone(timedelta(hours=8))).date()
    cutoff = (today - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    
    keys_to_remove = [k for k in daily if k < cutoff]
    for k in keys_to_remove:
        del daily[k]
