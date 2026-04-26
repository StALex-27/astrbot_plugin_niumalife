"""
配置常量模块
负责从 JSON 文件加载所有配置数据
"""
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "data" / "config"


def load_json(name: str) -> dict:
    """加载 JSON 配置文件"""
    with open(CONFIG_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


# 加载所有配置
ITEMS = load_json("items")
STOCKS = load_json("stocks")

# 食物系统已合并到 ITEMS，按 category="food" 过滤
FOODS = {k: v for k, v in ITEMS.items() if v.get("category") == "food"}
RESIDENCES = load_json("residences")
JOBS = load_json("jobs")
COURSES = load_json("courses")
ENTERTAINMENTS = load_json("entertainments")
# 游戏初始值常量
INITIAL_GOLD = 0
INITIAL_ATTRIBUTES = {
    "health": 100,
    "strength": 100,
    "energy": 100,
    "mood": 100,
    "satiety": 100,
}
INITIAL_SKILLS = {"苦力": 1}
MAX_ATTRIBUTE = 100

# Tick 常量
TICKS_PER_HOUR = 60  # 每小时 tick 数（1 tick = 1 分钟）


# ============================================================
# 压力系统配置
# ============================================================

# 压力阈值与效率惩罚（0-100）
PRESSURE_THRESHOLDS = [
    (50, 0.10),   # 50-60%: -10%
    (60, 0.15),   # 60-70%: -15%
    (70, 0.20),   # 70-80%: -20%
    (80, 0.25),   # 80-90%: -25%
    (90, 0.30),   # 90-100%: -30%
]


def get_pressure_penalty(pressure: float) -> float:
    """根据压力值获取效率惩罚倍率"""
    penalty = 0.0
    for threshold, p in PRESSURE_THRESHOLDS:
        if pressure >= threshold:
            penalty = p
    return penalty


# 工作类型 → 压力类型映射
JOB_PRESSURE_TYPE = {
    # 体力型工作 → 身体疲劳
    "搬砖": "body",
    "清洁工": "body",
    "外卖配送": "body",
    "快递分拣": "body",
    "工地小工": "body",
    # 脑力/技能型工作 → 精神压力
    "文员": "mind",
    "数据录入": "mind",
    "客服": "mind",
    "会计": "mind",
    "程序员": "mind",
    "销售": "mind",
    "项目经理": "mind",
    "技术总监": "mind",
    "企业顾问": "mind",
}

# 工作每小时积累的压力值
JOB_PRESSURE_RATE = {
    # 体力型
    "搬砖": 3,
    "清洁工": 3,
    "外卖配送": 4,
    "快递分拣": 4,
    "工地小工": 5,
    # 脑力/技能型
    "文员": 3,
    "数据录入": 4,
    "客服": 5,
    "会计": 5,
    "程序员": 6,
    "销售": 5,
    "项目经理": 6,
    "技术总监": 7,
    "企业顾问": 7,
}

# 压力衰减配置
PRESSURE_DECAY_IDLE = 2       # 空闲时每小时每种压力衰减

# 娱乐对应的压力缓解（娱乐名称 → {body/mind: 缓解值}）
ENTERTAINMENT_PRESSURE_RELIEF = {
    # 名称: {身体疲劳缓解%, 精神压力缓解%}
    "按摩": {"body": 15, "mind": 5},
    "SPA": {"body": 20, "mind": 8},
    "游戏": {"body": 3, "mind": 15},
    "电影": {"body": 2, "mind": 12},
    "旅游": {"body": 10, "mind": 20},
    "酒吧": {"body": 5, "mind": 18},
    "运动": {"body": 18, "mind": 10},
    "阅读": {"body": 3, "mind": 15},
}


# ============================================================
# Debuff系统配置
# ============================================================

DEBUFF_ATTR_THRESHOLD = 20      # 属性低值触发阈值
DEBUFF_RECOVERY_THRESHOLD = 50  # 恢复到 >= 此值时解除 debuff

# Debuff 定义
DEBUFF_DEFINITIONS = {
    "weak": {
        "id": "weak",
        "name": "虚弱",
        "emoji": "😵",
        "attr": "strength",
        "effect": "income_penalty",
        "value": 0.30,
        "desc": "体力不足，工作收入 -30%",
    },
    "tired": {
        "id": "tired",
        "name": "疲劳",
        "emoji": "😴",
        "attr": "energy",
        "effect": "learn_penalty",
        "value": 0.30,
        "desc": "精力不足，学习效率 -30%",
    },
    "depressed": {
        "id": "depressed",
        "name": "抑郁",
        "emoji": "😔",
        "effect": "all_penalty",
        "value": 0.20,
        "desc": "心情低落，所有活动效率 -20%",
    },
    "hungry": {
        "id": "hungry",
        "name": "饥饿",
        "emoji": "🍽️",
        "attr": "satiety",
        "effect": "strength_drain",
        "value": 1.0,
        "desc": "饱食不足，每分钟额外消耗体力",
    },
    "sick": {
        "id": "sick",
        "name": "疾病",
        "emoji": "🤒",
        "attr": "health",
        "effect": "recovery_penalty",
        "value": 0.50,
        "desc": "健康不佳，被动恢复效率 -50%",
    },
}


# ============================================================
# 医院系统配置
# ============================================================

HOSPITAL_COST_PER_HOUR = 30          # 每小时消耗金币
HOSPITAL_HEALTH_PER_HOUR = 5         # 每小时恢复健康
HOSPITAL_STRENGTH_PER_HOUR = 2      # 每小时恢复体力
HOSPITAL_ENERGY_PER_HOUR = 2        # 每小时恢复精力
HOSPITAL_MOOD_TARGET = 20            # 心情固定值
HOSPITAL_DISCHARGE_THRESHOLD = 50    # 出院需要健康 >= 此值


# ============================================================
# 通用格式化工具
# ============================================================

SEPARATOR = "━━━━━━━━━━━━━━"


def section(title: str = None, content: str = None, footer: bool = True) -> str:
    """格式化文本区块"""
    lines = []
    lines.append(SEPARATOR)
    if title:
        lines.append(f"「 {title} 」")
        lines.append(SEPARATOR)
    if content:
        lines.append(content)
    if footer:
        lines.append(SEPARATOR)
    return "\n".join(lines)


def format_attributes(attrs: dict) -> str:
    """格式化属性显示"""
    bars = []
    for key, label in [
        ("health", "❤️ 健康"),
        ("strength", "💪 体力"),
        ("energy", "⚡ 精力"),
        ("mood", "😊 心情"),
        ("satiety", "🍖 饱食"),
    ]:
        value = int(attrs.get(key, 0))
        bar_count = value // 10
        bar = "█" * bar_count + "░" * (10 - bar_count)
        bars.append(f"{label}: {bar} {value}")
    return "\n".join(bars)


def format_error(msg: str) -> str:
    """格式化错误消息"""
    return f"⚠️ {msg}"


def format_success(msg: str) -> str:
    """格式化成功消息"""
    return f"✅ {msg}"
