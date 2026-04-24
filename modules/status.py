"""
状态机模块
包含状态转换逻辑、被动恢复倍率等
"""
from datetime import datetime


class StatusTransition:
    """状态转换工具类"""
    
    # 夜间时段定义 (1:00 - 7:00)
    NIGHT_START = 1
    NIGHT_END = 7
    
    @staticmethod
    def should_auto_sleep(current_status: str, current_hour: int) -> bool:
        """判断是否应该自动进入睡眠
        
        Args:
            current_status: 当前状态
            current_hour: 当前小时 (0-23)
        
        Returns:
            bool: 是否应该自动睡眠
        """
        # 只在夜间时段(1:00-7:00)检测
        if current_hour < StatusTransition.NIGHT_START or current_hour >= StatusTransition.NIGHT_END:
            return False
        # 只对 FREE 状态的用户自动睡眠
        return current_status == "空闲"
    
    @staticmethod
    def get_passive_recovery_multiplier(residence: str) -> float:
        """获取被动恢复倍率（基于住所）
        
        Args:
            residence: 住所名称
        
        Returns:
            float: 恢复倍率
        """
        multipliers = {
            "桥下": 1.0,
            "地下室": 1.2,
            "合租房": 1.5,
            "公寓": 1.8,
            "景江公寓": 2.5,
            "别墅": 3.0,
            "海豹国际": 4.0,
        }
        return multipliers.get(residence, 1.0)
    
    @staticmethod
    def calc_hours_to_morning(now: datetime) -> float:
        """计算到早上7:00的小时数
        
        Args:
            now: 当前时间
        
        Returns:
            float: 到早上7:00的小时数
        """
        current_hour = now.hour
        current_minute = now.minute
        
        if current_hour < StatusTransition.NIGHT_START:
            # 0:00-0:59，距离1:00不到1小时
            return (60 - current_minute) / 60
        elif current_hour < StatusTransition.NIGHT_END:
            # 1:00-6:59，距离7:00
            return (StatusTransition.NIGHT_END - current_hour) - current_minute / 60
        else:
            # 7:00-23:59，距离次日7:00
            return (24 - current_hour) + StatusTransition.NIGHT_START - current_minute / 60
    
    @staticmethod
    def can_transition_to(current_status: str, target_status: str) -> bool:
        """检查是否能从当前状态转换到目标状态
        
        Args:
            current_status: 当前状态
            target_status: 目标状态
        
        Returns:
            bool: 是否允许转换
        """
        # 定义允许的状态转换
        allowed_transitions = {
            "空闲": ["工作中", "睡眠中", "学习中", "娱乐中"],
            "工作中": ["空闲", "睡眠中"],
            "睡眠中": ["空闲"],
            "学习中": ["空闲", "睡眠中"],
            "娱乐中": ["空闲", "睡眠中"],
        }
        
        return target_status in allowed_transitions.get(current_status, [])