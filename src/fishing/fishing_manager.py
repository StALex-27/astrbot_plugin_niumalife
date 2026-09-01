"""
钓鱼管理器 - 钓鱼系统的核心逻辑。

职责：
- 加载 FISHES / FISHING_SPOTS 数据
- 提供 roll_catch(user, spot_id, rod_id, bait_id) -> dict | None
- 提供 estimate_price(fish_name, weight, user) -> int
- 提供 check_fish_titles(user) -> str（授予称号）

设计原则：
- 纯函数为主，不依赖 plugin / store 等有状态对象（除调用方传入）
- 每个 tick 由 FishingTickProcessor 调用 roll_catch 决定是否中鱼
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional


# ============================================================
# 数据加载（懒加载单例）
# ============================================================

_DATA_DIR: Optional[Path] = None
FISHES: dict = {}
FISHING_SPOTS: dict = {}
RARITY_WEIGHT: dict = {}

_loaded = False


def _get_data_dir() -> Path:
    global _DATA_DIR
    if _DATA_DIR is None:
        # 路径: src/fishing/fishing_manager.py → 向上 4 级到插件根
        _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "config"
    return _DATA_DIR


def _ensure_loaded() -> None:
    global _loaded, FISHES, FISHING_SPOTS, RARITY_WEIGHT
    if _loaded:
        return
    data_dir = _get_data_dir()
    with open(data_dir / "fishes.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
    RARITY_WEIGHT = raw.pop("_rarity_weight", {
        "common": 1.0, "uncommon": 0.4, "rare": 0.12, "epic": 0.03, "legendary": 0.005,
    })
    # 过滤注释字段
    FISHES = {k: v for k, v in raw.items() if not k.startswith("_")}

    with open(data_dir / "fishing_spots.json", "r", encoding="utf-8") as f:
        raw_spots = json.load(f)
    FISHING_SPOTS = {k: v for k, v in raw_spots.items() if not k.startswith("_")}
    _loaded = True


# ============================================================
# 工具函数
# ============================================================

def get_fishing_skill_level(user: dict) -> int:
    """获取用户钓鱼技能等级（兼容老用户无 skill_exp 的情况）。"""
    skill_exp = user.get("skill_exp", {})
    exp = skill_exp.get("钓鱼", 0)
    # 简化：每 100 exp = 1 级
    return max(0, exp // 100)


def _skill_effect(skill_level: int, key: str, default: float = 0.0) -> float:
    """技能等级 → 加成值。从 skills.json 的 effects_per_level 读取。"""
    # 不读 JSON（避免 I/O），按设计文档约定硬编码
    # rare_bonus: 0.01/级；value_bonus: 0.005/级
    per_level = {"rare_bonus": 0.01, "value_bonus": 0.005}
    return skill_level * per_level.get(key, 0) + default


def _classify_size(fish: dict, weight: float) -> str:
    """根据 weight_range + size_thresholds 给尺寸标签。"""
    labels = fish.get("size_labels", ["普通"])
    thresholds = fish.get("size_thresholds", [])
    for i, t in enumerate(thresholds):
        if weight < t:
            return labels[i] if i < len(labels) else labels[-1]
    return labels[-1] if labels else "普通"


def _weight_fish_choice(candidates: list[dict], extra_rare_bonus: float) -> dict:
    """按 rarity_weight + 加成加权随机抽一条鱼。"""
    weights = []
    for f in candidates:
        w = RARITY_WEIGHT.get(f.get("rarity", "common"), 1.0)
        # 每 +0.01 rare_bonus = 加权翻倍近似
        w *= (1 + extra_rare_bonus * 20)
        weights.append(w)
    return random.choices(candidates, weights=weights, k=1)[0]


def get_spot(spot_id: str) -> Optional[dict]:
    _ensure_loaded()
    return FISHING_SPOTS.get(spot_id)


def get_fish(fish_id: str) -> Optional[dict]:
    _ensure_loaded()
    return FISHES.get(fish_id)


# ============================================================
# 核心：roll_catch
# ============================================================

# 每 tick 中鱼的"基础概率"，按 spot.tier 分档：
#   tier 1（村口池塘）= 50% — 新手区，鱼多易上钩
#   tier 2（城郊河边）= 30%
#   tier 3（深山水库）= 15% — 难度水域，需要好装备
# 鱼竿 fishing_bonus 直接累加（高端鱼竿可显著补正难度）
PER_TICK_CATCH_BASE_BY_TIER = {1: 0.50, 2: 0.30, 3: 0.15}
PER_TICK_CATCH_MAX = 0.80  # 概率上限 80%（让顶级鱼竿有意义）


def roll_catch(user: dict, spot_id: str, rod_effects: dict, bait_effects: dict) -> Optional[dict]:
    """每 tick 调用一次：决定是否中鱼。

    Args:
        user: 用户数据 dict
        spot_id: 水域 ID
        rod_effects: 鱼竿 effects dict（来自 ITEMS[id]["effects"]）
        bait_effects: 鱼饵 effects dict

    Returns:
        None = 没钓到；dict = 中鱼详情
    """
    _ensure_loaded()

    spot = get_spot(spot_id)
    if not spot:
        return None

    skill_level = get_fishing_skill_level(user)

    # 1. 基础成功率（按水域 tier 分档）
    tier = spot.get("tier", 1)
    base = PER_TICK_CATCH_BASE_BY_TIER.get(tier, 0.50)
    rod_bonus = rod_effects.get("fishing_bonus", 0.0)
    bait_rare = bait_effects.get("rare_bonus", 0.0)
    skill_rare = _skill_effect(skill_level, "rare_bonus")

    # 总成功率 = 基础 + 鱼竿 fishing_bonus（直接叠加，封顶 80%）
    success_rate = min(PER_TICK_CATCH_MAX, base + rod_bonus)
    if random.random() > success_rate:
        return None

    # 2. 抽鱼种（按水域可钓鱼种 + 稀有度权重）
    habitat_tags = spot.get("habitat_tags", [])
    candidates = [f for f in FISHES.values() if any(h in f.get("habitat", []) for h in habitat_tags)]
    if not candidates:
        return None

    extra_rare = bait_rare + skill_rare
    fish = _weight_fish_choice(candidates, extra_rare)

    # 3. 抽尺寸
    w_min, w_max = fish["weight_range"]
    min_size_bias = rod_effects.get("min_size_bonus", 0.0)
    weight = random.uniform(w_min, w_max) * (1 + min_size_bias)
    weight = round(weight, 2)
    size_label = _classify_size(fish, weight)

    # 4. 估算售价（基础价 × 尺寸因子）
    size_factor = 1.0 + (size_label_index(fish, size_label) * 0.15)
    skill_value = _skill_effect(skill_level, "value_bonus")
    estimated_price = int(fish["base_price"] * size_factor * (1 + skill_value))

    return {
        "fish_id": fish["name"],
        "fish": fish,
        "weight": weight,
        "size_label": size_label,
        "estimated_price": estimated_price,
    }


def size_label_index(fish: dict, size_label: str) -> int:
    labels = fish.get("size_labels", [])
    try:
        return labels.index(size_label)
    except ValueError:
        return 0


# ============================================================
# 结算：把鱼加入用户数据
# ============================================================

def apply_catch(user: dict, catch: dict, now_iso: str) -> None:
    """结算一条鱼：写入 fish_caught / fish_records / biggest_catch / 累计。"""
    fish_name = catch["fish_id"]
    weight = catch["weight"]
    size_label = catch["size_label"]

    fishing = user.setdefault("fishing", {
        "fish_caught": {}, "fish_records": [],
        "total_fishing_count": 0, "total_fishing_value": 0,
        "biggest_catch": {}, "fish_title": "",
    })

    # 累计计数
    fishing["fish_caught"][fish_name] = fishing["fish_caught"].get(fish_name, 0) + 1
    fishing["total_fishing_count"] = fishing.get("total_fishing_count", 0) + 1

    # 记录
    fishing.setdefault("fish_records", []).append({
        "fish": fish_name, "weight": weight,
        "size_label": size_label, "time": now_iso,
    })
    # 只保留最近 50 条
    if len(fishing["fish_records"]) > 50:
        fishing["fish_records"] = fishing["fish_records"][-50:]

    # 最大单条
    prev_biggest = fishing.get("biggest_catch", {}).get("weight", 0)
    if weight > prev_biggest:
        fishing["biggest_catch"] = {"fish": fish_name, "weight": weight, "size_label": size_label}

    # lifetime_stats
    lifetime = user.setdefault("lifetime_stats", {})
    lifetime["total_fish_caught"] = lifetime.get("total_fish_caught", 0) + 1
    if weight > lifetime.get("biggest_fish_weight", 0):
        lifetime["biggest_fish_weight"] = weight


# ============================================================
# 称号
# ============================================================

def check_fish_title(user: dict) -> Optional[str]:
    """根据用户钓鱼进度返回当前应得称号。无变化返回 None。"""
    fishing = user.get("fishing", {})
    count = fishing.get("total_fishing_count", 0)
    caught = fishing.get("fish_caught", {})
    biggest = fishing.get("biggest_catch", {}).get("weight", 0)

    new_title = None
    if biggest >= 10:
        new_title = "🐋 渔神"
    elif biggest >= 5:
        new_title = "🌊 深海之王"
    elif biggest >= 3:
        new_title = "🦈 巨物挑战者"
    elif biggest >= 1:
        new_title = "💪 大鱼猎手"
    elif count >= 100:
        new_title = "🎣 老渔民"
    elif count >= 10:
        new_title = "🌱 初出茅庐"

    if "黄金锦鲤" in caught:
        new_title = "👑 传奇钓手"
    elif "虹鳟" in caught and (new_title is None or "🐋" not in new_title):
        new_title = new_title or "🏆 虹鳟大师"

    if len(caught) >= 8:
        new_title = "🏆 鱼类图鉴·完"
    elif len(caught) >= 4:
        new_title = new_title or "📖 鱼类图鉴·初"

    current = fishing.get("fish_title", "")
    if new_title and new_title != current:
        fishing["fish_title"] = new_title
        return new_title
    return None


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    _ensure_loaded()
    print(f"已加载 {len(FISHES)} 种鱼, {len(FISHING_SPOTS)} 个水域")
    print("鱼类:", list(FISHES.keys()))
    print("水域:", list(FISHING_SPOTS.keys()))
