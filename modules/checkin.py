"""
签到模块
包含每日签到、欧气评级、连续签到奖励、幸运掉落等
"""
import random
from datetime import datetime, timezone
from typing import Optional

from .constants import FOODS, ITEMS


# 欧气评级定义
LUCK_RATINGS = {
    (1, 1): {"name": "超级非酋", "emoji": "💀", "desc": "今日运势：踩到狗屎运了"},
    (2, 10): {"name": "非酋", "emoji": "😣", "desc": "今日运势：诸事不宜"},
    (11, 50): {"name": "普通人", "emoji": "😐", "desc": "今日运势：平平无奇"},
    (51, 90): {"name": "欧皇", "emoji": "😄", "desc": "今日运势：好事发生"},
    (91, 99): {"name": "欧皇", "emoji": "🤩", "desc": "今日运势：心想事成"},
    (100, 100): {"name": "超级欧皇", "emoji": "🤑", "desc": "今日运势：神眷顾你"},
}

# 连续签到奖励
STREAK_REWARDS = {
    3: {"gold": 20, "name": "连签3日", "emoji": "🌟"},
    7: {"gold": 50, "name": "连签7日", "emoji": "🌟🌟"},
    15: {"gold": 100, "name": "连签15日", "emoji": "💫"},
    30: {"gold": 200, "name": "连签30日", "emoji": "✨"},
}

# 幸运掉落奖池
LUCKY_DROP_GOLD = [50, 100, 200, 500]
LUCKY_DROP_WEIGHTS = [50, 30, 15, 5]  # 权重：50金50%，100金30%，200金15%，500金5%

# 幸运掉落基础概率
BASE_DROP_CHANCE = 0.05  # 5%

# 连续签到额外掉落概率
STREAK_DROP_BONUS = {
    0: 0,    # 无额外
    3: 0.03, # +3%
    7: 0.05, # +5%
    15: 0.07,# +7%
    30: 0.10,# +10%
}

# 临时buff定义
TEMP_BUFFS = {
    "income_10": {
        "name": "收益提升I",
        "desc": "下次工作收益+10%",
        "emoji": "📈",
        "duration_job": True,
        "effect": {"income_multi": 0.1}
    },
    "income_20": {
        "name": "收益提升II",
        "desc": "下次工作收益+20%",
        "emoji": "📈📈",
        "duration_job": True,
        "effect": {"income_multi": 0.2}
    },
    "income_30": {
        "name": "收益提升III",
        "desc": "下次工作收益+30%",
        "emoji": "📈📈📈",
        "duration_job": True,
        "effect": {"income_multi": 0.3}
    },
    "cost_half": {
        "name": "高效工作",
        "desc": "下次工作体力/精力消耗-50%",
        "emoji": "⚡",
        "duration_job": True,
        "effect": {"cost_multi": 0.5}
    },
    "double_income": {
        "name": "双倍收益",
        "desc": "下次工作收益翻倍",
        "emoji": "💰💰",
        "duration_job": True,
        "effect": {"income_multi": 1.0}
    },
}

# buff触发权重
BUFF_WEIGHTS = {
    "income_10": 30,
    "income_20": 20,
    "income_30": 10,
    "cost_half": 25,
    "double_income": 5,  # 稀有
}


def get_luck_rating(luck_value: int) -> dict:
    """根据随机值获取欧气评级"""
    for (min_val, max_val), rating in LUCK_RATINGS.items():
        if min_val <= luck_value <= max_val:
            return rating
    return LUCK_RATINGS[(11, 50)]


def get_streak_reward(streak_days: int) -> Optional[dict]:
    """获取连续签到奖励（返回达成的最高档位）"""
    achieved = None
    for threshold, reward in STREAK_REWARDS.items():
        if streak_days >= threshold:
            achieved = reward.copy()
            achieved["threshold"] = threshold
    return achieved


def get_drop_chance(streak_days: int) -> float:
    """获取幸运掉落概率"""
    bonus = 0
    for threshold, bonus_val in STREAK_DROP_BONUS.items():
        if streak_days >= threshold:
            bonus = bonus_val
    return BASE_DROP_CHANCE + bonus


def roll_lucky_drop(streak_days: int) -> Optional[dict]:
    """掷骰子决定是否触发幸运掉落"""
    chance = get_drop_chance(streak_days)
    if random.random() > chance:
        return None
    
    # 决定掉落类型：金币(60%)、食品(20%)、道具(15%)、buff(5%)
    roll = random.random()
    
    if roll < 0.60:
        # 金币掉落
        gold_amount = random.choices(LUCKY_DROP_GOLD, weights=LUCKY_DROP_WEIGHTS, k=1)[0]
        return {
            "type": "gold",
            "item": {"name": f"{gold_amount}金币", "emoji": "💰"},
            "amount": gold_amount
        }
    elif roll < 0.80:
        # 食品掉落
        food_list = list(FOODS.items())
        if food_list:
            name, food = random.choice(food_list)
            return {
                "type": "food",
                "item": {"name": name, "emoji": "🍖"},
                "food_data": (name, food)
            }
    elif roll < 0.95:
        # 道具/装备掉落
        item_list = list(ITEMS.items())
        if item_list:
            name, item = random.choice(item_list)
            return {
                "type": "item",
                "item": {"name": name, "emoji": item.get("emoji", "📦")},
                "item_data": (name, item)
            }
    else:
        # buff掉落（从权重池抽取）
        buff_id = random.choices(list(BUFF_WEIGHTS.keys()), weights=list(BUFF_WEIGHTS.values()), k=1)[0]
        buff = TEMP_BUFFS[buff_id]
        return {
            "type": "buff",
            "item": {"name": buff["name"], "emoji": buff["emoji"]},
            "buff_id": buff_id,
            "buff_data": buff
        }
    
    return None


def format_checkin_report(
    luck_value: int,
    base_gold: int,
    streak_days: int,
    streak_reward: Optional[dict],
    drop: Optional[dict],
    total_gold: int
) -> str:
    """格式化签到报告"""
    rating = get_luck_rating(luck_value)
    
    lines = [
        "━━━━━━━━━━━━━━",
        "「 每 日 签 到 」",
        "━━━━━━━━━━━━━━",
        "",
        f"🎰 欧气评定：{rating['emoji']} {rating['name']}",
        f"📝 {rating['desc']}",
        "",
        f"🎲 随机数：{luck_value}",
        f"💰 基础奖励：+{base_gold} 金币",
    ]
    
    # 连续签到奖励
    if streak_reward:
        lines.append(f"🔥 连续签到：{streak_reward['emoji']} {streak_reward['name']} +{streak_reward['gold']} 金币")
    
    # 幸运掉落
    if drop:
        lines.append("")
        lines.append(f"⭐ 幸运掉落：{drop['item']['emoji']} {drop['item']['name']}")
        if drop["type"] == "buff":
            lines.append(f"   └ {drop['buff_data']['desc']}")
    
    lines.extend([
        "",
        "━━━━━━━━━━━━━━",
        f"💰 本次签到：+{total_gold} 金币",
        f"📅 连续签到：{streak_days} 天",
        "━━━━━━━━━━━━━━",
    ])
    
    return "\n".join(lines)


def get_next_streak_threshold(current_streak: int) -> Optional[tuple]:
    """获取下一个签到奖励档位"""
    for threshold in sorted(STREAK_REWARDS.keys()):
        if current_streak < threshold:
            return (threshold, STREAK_REWARDS[threshold])
    return None  # 已满所有档位
