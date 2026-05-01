"""
打工系统 V2 - 公司好感度系统
管理玩家与各公司的好感度关系
"""

import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class CompanyFavorability:
    """公司好感度管理器"""
    
    # 好感度等级定义
    FAVOR_LEVELS = [
        {"level": 1, "min": 0, "max": 49, "name": "陌生人", "unlock": ["D级委托"]},
        {"level": 2, "min": 50, "max": 99, "name": "路人", "unlock": ["D级委托"]},
        {"level": 3, "min": 100, "max": 149, "name": "初识", "unlock": ["C级委托"]},
        {"level": 4, "min": 150, "max": 199, "name": "认识", "unlock": ["C级委托"]},
        {"level": 5, "min": 200, "max": 299, "name": "熟人", "unlock": ["B级委托"]},
        {"level": 6, "min": 300, "max": 399, "name": "朋友", "unlock": ["B级委托", "公司商店(普通)"]},
        {"level": 7, "min": 400, "max": 499, "name": "好友", "unlock": ["A级委托"]},
        {"level": 8, "min": 500, "max": 599, "name": "核心成员", "unlock": ["A级委托", "公司商店(高级)"]},
        {"level": 9, "min": 600, "max": 799, "name": "精英", "unlock": ["S级委托"]},
        {"level": 10, "min": 800, "max": 1000, "name": "传说", "unlock": ["S+级委托", "隐藏委托"]},
    ]
    
    # 好感度变化事件
    FAVOR_CHANGE_COMPLETE_BASE = 10
    FAVOR_CHANGE_FAIL_PENALTY = -20
    FAVOR_CHANGE_CANCEL_PENALTY = -5
    FAVOR_CHANGE_REJECT_PENALTY = -5
    FAVOR_CHANGE_SHOP_PURCHASE = 1  # 每消费1000金币
    
    # 最大好感度
    MAX_FAVORABILITY = 1000
    
    def __init__(self, config_dir: str = None):
        """初始化好感度管理器"""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "data" / "config"
        self.config_dir = Path(config_dir)
        
        self._load_companies_config()
        
    def _load_companies_config(self):
        """加载公司配置"""
        with open(self.config_dir / "companies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.companies = {k: v for k, v in data.items() if not k.startswith("_")}
            
    def get_player_favorability(self, user_data: dict) -> Dict[str, int]:
        """获取玩家所有公司的好感度"""
        return user_data.get("company_favorability", {})
        
    def get_company_favorability(self, user_data: dict, company_id: str) -> int:
        """获取玩家对特定公司的好感度"""
        favors = self.get_player_favorability(user_data)
        return favors.get(company_id, 0)
        
    def initialize_favorability(self, user_data: dict) -> Dict[str, int]:
        """初始化用户的好感度数据"""
        if "company_favorability" not in user_data:
            user_data["company_favorability"] = {}
        return user_data["company_favorability"]
        
    def get_favor_level(self, favorability: int) -> Dict:
        """根据好感度数值获取等级信息"""
        for level_info in self.FAVOR_LEVELS:
            if level_info["min"] <= favorability <= level_info["max"]:
                return level_info
        # 超过最大值
        return self.FAVOR_LEVELS[-1]
        
    def get_favor_level_number(self, favorability: int) -> int:
        """获取好感度等级数字"""
        return self.get_favor_level(favorability)["level"]
        
    def get_favor_level_name(self, favorability: int) -> str:
        """获取好感度等级名称"""
        return self.get_favor_level(favorability)["name"]
        
    def get_unlocked_content(self, favorability: int) -> List[str]:
        """获取该好感度等级解锁的内容"""
        return self.get_favor_level(favorability)["unlock"]
        
    def can_accept_difficulty(self, favorability: int, difficulty: str) -> bool:
        """检查好感度是否足够接受该难度委托"""
        favor_level = self.get_favor_level_number(favorability)
        required_level = self.get_required_level_for_difficulty(difficulty)
        return favor_level >= required_level
        
    def get_required_level_for_difficulty(self, difficulty: str) -> int:
        """获取接受某难度委托所需的最低好感度等级"""
        level_map = {
            "D": 1,
            "C": 3,
            "B": 5,
            "A": 7,
            "S": 9,
            "S+": 10
        }
        return level_map.get(difficulty, 1)
        
    def get_available_difficulties(self, favorability: int) -> List[str]:
        """获取当前好感度可接受的所有难度"""
        favor_level = self.get_favor_level_number(favorability)
        difficulties = []
        for diff, required in [("D", 1), ("C", 3), ("B", 5), ("A", 7), ("S", 9), ("S+", 10)]:
            if favor_level >= required:
                difficulties.append(diff)
        return difficulties
        
    def can_access_shop(self, favorability: int, shop_tier: int = 1) -> bool:
        """检查是否可以访问商店"""
        favor_level = self.get_favor_level_number(favorability)
        if shop_tier == 1:
            return favor_level >= 6  # 普通商店
        elif shop_tier == 2:
            return favor_level >= 8  # 高级商店
        return False
        
    def modify_favorability(self, user_data: dict, company_id: str, 
                           change: int, reason: str = "") -> Tuple[int, int]:
        """
        修改好感度
        
        Args:
            user_data: 用户数据
            company_id: 公司ID
            change: 变化值（正数增加，负数减少）
            reason: 变化原因日志
            
        Returns:
            (变化前的值, 变化后的值)
        """
        if "company_favorability" not in user_data:
            self.initialize_favorability(user_data)
            
        favors = user_data["company_favorability"]
        old_value = favors.get(company_id, 0)
        new_value = max(0, min(self.MAX_FAVORABILITY, old_value + change))
        favors[company_id] = new_value
        
        return old_value, new_value
        
    def on_job_complete(self, user_data: dict, company_id: str, 
                        difficulty: str, evaluation_grade: str) -> int:
        """
        任务完成时调用，增加好感度
        
        Returns:
            好感度变化值
        """
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        
        base = favor_table.get("complete_base", self.FAVOR_CHANGE_COMPLETE_BASE)
        diff_bonus = favor_table.get("complete_difficulty_bonus", 5)
        
        # 难度加成
        diff_map = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4, "S+": 5}
        diff_idx = diff_map.get(difficulty, 0)
        
        # 评价加成
        eval_bonus = 0
        if evaluation_grade == "S":
            eval_bonus = 10
        elif evaluation_grade == "A":
            eval_bonus = 5
        elif evaluation_grade in ["D", "F"]:
            eval_bonus = -5
            
        change = base + (diff_bonus * diff_idx) + eval_bonus
        
        _, new_value = self.modify_favorability(user_data, company_id, change, "job_complete")
        return change
        
    def on_job_fail(self, user_data: dict, company_id: str) -> int:
        """
        任务失败时调用，减少好感度
        
        Returns:
            好感度变化值
        """
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        penalty = favor_table.get("fail_penalty", self.FAVOR_CHANGE_FAIL_PENALTY)
        
        _, new_value = self.modify_favorability(user_data, company_id, penalty, "job_fail")
        return penalty
        
    def on_job_cancel(self, user_data: dict, company_id: str) -> int:
        """
        取消任务时调用，减少好感度
        
        Returns:
            好感度变化值
        """
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        penalty = favor_table.get("cancel_penalty", self.FAVOR_CHANGE_CANCEL_PENALTY)
        
        _, new_value = self.modify_favorability(user_data, company_id, penalty, "job_cancel")
        return penalty
        
    def on_reject_too_much(self, user_data: dict, company_id: str) -> int:
        """
        连续拒绝过多时调用，减少好感度
        
        Returns:
            好感度变化值
        """
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        penalty = favor_table.get("reject_penalty", self.FAVOR_CHANGE_REJECT_PENALTY)
        
        _, new_value = self.modify_favorability(user_data, company_id, penalty, "reject_too_much")
        return penalty
        
    def on_shop_purchase(self, user_data: dict, company_id: str, 
                         amount: int) -> int:
        """
        商店购物时增加好感度
        
        Args:
            amount: 消费金额
            
        Returns:
            好感度变化值
        """
        bonus = amount // 1000  # 每1000金币+1
        if bonus > 0:
            _, new_value = self.modify_favorability(user_data, company_id, bonus, "shop_purchase")
            return bonus
        return 0
        
    def get_reject_ban_hours(self, company_id: str) -> int:
        """获取拒绝过多时的禁止时间（小时）"""
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        return favor_table.get("reject_ban_hours", 2)
        
    def get_reject_count_threshold(self, company_id: str) -> int:
        """获取触发禁止的拒绝次数"""
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        return favor_table.get("reject_count_threshold", 3)
        
    def get_all_companies_summary(self, user_data: dict) -> List[Dict]:
        """
        获取所有公司的好感度摘要
        
        Returns:
            List[Dict] - 包含公司ID、名称、Emoji、好感度、等级等信息
        """
        favors = self.get_player_favorability(user_data)
        result = []
        
        for company_id, company_info in self.companies.items():
            if company_id.startswith("_"):
                continue
                
            favor = favors.get(company_id, 0)
            level_info = self.get_favor_level(favor)
            
            result.append({
                "company_id": company_id,
                "name": company_info.get("name", company_id),
                "emoji": company_info.get("emoji", ""),
                "favorability": favor,
                "level": level_info["level"],
                "level_name": level_info["name"],
                "unlocked": level_info["unlock"],
                "available_difficulties": self.get_available_difficulties(favor)
            })
            
        # 按好感度排序
        result.sort(key=lambda x: x["favorability"], reverse=True)
        return result
        
    def get_company_info(self, company_id: str) -> Optional[Dict]:
        """获取公司信息"""
        return self.companies.get(company_id)
        
    def get_all_company_ids(self) -> List[str]:
        """获取所有公司ID"""
        return [k for k in self.companies.keys() if not k.startswith("_")]


def get_favorability_manager(config_dir: str = None) -> CompanyFavorability:
    """获取好感度管理器单例"""
    if not hasattr(get_favorability_manager, "_instance"):
        get_favorability_manager._instance = CompanyFavorability(config_dir)
    return get_favorability_manager._instance


if __name__ == "__main__":
    # 测试代码
    fm = CompanyFavorability()
    
    test_user = {
        "company_favorability": {
            "company_tech": 350,
            "company_labor": 80,
            "company_business": 500
        }
    }
    
    print("=== 好感度等级查询 ===")
    for cid, favor in test_user["company_favorability"].items():
        level = fm.get_favor_level(favor)
        print(f"{cid}: {favor} -> Lv{level['level']} {level['name']}")
        print(f"  解锁: {level['unlock']}")
        print(f"  可接难度: {fm.get_available_difficulties(favor)}")
        
    print("\n=== 好感度变化测试 ===")
    change = fm.on_job_complete(test_user, "company_tech", "A", "A")
    print(f"完成任务后: +{change}")
    print(f"新技术好度: {test_user['company_favorability']['company_tech']}")
    
    print("\n=== 所有公司摘要 ===")
    summary = fm.get_all_companies_summary(test_user)
    for s in summary:
        print(f"{s['emoji']} {s['name']}: Lv{s['level']} {s['level_name']} ({s['favorability']})")
