"""
打工系统 V2 - 公司商店模块
基于公司好感度的装备/道具商店
"""

import json
import random
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ShopItem:
    """商店物品"""
    item_id: str
    name: str
    rarity: str
    price: int
    description: str
    buff_effect: dict
    
    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "rarity": self.rarity,
            "price": self.price,
            "description": self.description,
            "buff_effect": self.buff_effect,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ShopItem":
        return cls(**data)


class CompanyShop:
    """
    公司商店管理器
    每个公司有自己的商店，好感度越高可购买的物品种类越多
    """
    
    RARITY_ORDER = ["common", "rare", "epic", "legendary", "mythic"]
    RARITY_EMOJI = {
        "common": "⚪",
        "rare": "🔵",
        "epic": "🟣",
        "legendary": "🟡",
        "mythic": "🔴",
    }
    RARITY_COLORS = {
        "common": "灰色",
        "rare": "蓝色",
        "epic": "紫色",
        "legendary": "金色",
        "mythic": "红色",
    }
    
    # 好感度等级对应的商店Tier
    TIER_REQUIREMENTS = {
        1: 0,  # 陌生人 - 不能买
        2: 0,  # 路人 - 不能买
        3: 0,  # 初识 - 不能买
        4: 0,  # 认识 - 不能买
        5: 0,  # 熟人 - 不能买
        6: 1,  # 朋友 - T1普通商店
        7: 1,  # 好友 - T1普通商店
        8: 2,  # 核心成员 - T2高级商店
        9: 2,  # 精英 - T2高级商店
        10: 2, # 传说 - T2高级商店
    }
    
    def __init__(self, config_dir: str = None):
        """初始化商店管理器"""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "data" / "config"
        self.config_dir = Path(config_dir)
        
        self._load_config()
        
    def _load_config(self):
        """加载商店配置"""
        with open(self.config_dir / "company_shops.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # 提取公司商店数据
        self.company_shops: Dict[str, dict] = {}
        self.rarity_colors = config.get("_rarity_colors", self.RARITY_COLORS)
        self.rarity_drop_rates = config.get("_rarity_drop_rates", {})
        self.shop_unlock_reqs = config.get("_shop_unlock_requirements", {"tier1": 6, "tier2": 8})
        self.buff_definitions = config.get("_buff_type_definitions", {})
        
        for key, value in config.items():
            if key.startswith("_"):
                continue
            self.company_shops[key] = value
            
    def get_shop_tier(self, favor_level: int) -> int:
        """根据好感度等级获取可访问的商店Tier"""
        return self.TIER_REQUIREMENTS.get(favor_level, 0)
        
    def can_access_shop(self, favor_level: int) -> bool:
        """检查是否可以访问商店"""
        return self.get_shop_tier(favor_level) >= 1
        
    def can_access_tier2(self, favor_level: int) -> bool:
        """检查是否可以访问高级商店"""
        return self.get_shop_tier(favor_level) >= 2
        
    def get_available_items(self, company_id: str, favor_level: int) -> List[ShopItem]:
        """
        获取指定公司可用购买的物品
        
        Args:
            company_id: 公司ID
            favor_level: 好感度等级 (1-10)
            
        Returns:
            可购买的物品列表
        """
        shop_data = self.company_shops.get(company_id, {})
        tier = self.get_shop_tier(favor_level)
        
        items = []
        
        # T1物品（好感度等级6+）
        if tier >= 1:
            tier1_items = shop_data.get("tier1", {}).get("items", [])
            for item_data in tier1_items:
                items.append(ShopItem.from_dict(item_data))
                
        # T2物品（好感度等级8+）
        if tier >= 2:
            tier2_items = shop_data.get("tier2", {}).get("items", [])
            for item_data in tier2_items:
                items.append(ShopItem.from_dict(item_data))
                
        return items
        
    def get_shop_display(self, company_id: str, favor_level: int) -> Tuple[str, List[str]]:
        """
        获取商店显示信息
        
        Returns:
            (shop_name, lines)
        """
        shop_data = self.company_shops.get(company_id, {})
        shop_name = shop_data.get("shop_name", "公司商店")
        
        tier = self.get_shop_tier(favor_level)
        tier_label = "普通商店" if tier == 1 else "高级商店" if tier >= 2 else "未解锁"
        
        lines = [
            f"🏪 {shop_name}",
            f"   访问等级: {tier_label}"
        ]
        
        if tier == 0:
            lines.append("\n   好感度达到Lv.6（朋友）解锁商店")
            return shop_name, lines
            
        items = self.get_available_items(company_id, favor_level)
        
        if not items:
            lines.append("\n   暂无商品")
            return shop_name, lines
            
        # 按稀有度分组显示
        lines.append("")
        
        for rarity in self.RARITY_ORDER:
            rarity_items = [i for i in items if i.rarity == rarity]
            if not rarity_items:
                continue
                
            emoji = self.RARITY_EMOJI.get(rarity, "⚪")
            color = self.rarity_colors.get(rarity, rarity)
            lines.append(f"\n  {emoji} {color}品质")
            
            for item in rarity_items:
                lines.append(
                    f"    • {item.name} - {item.price}金币\n"
                    f"      {item.description}"
                )
                
        return shop_name, lines
        
    def format_shop_items(self, company_id: str, favor_level: int) -> str:
        """格式化商店物品列表"""
        shop_data = self.company_shops.get(company_id, {})
        shop_name = shop_data.get("shop_name", "公司商店")
        
        tier = self.get_shop_tier(favor_level)
        
        lines = ["═══════════════════════════"]
        lines.append(f"    「 {shop_name} 」")
        lines.append("═══════════════════════════")
        
        if tier == 0:
            lines.append("\n🔒 商店未解锁")
            lines.append("需要好感度达到 Lv.6（朋友）")
            lines.append("\n═══════════════════════════")
            return "\n".join(lines)
            
        items = self.get_available_items(company_id, favor_level)
        
        if not items:
            lines.append("\n暂无商品")
        else:
            for rarity in self.RARITY_ORDER:
                rarity_items = [i for i in items if i.rarity == rarity]
                if not rarity_items:
                    continue
                    
                emoji = self.RARITY_EMOJI.get(rarity, "⚪")
                color = self.rarity_colors.get(rarity, rarity)
                
                lines.append(f"\n{emoji} {color} [{len(rarity_items)}件]")
                
                for item in rarity_items:
                    lines.append(
                        f"  ├─ {item.name}"
                        f"\n│   💰 {item.price}金币"
                        f"\n│   📝 {item.description}"
                    )
                    
        lines.append("\n═══════════════════════════")
        lines.append(f"输入 /购买装备 <公司ID> <物品ID> 购买")
        
        return "\n".join(lines)
        
    def purchase_item(self, user_data: dict, company_id: str, 
                     item_id: str) -> Tuple[bool, str, dict]:
        """
        购买物品
        
        Returns:
            (是否成功, 消息, 物品数据)
        """
        # 检查公司是否存在
        if company_id not in self.company_shops:
            return False, f"公司不存在: {company_id}", {}
            
        # 检查好感度
        favor_mgr = None
        try:
            from ...modules.company_favorability import get_favorability_manager
            favor_mgr = get_favorability_manager()
        except ImportError:
            favor = user_data.get("company_favorability", {}).get(company_id, 0)
            favor_level = self._get_favor_level_number(favor)
            
        if favor_mgr:
            favor = favor_mgr.get_company_favorability(user_data, company_id)
            favor_level = favor_mgr.get_favor_level_number(favor)
            
        if not self.can_access_shop(favor_level):
            return False, f"好感度不足，需要 Lv.6（朋友）", {}
            
        # 查找物品
        items = self.get_available_items(company_id, favor_level)
        item = None
        for i in items:
            if i.item_id == item_id:
                item = i
                break
                
        if not item:
            return False, f"物品不存在或无法购买: {item_id}", {}
            
        # 检查金币
        user_gold = user_data.get("gold", 0)
        if user_gold < item.price:
            return False, f"金币不足，需要 {item.price}，现有 {user_gold}", {}
            
        # 扣除金币
        user_data["gold"] = user_gold - item.price
        
        # 添加物品到背包
        if "inventory" not in user_data:
            user_data["inventory"] = {}
        if item_id not in user_data["inventory"]:
            user_data["inventory"][item_id] = 0
        user_data["inventory"][item_id] += 1
        
        # 添加Buff效果
        self._apply_buff_effect(user_data, item.buff_effect)
        
        # 好感度增加
        if favor_mgr:
            favor_mgr.on_shop_purchase(user_data, company_id, item.price)
            
        return True, f"购买成功：{item.name}", item.to_dict()
        
    def _apply_buff_effect(self, user_data: dict, buff_effect: dict):
        """应用Buff效果到用户数据"""
        buff_type = buff_effect.get("type", "")
        value = buff_effect.get("value", 0)
        
        # 被动Buff（如装备加成）
        if "passive_buffs" not in user_data:
            user_data["passive_buffs"] = []
            
        passive_buff = {
            "type": buff_type,
            "value": value,
            "applicable_jobs": buff_effect.get("applicable_jobs", "all"),
        }
        
        # 检查是否已存在同类Buff，存在则更新
        for i, existing in enumerate(user_data["passive_buffs"]):
            if existing["type"] == buff_type and existing.get("applicable_jobs") == passive_buff["applicable_jobs"]:
                # 更新值（取较高）
                user_data["passive_buffs"][i]["value"] = max(existing["value"], value)
                return
                
        user_data["passive_buffs"].append(passive_buff)
        
    def _get_favor_level_number(self, favorability: int) -> int:
        """根据好感度数值获取等级数字"""
        if favorability < 50:
            return 1
        elif favorability < 100:
            return 2
        elif favorability < 150:
            return 3
        elif favorability < 200:
            return 4
        elif favorability < 300:
            return 5
        elif favorability < 400:
            return 6
        elif favorability < 500:
            return 7
        elif favorability < 600:
            return 8
        elif favorability < 800:
            return 9
        else:
            return 10
            
    def get_all_shops_summary(self, favor_data: dict) -> List[dict]:
        """
        获取所有商店摘要
        
        Args:
            favor_data: Dict[company_id, favorability]
            
        Returns:
            List[dict] - 商店信息列表
        """
        result = []
        
        for company_id, shop_data in self.company_shops.items():
            favor = favor_data.get(company_id, 0)
            favor_level = self._get_favor_level_number(favor)
            tier = self.get_shop_tier(favor_level)
            
            result.append({
                "company_id": company_id,
                "shop_name": shop_data.get("shop_name", "商店"),
                "tier": tier,
                "tier_label": "普通商店" if tier == 1 else "高级商店" if tier >= 2 else "未解锁",
                "item_count": len(self.get_available_items(company_id, favor_level)),
                "favor_required": 6 if tier >= 1 else "无",
            })
            
        return result
        
    def format_all_shops_summary(self, favor_data: dict) -> str:
        """格式化所有商店摘要"""
        shops = self.get_all_shops_summary(favor_data)
        
        lines = ["═══════════════════════════"]
        lines.append("    「 公 司 商 店 」")
        lines.append("═══════════════════════════")
        
        unlocked = [s for s in shops if s["tier"] >= 1]
        locked = [s for s in shops if s["tier"] == 0]
        
        if unlocked:
            lines.append("\n🔓 已解锁")
            for s in unlocked:
                lines.append(
                    f"\n  {s['shop_name']}"
                    f"\n    等级: {s['tier_label']}"
                    f"\n    商品: {s['item_count']}件"
                )
                
        if locked:
            lines.append("\n🔒 未解锁 (需要 Lv.6)")
            for s in locked:
                lines.append(f"\n  {s['shop_name']}")
                
        lines.append("\n═══════════════════════════")
        lines.append("输入 /公司商店 <公司ID> 查看详情")
        
        return "\n".join(lines)
        
    def get_item_by_id(self, company_id: str, item_id: str, 
                       favor_level: int = 10) -> Optional[ShopItem]:
        """根据ID获取物品详情"""
        items = self.get_available_items(company_id, favor_level)
        for item in items:
            if item.item_id == item_id:
                return item
        return None


# 全局实例
_shop_manager = None

def get_shop_manager(config_dir: str = None) -> CompanyShop:
    """获取商店管理器单例"""
    global _shop_manager
    if _shop_manager is None:
        _shop_manager = CompanyShop(config_dir)
    return _shop_manager


if __name__ == "__main__":
    # 测试代码
    shop = CompanyShop()
    
    # 测试获取物品
    print("=== 阿尔法劳务商店 (好感度Lv.6) ===")
    print(shop.format_shop_items("company_labor", 6))
    
    print("\n=== 贝塔科技商店 (好感度Lv.8) ===")
    print(shop.format_shop_items("company_tech", 8))
    
    print("\n=== 所有商店摘要 ===")
    favor_data = {
        "company_labor": 350,
        "company_tech": 500,
        "company_business": 100,
    }
    print(shop.format_all_shops_summary(favor_data))
