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
# 通用格式化工具
# ============================================================

SEPARATOR = "━━━━━━━━━━━━━━"

def section(title: str = None, content: str = None, footer: bool = True) -> str:
    """格式化文本区块
    
    Args:
        title: 区块标题
        content: 区块内容
        footer: 是否显示底部分隔线
    
    Returns:
        格式化后的字符串
    """
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
