"""
Buff系统模块
独立设计，支持多种buff类型和生效条件
"""
import random
from datetime import datetime, timezone
from typing import Optional, Union


# ============================================================
# Buff类型枚举
# ============================================================

class BuffType:
    """Buff效果类型"""
    INCOME_MULTI = "income_multi"      # 金币收益倍率
    COST_REDUCE = "cost_reduce"         # 消耗降低
    EXP_MULTI = "exp_multi"            # 经验倍率
    ATTR_BOOST = "attr_boost"          # 属性加成


class BuffLimit:
    """Buff限制类型"""
    TIMED = "timed"        # 时间限制（秒）
    USES = "uses"          # 次数限制
    JOB_COUNT = "job_count" # 工作次数
    INSTANT = "instant"    # 瞬时（立即生效后消失）


# ============================================================
# Buff定义表
# ============================================================

# 所有Buff的完整定义
# id: buff_id
# name: 显示名称
# emoji: 图标
# desc: 描述
# type: BuffType
# limit: BuffLimit
# value: 效果值 (倍率，如1.1表示+10%)
# duration: 持续时间（秒），timed类型需要
# uses: 使用次数，uses类型需要
# job_count: 工作次数，job_count类型需要
# source: 来源 (checkin/market/drop/etc)
# rarity: 稀有度 (common/rare/epic/legendary)

ALL_BUFFS = {
    # ===== 金币收益类 ===== (INCOME_MULTI)
    "income_10": {
        "id": "income_10",
        "name": "收益提升I",
        "emoji": "📈",
        "desc": "下次工作收益+10%",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.JOB_COUNT,
        "value": 0.1,
        "job_count": 1,
        "source": "checkin",
        "rarity": "common",
        "weight": 30,
    },
    "income_20": {
        "id": "income_20",
        "name": "收益提升II",
        "emoji": "📈📈",
        "desc": "下次工作收益+20%",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.JOB_COUNT,
        "value": 0.2,
        "job_count": 1,
        "source": "checkin",
        "rarity": "common",
        "weight": 20,
    },
    "income_30": {
        "id": "income_30",
        "name": "收益提升III",
        "emoji": "📈📈📈",
        "desc": "下次工作收益+30%",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.JOB_COUNT,
        "value": 0.3,
        "job_count": 1,
        "source": "checkin",
        "rarity": "rare",
        "weight": 10,
    },
    "double_income": {
        "id": "double_income",
        "name": "双倍收益",
        "emoji": "💰💰",
        "desc": "下次工作收益翻倍",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.JOB_COUNT,
        "value": 1.0,
        "job_count": 1,
        "source": "checkin",
        "rarity": "legendary",
        "weight": 5,
    },
    
    # ===== 消耗降低类 ===== (COST_REDUCE)
    "cost_half": {
        "id": "cost_half",
        "name": "高效工作",
        "emoji": "⚡",
        "desc": "下次工作体力/精力消耗-50%",
        "type": BuffType.COST_REDUCE,
        "limit": BuffLimit.JOB_COUNT,
        "value": 0.5,
        "job_count": 1,
        "source": "checkin",
        "rarity": "common",
        "weight": 25,
    },
    "cost_third": {
        "id": "cost_third",
        "name": "极限效率",
        "emoji": "🔥",
        "desc": "下次工作体力/精力消耗-70%",
        "type": BuffType.COST_REDUCE,
        "limit": BuffLimit.JOB_COUNT,
        "value": 0.3,
        "job_count": 1,
        "source": "checkin",
        "rarity": "rare",
        "weight": 8,
    },
    
    # ===== 经验加成类 ===== (EXP_MULTI)
    "exp_50": {
        "id": "exp_50",
        "name": "学习加速",
        "emoji": "📚",
        "desc": "下次学习获得+50%经验",
        "type": BuffType.EXP_MULTI,
        "limit": BuffLimit.USES,
        "value": 0.5,
        "uses": 1,
        "source": "checkin",
        "rarity": "common",
        "weight": 20,
    },
    "exp_double": {
        "id": "exp_double",
        "name": "知识爆发",
        "emoji": "🧠",
        "desc": "下次学习经验翻倍",
        "type": BuffType.EXP_MULTI,
        "limit": BuffLimit.USES,
        "value": 1.0,
        "uses": 1,
        "source": "checkin",
        "rarity": "rare",
        "weight": 8,
    },
    
    # ===== 属性加成类(时间限制) ===== (ATTR_BOOST)
    "strength_boost_1h": {
        "id": "strength_boost_1h",
        "name": "体力充沛",
        "emoji": "💪",
        "desc": "接下来1小时，体力恢复+50%",
        "type": BuffType.ATTR_BOOST,
        "limit": BuffLimit.TIMED,
        "attr": "strength",
        "value": 0.5,
        "duration": 3600,  # 1小时
        "source": "market",
        "rarity": "common",
        "weight": 25,
    },
    "energy_boost_2h": {
        "id": "energy_boost_2h",
        "name": "精力充沛",
        "emoji": "⚡",
        "desc": "接下来2小时，精力恢复+100%",
        "type": BuffType.ATTR_BOOST,
        "limit": BuffLimit.TIMED,
        "attr": "energy",
        "value": 1.0,
        "duration": 7200,  # 2小时
        "source": "market",
        "rarity": "common",
        "weight": 20,
    },
    "mood_boost_1h": {
        "id": "mood_boost_1h",
        "name": "心情愉悦",
        "emoji": "😊",
        "desc": "接下来1小时，心情恢复+100%",
        "type": BuffType.ATTR_BOOST,
        "limit": BuffLimit.TIMED,
        "attr": "mood",
        "value": 1.0,
        "duration": 3600,
        "source": "market",
        "rarity": "common",
        "weight": 20,
    },
    
    # ===== 稀有特殊Buff =====
    "lucky_day": {
        "id": "lucky_day",
        "name": "幸运日",
        "emoji": "🍀",
        "desc": "今日所有收益+15%，所有掉落概率+5%",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.TIMED,
        "value": 0.15,
        "duration": 86400,  # 24小时
        "source": "drop",
        "rarity": "epic",
        "weight": 3,
    },
    "golden_touch": {
        "id": "golden_touch",
        "name": "点金手",
        "emoji": "✨",
        "desc": "下一次工作结算时额外获得50金币",
        "type": BuffType.INCOME_MULTI,
        "limit": BuffLimit.JOB_COUNT,
        "value": 50,  # 固定值，不是倍率
        "job_count": 1,
        "is_fixed": True,  # 标记为固定值
        "source": "drop",
        "rarity": "rare",
        "weight": 10,
    },
}


# ============================================================
# Buff来源分类
# ============================================================

BUFF_BY_SOURCE = {
    "checkin": ["income_10", "income_20", "income_30", "double_income", 
                "cost_half", "cost_third", "exp_50", "exp_double"],
    "market": ["strength_boost_1h", "energy_boost_2h", "mood_boost_1h"],
    "drop": ["lucky_day", "golden_touch"],
}


# ============================================================
# Buff工具类
# ============================================================

class BuffManager:
    """Buff管理器"""
    
    @staticmethod
    def create_buff_instance(buff_id: str, acquired_at: datetime = None) -> Optional[dict]:
        """从buff定义创建实例
        
        Args:
            buff_id: buff定义ID
            acquired_at: 获取时间
        
        Returns:
            dict: buff实例，包含剩余次数/时间等运行时数据
        """
        if acquired_at is None:
            acquired_at = datetime.now(timezone.utc)
        
        buff_def = ALL_BUFFS.get(buff_id)
        if not buff_def:
            return None
        
        instance = buff_def.copy()
        instance["instance_id"] = f"{buff_id}_{int(acquired_at.timestamp())}_{random.randint(1000,9999)}"
        instance["acquired_at"] = acquired_at.isoformat()
        
        # 根据limit类型设置初始剩余值
        limit = buff_def["limit"]
        if limit == BuffLimit.TIMED:
            instance["remaining_time"] = buff_def["duration"]
            instance["expire_at"] = (acquired_at.timestamp() + buff_def["duration"])
        elif limit == BuffLimit.USES:
            instance["remaining_uses"] = buff_def["uses"]
        elif limit == BuffLimit.JOB_COUNT:
            instance["remaining_jobs"] = buff_def["job_count"]
        
        return instance
    
    @staticmethod
    def is_expired(buff_instance: dict) -> bool:
        """检查buff是否过期"""
        limit = buff_instance.get("limit")
        
        if limit == BuffLimit.TIMED:
            import time
            expire_at = buff_instance.get("expire_at", 0)
            return time.time() > expire_at
        
        elif limit == BuffLimit.USES:
            return buff_instance.get("remaining_uses", 0) <= 0
        
        elif limit == BuffLimit.JOB_COUNT:
            return buff_instance.get("remaining_jobs", 0) <= 0
        
        elif limit == BuffLimit.INSTANT:
            return True  # 瞬时buff立即过期
        
        return False
    
    @staticmethod
    def consume_buff(buff_instance: dict) -> bool:
        """消耗一次buff使用次数
        
        Returns:
            bool: 是否消耗成功（还有剩余）
        """
        limit = buff_instance.get("limit")
        
        if limit == BuffLimit.USES:
            buff_instance["remaining_uses"] = max(0, buff_instance.get("remaining_uses", 1) - 1)
            return buff_instance["remaining_uses"] > 0
        
        elif limit == BuffLimit.JOB_COUNT:
            buff_instance["remaining_jobs"] = max(0, buff_instance.get("remaining_jobs", 1) - 1)
            return buff_instance["remaining_jobs"] > 0
        
        elif limit == BuffLimit.TIMED:
            # 时间限制buff不需要消耗
            return True
        
        return False
    
    @staticmethod
    def get_effective_buffs(buffs: list, filter_type: str = None) -> list:
        """获取当前有效的buff列表
        
        Args:
            buffs: 用户buff列表
            filter_type: 过滤类型（如BuffType.INCOME_MULTI）
        
        Returns:
            list: 有效的buff实例列表
        """
        effective = []
        for buff in buffs:
            if BuffManager.is_expired(buff):
                continue
            if filter_type and buff.get("type") != filter_type:
                continue
            effective.append(buff)
        return effective
    
    @staticmethod
    def roll_buff_from_source(source: str, exclude_ids: list = None) -> Optional[dict]:
        """从指定来源抽取一个buff
        
        Args:
            source: 来源 (checkin/market/drop)
            exclude_ids: 排除的buff_id列表
        
        Returns:
            dict: 抽中的buff实例，或None
        """
        buff_ids = BUFF_BY_SOURCE.get(source, [])
        
        # 过滤排除的buff
        if exclude_ids:
            buff_ids = [bid for bid in buff_ids if bid not in exclude_ids]
        
        if not buff_ids:
            return None
        
        # 根据权重抽取
        weights = [ALL_BUFFS[bid]["weight"] for bid in buff_ids]
        total_weight = sum(weights)
        
        if total_weight <= 0:
            return None
        
        rand = random.random() * total_weight
        cumulative = 0
        
        for i, buff_id in enumerate(buff_ids):
            cumulative += weights[i]
            if rand <= cumulative:
                return BuffManager.create_buff_instance(buff_id)
        
        return None
    
    @staticmethod
    def calculate_income_multi(buffs: list) -> float:
        """计算金币收益倍率（所有同类buff叠加）"""
        effective = BuffManager.get_effective_buffs(buffs, BuffType.INCOME_MULTI)
        multi = 0.0
        for buff in effective:
            if buff.get("is_fixed"):
                # 固定值不计入倍率
                continue
            multi += buff.get("value", 0.0)
        return 1.0 + multi
    
    @staticmethod
    def calculate_fixed_income_bonus(buffs: list) -> int:
        """计算固定金币加成"""
        effective = BuffManager.get_effective_buffs(buffs, BuffType.INCOME_MULTI)
        bonus = 0
        for buff in effective:
            if buff.get("is_fixed"):
                bonus += int(buff.get("value", 0))
        return bonus
    
    @staticmethod
    def calculate_cost_multi(buffs: list) -> float:
        """计算消耗倍率（相乘）"""
        effective = BuffManager.get_effective_buffs(buffs, BuffType.COST_REDUCE)
        multi = 1.0
        for buff in effective:
            multi *= buff.get("value", 1.0)
        return multi
    
    @staticmethod
    def calculate_exp_multi(buffs: list) -> float:
        """计算经验倍率"""
        effective = BuffManager.get_effective_buffs(buffs, BuffType.EXP_MULTI)
        multi = 0.0
        for buff in effective:
            multi += buff.get("value", 0.0)
        return 1.0 + multi
    
    @staticmethod
    def format_buff_instance(buff: dict) -> str:
        """格式化单个buff为字符串"""
        emoji = buff.get("emoji", "✨")
        name = buff.get("name", "未知")
        desc = buff.get("desc", "")
        
        lines = [f"{emoji} {name}"]
        lines.append(f"   └ {desc}")
        
        # 添加剩余次数/时间
        limit = buff.get("limit")
        if limit == BuffLimit.TIMED:
            remaining = max(0, buff.get("remaining_time", 0))
            if remaining > 0:
                if remaining >= 3600:
                    lines.append(f"   └ 剩余: {int(remaining/3600)}小时")
                else:
                    lines.append(f"   └ 剩余: {int(remaining/60)}分钟")
        elif limit == BuffLimit.USES:
            lines.append(f"   └ 剩余次数: {buff.get('remaining_uses', 0)}")
        elif limit == BuffLimit.JOB_COUNT:
            lines.append(f"   └ 剩余工作: {buff.get('remaining_jobs', 0)}次")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_buff_list(buffs: list, filter_type: str = None) -> str:
        """格式化buff列表为字符串"""
        effective = BuffManager.get_effective_buffs(buffs, filter_type)
        
        if not effective:
            return "暂无生效的buff"
        
        lines = []
        for buff in effective:
            lines.append(BuffManager.format_buff_instance(buff))
            lines.append("")
        
        return "\n".join(lines).strip()


# 导出快捷函数
create_buff = BuffManager.create_buff_instance
is_buff_expired = BuffManager.is_expired
consume_buff = BuffManager.consume_buff
get_effective_buffs = BuffManager.get_effective_buffs
roll_buff = BuffManager.roll_buff_from_source
calc_income_multi = BuffManager.calculate_income_multi
calc_cost_multi = BuffManager.calculate_cost_multi
calc_exp_multi = BuffManager.calculate_exp_multi
get_fixed_bonus = BuffManager.calculate_fixed_income_bonus
format_buffs = BuffManager.format_buff_list
