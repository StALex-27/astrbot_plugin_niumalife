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

# 9/4: 顶层 import skills 模块, 避免函数内 import 触发 "No module named 'modules'" 错误
import sys as _sys
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
from modules.skills import get_skill_level, FISHING_EXP_RATE
from modules.entry_lib import get_entry_value


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
    """获取用户钓鱼技能等级 (兼容老用户无 skill_exp 的情况)。

    9/4: 使用 fishing_30 曲线 (N 平方增长), 等级上限 30
    老用户 exp 不变, 等级按新曲线查 -> 自动降低到应有水平
    """
    # 9/4: get_skill_level/FISHING_EXP_RATE 已在文件顶部 import
    skill_exp = user.get("skill_exp", {})
    exp = skill_exp.get("钓鱼", 0)
    return get_skill_level(exp, FISHING_EXP_RATE)


def get_fishing_skill_progress(user: dict) -> dict:
    """9/8: 钓鱼技能进度 (含 exp/xp_to_next)。

    Returns:
        {
            "level": 1-30,
            "current_exp": int,
            "next_level_exp": int (满级时 = current_exp),
            "is_max": bool,
        }
    """
    skill_exp = user.get("skill_exp", {})
    exp = skill_exp.get("钓鱼", 0)
    from modules.skills import EXP_RATE_TABLE
    table = EXP_RATE_TABLE.get(FISHING_EXP_RATE, {})
    level = get_skill_level(exp, FISHING_EXP_RATE)
    max_lvl = max(table.keys()) if table else 30
    if level >= max_lvl:
        return {"level": level, "current_exp": exp, "next_level_exp": exp, "is_max": True}
    next_level_exp = table.get(level + 1, exp)
    return {
        "level": level,
        "current_exp": exp,
        "next_level_exp": next_level_exp,
        "is_max": False,
    }


# 9/8: size_class → 平均最大重量 (kg)
# 数据来自 fishes.json 各 size_class 实际 weight_range 上限的平均值
# tiny=0.1 / small=0.9 / medium=13 / large=190 / huge=4080 / giant=46000 / titan=440000
# 比 SIZE_CLASS_MAX_WEIGHT (绝对上限) 更合理 — 因为鱼不会都按上限生长
SIZE_CLASS_AVG_WEIGHT = {
    "tiny": 0.1,
    "small": 0.9,
    "medium": 13,
    "large": 190,
    "huge": 4080,
    "giant": 46000,
    "titan": 440000,
}
SIZE_CLASS_ORDER = ["tiny", "small", "medium", "large", "huge", "giant", "titan"]


def calc_break_risk_from_hook(hook_effects: dict, rod_max: float, line_max: float) -> dict:
    """9/8: 按鱼钩覆盖的 size_class 范围评估断竿/断线风险。

    9/8 v2: 超载比例分级
      - ratio ≤ 0       → 无风险 (鱼钩目标完全在装备承重内)
      - 0 < ratio ≤ 10% → 低风险
      - 10% < ratio ≤ 20% → 中风险
      - 20% < ratio ≤ 30% → 高风险
      - ratio > 30%    → 极高风险

    ratio = (hook_max_kg - weak_max) / weak_max

    Args:
        hook_effects: 鱼钩 effects dict
        rod_max: 鱼竿 load_capacity_max (kg)
        line_max: 鱼线 load_capacity_max (kg)

    Returns:
        {
            "level": "无/低/中/高/极高",
            "ratio": float (超载比例 0.10 = 10%),
            "hook_max_kg": float,
            "hook_max_size": str,
            "reason": str,
        }
    """
    target_weights = hook_effects.get("target_size_weights", {}) or {}
    if not target_weights:
        return {"level": "高", "ratio": 0, "hook_max_kg": 0, "hook_max_size": "?", "reason": "鱼钩未配置 size 覆盖"}

    max_size_idx = -1
    for sc in target_weights.keys():
        if sc in SIZE_CLASS_ORDER:
            idx = SIZE_CLASS_ORDER.index(sc)
            if idx > max_size_idx:
                max_size_idx = idx

    if max_size_idx < 0:
        return {"level": "中", "ratio": 0, "hook_max_kg": 0, "hook_max_size": "?", "reason": "鱼钩无已知 size"}

    max_size = SIZE_CLASS_ORDER[max_size_idx]
    hook_max_kg = SIZE_CLASS_AVG_WEIGHT[max_size]

    weak_max = min(rod_max, line_max)
    if weak_max <= 0:
        return {"level": "高", "ratio": 0, "hook_max_kg": hook_max_kg, "hook_max_size": max_size, "reason": "无竿/线"}

    # 超载比例
    ratio = (hook_max_kg - weak_max) / weak_max

    if ratio <= 0:
        level = "无"
    elif ratio <= 0.10:
        level = "低"
    elif ratio <= 0.20:
        level = "中"
    elif ratio <= 0.30:
        level = "高"
    else:
        level = "极高"

    return {
        "level": level,
        "ratio": ratio,
        "hook_max_kg": hook_max_kg,
        "hook_max_size": max_size,
        "reason": f"鱼钩 {max_size} (~{hook_max_kg:.1f}kg) / 弱边 {weak_max}kg → 超载 {ratio*100:+.1f}%",
    }


def _skill_effect(skill_level: int, key: str, default: float = 0.0) -> float:
    """技能等级 → 加成值。从 skills.json 的 effects_per_level 读取。"""
    # 不读 JSON（避免 I/O），按设计文档约定硬编码
    # rare_bonus: 0.01/级；value_bonus: 0.005/级
    per_level = {"rare_bonus": 0.01, "value_bonus": 0.005}
    return skill_level * per_level.get(key, 0) + default


def _fish_in_buckets(fish: dict, target_sizes: list = [], target_diet: list = []) -> bool:
    """9/4: 鱼分桶 (7级尺寸 + 食性) - 判定鱼是否命中鱼钩目标

    7级尺寸 (按 w_max 现算/读字段):
        tiny:    w_max <= 0.3kg
        small:   0.3 < w_max <= 2kg
        medium:  2 < w_max <= 50kg
        large:   50 < w_max <= 500kg
        huge:    500 < w_max <= 10000kg
        giant:   10000 < w_max <= 100000kg
        titan:   w_max > 100000kg

    食性: carnivore / herbivore / omnivore

    兜底: fish 没有 size_class 时用 weight_range 现算
    """
    # 优先读 size_class 字段
    fish_size = fish.get("size_class")
    if not fish_size:
        # 兜底: 现算 (兼容未迁移的鱼)
        w_min, w_max = fish.get("weight_range", [0, 0])
        if w_max <= 0.3:
            fish_size = "tiny"
        elif w_max <= 2.0:
            fish_size = "small"
        elif w_max <= 50.0:
            fish_size = "medium"
        elif w_max <= 500.0:
            fish_size = "large"
        elif w_max <= 10000.0:
            fish_size = "huge"
        elif w_max <= 100000.0:
            fish_size = "giant"
        else:
            fish_size = "titan"
    # 尺寸命中 (target_sizes 非空时检查)
    if target_sizes and fish_size not in set(target_sizes):
        return False
    # 食性匹配 (target_diet 非空时检查)
    if target_diet:
        fish_diet = fish.get("diet", "omnivore")
        if fish_diet not in target_diet:
            return False
    return True


def _fish_size(fish: dict) -> str:
    """9/4: 读鱼 size_class (优先字段, 兜底现算)"""
    sc = fish.get("size_class")
    if sc:
        return sc
    # 兜底: 用 weight_range 现算
    w_max = fish.get("weight_range", [0, 0])[1]
    if w_max <= 0.3:
        return "tiny"
    if w_max <= 2.0:
        return "small"
    if w_max <= 50.0:
        return "medium"
    if w_max <= 500.0:
        return "large"
    if w_max <= 10000.0:
        return "huge"
    if w_max <= 100000.0:
        return "giant"
    return "titan"


# 9/7: 鱼钩 target_size_weights 现在是 size_class 百分比加成 (不再是筛子)
# value 范围 0.0~1.0 (0%=无加成, 0.5=+50%, 1.0=翻倍)
# 不在 weights 里的鱼 size_class 没有加成, 仍然能上钩
#
# 专用钩 vs 万能钩差异化设计 (9/7):
#   - 专用钩 (1-2 个 size key): 高加成 0.4~0.5 (如袖钩 small=0.5)
#   - 中型钩 (2-3 个 size key): 中加成 0.2~0.35
#   - 万能钩 (6+ size key): 低加成 0.05~0.1 (如小矶每个 size=0.1)
# 数据已经在 items.json 体现此差异, _calc_hook_size_boost 直接读权重值
def _calc_hook_size_boost(fish: dict, hook_effects: dict) -> float:
    """9/7: 鱼钩 size_class 加成 (鱼钩本身就是筛子, 命中鱼按权重加成)

    Returns:
        float: 权重乘数 (1.0 无加成 ~ 1.5 半加成)
    """
    size_weights = hook_effects.get("target_size_weights", {}) if hook_effects else {}
    if not size_weights:
        return 1.0
    sc = _fish_size(fish)
    boost = size_weights.get(sc, 0.0)
    return 1.0 + float(boost)


# 9/7: 鱼饵食性匹配加成
# - 素饵 target_diet=[herbivore]: 素食鱼 ×1.5, 杂食鱼 ×1.1 (少量), 肉食鱼 ×0.3 (少量)
# - 肉饵 target_diet=[carnivore]: 肉食鱼 ×1.5, 杂食鱼 ×1.1 (少量), 素食鱼 ×0.3 (少量)
# - 杂饵 target_diet=[omnivore]: 杂食鱼 ×1.5, 素食鱼 ×1.1, 肉食鱼 ×1.1
# - 通用饵 target_diet=[]: 全部 ×1.0 (无加成无惩罚)
DIET_BOOST_MATRIX = {
    # 饵target → 鱼diet → 乘数
    ("herbivore", "herbivore"): 1.5,
    ("herbivore", "omnivore"): 1.1,
    ("herbivore", "carnivore"): 0.3,
    ("carnivore", "carnivore"): 1.5,
    ("carnivore", "omnivore"): 1.1,
    ("carnivore", "herbivore"): 0.3,
    ("omnivore", "omnivore"): 1.5,
    ("omnivore", "herbivore"): 1.1,
    ("omnivore", "carnivore"): 1.1,
}


def _calc_diet_boost(fish: dict, bait_effects: dict) -> float:
    """9/7: 鱼饵食性加成

    Returns:
        float: 权重乘数 (0.3 ~ 1.5)
    """
    if not bait_effects:
        return 1.0
    fish_diet = fish.get("diet", "omnivore")
    target_diet = bait_effects.get("target_diet", [])
    if not target_diet:
        return 1.0
    # 多饵 (鱼饵 + 拟饵 都装备): 取最大加成, 不叠加惩罚
    max_boost = 0.0
    for td in target_diet:
        mult = DIET_BOOST_MATRIX.get((td, fish_diet), 1.0)
        max_boost = max(max_boost, mult)
    return max_boost if max_boost > 0 else 1.0


def _calc_species_boost(fish: dict, bait_effects_list: list) -> float:
    """9/7: 鱼饵对特定鱼种加成 (fish_bonus 字段)

    Returns:
        float: 权重乘数 (1.0 ~ N)
    """
    fish_name = fish.get("name", "")
    mult = 1.0
    for b in (bait_effects_list or []):
        fb = b.get("fish_bonus", {})
        if fish_name in fb:
            mult *= 1.0 + float(fb[fish_name])
    return mult


def _pick_fish_by_size_weights(candidates: list, size_weights: dict, target_diet: list = [],
                              size_filter: bool = True, diet_filter: bool = True) -> Optional[dict]:
    """按鱼钩 size_weights 加权抽样候选鱼.

    Args:
        candidates: 候选鱼
        size_weights: 鱼钩 size_class 权重 (e.g. {"small": 0.4, "medium": 0.3})
        target_diet: 鱼饵 target_diet (e.g. ["herbivore"])
        size_filter: 9/7 是否用 size_weights 当筛子 (默认 True 保留新手安全)
                     False = 仅作 boost, 不筛 (高级装备允许)
        diet_filter: 9/7 是否用 target_diet 当筛子 (默认 True)
                     False = 仅作 DIET_BOOST_MATRIX 加成

    9/7: 双模式支持. 新手钩 (默认): 保留筛子避免大鱼袭击.
          高级装备: 设 size_filter=False, 鱼钩纯 boost 不筛.

    Returns:
        Optional[dict]: 抽到的鱼, 或 None (过滤后无候选 / 池过窄)
    """
    MIN_CANDIDATES_THRESHOLD = 3  # 9/4 防刷: 池过窄 → 轮空
    if not candidates:
        return None

    # 第一步: 过滤
    filtered = []
    for f in candidates:
        sc = _fish_size(f)
        if size_filter and size_weights and sc not in size_weights:
            continue  # size 筛子
        if diet_filter and target_diet:
            fish_diet = f.get("diet", "omnivore")
            if fish_diet not in target_diet:
                continue  # diet 筛子
        filtered.append(f)

    if not filtered:
        return None
    # 9/4 防刷: 池过窄 → 轮空 (避免极端组合下 100% 出稀有鱼)
    if len(filtered) < MIN_CANDIDATES_THRESHOLD:
        return None

    # 第二步: 加权 (size boost + diet boost matrix)
    weighted = []
    for f in filtered:
        sc = _fish_size(f)
        boost = float(size_weights.get(sc, 0.0)) if size_weights else 0.0
        if target_diet:
            fish_diet = f.get("diet", "omnivore")
            diet_mult = max((DIET_BOOST_MATRIX.get((td, fish_diet), 1.0) for td in target_diet), default=1.0)
        else:
            diet_mult = 1.0
        w = (1.0 + boost) * diet_mult
        if w > 0:
            weighted.append((f, w))

    if not weighted:
        return None
    fish = random.choices([f for f, _ in weighted], weights=[w for _, w in weighted], k=1)[0]
    return fish


def _classify_size(fish: dict, weight: float) -> str:
    """根据 weight_range + size_thresholds 给尺寸标签。"""
    labels = fish.get("size_labels", ["普通"])
    thresholds = fish.get("size_thresholds", [])
    for i, t in enumerate(thresholds):
        if weight < t:
            return labels[i] if i < len(labels) else labels[-1]
    return labels[-1] if labels else "普通"


def _weight_fish_choice(candidates: list[dict], extra_rare_bonus: float, fish_bonus: dict = {}) -> Optional[dict]:
    """按 rarity_weight + 加成加权随机抽一条鱼。

    Args:
        candidates: 候选鱼种
        extra_rare_bonus: 稀有度加成 (鱼钩 + 鱼饵 + 技能)
        fish_bonus: 9/3 鱼饵专属加权, dict {鱼名: 加成 0~1}, 命中的鱼额外乘 (1 + 加成 * 20)

    9/4防刷: 候选池 < 3 条 → 轮空 (避免极端过滤组合下 100% 出稀有鱼)
    """
    if not candidates or len(candidates) < 3:
        return None
    weights = []
    for f in candidates:
        w = RARITY_WEIGHT.get(f.get("rarity", "common"), 1.0)
        # 每 +0.01 rare_bonus = 加权翻倍近似
        w *= (1 + extra_rare_bonus * 20)
        # 9/3: 鱼饵鱼种加成 (调整上鱼种类池)
        if fish_bonus and f.get("name") in fish_bonus:
            w *= (1 + fish_bonus[f["name"]] * 20)
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


# ============================================================
# 9/4 权重池系统
# ============================================================
# 设计: 候选池 + 轮空权重 → random.choices 抽 (鱼, 或 "SKIP")
# 1. 鱼基础权重按 rarity 设定 (common=500, ...mythic=1)
# 2. 水域 tier 影响稀有鱼权重 (tier 5 deep_sea 让 legendary/mythic 突出)
# 3. 鱼钩 target_size_weights 命中该鱼 → 权重 × 1.5
# 4. 鱼饵 target_diet 命中 → × 1.3
# 5. 鱼饵 habitat_filter 命中 → × 1.2
# 6. 鱼饵 fish_bonus[鱼名] → × (1 + 加成)
# 7. 鱼饵/钩/技能 rare_bonus → 整体加到所有鱼的 + 加成系数 (0.05 / 0.02 / 0.01)
# 8. 池子 + 轮空权重 → random.choices 抽样
# 9. 选到 "SKIP" → return None (本 tick 不上钩, 等下一 tick)

# 基础权重表 (9/4 用户设计: 大权重比, 更大调节空间)
# 设计原则:
#   - 普通鱼 5000 基准, 让稀有度权重差异巨大
#   - 鱼饵/钩直接加权重点数 (如 +10 放大传奇), 不走百分比
#   - 体重分段升档, 累加所有升档权重作为鱼总权重
#
# 升档概率 (weight 在 weight_range 内位置):
#   中段 80% (10%~90%): 升档 +0
#   边缘 15% (2.5%~10% 或 90%~97.5%): 升档 +1
#   极边缘 4.9% (0.1%~2.5% 或 97.5%~99.9%): 升档 +2
#   极端 0.1% (0~0.1% 或 99.9%~100%): 升档 +3
#
# 升档后稀有度查找表 (9/4: 顶级鱼 legendary +1 档可升 mythic)
RARITY_LADDER = ["common", "uncommon", "rare", "epic", "legendary", "mythic"]

RARITY_BASE_WEIGHT = {
    "common": 4000,
    "uncommon": 1000,   # 4x common
    "rare": 200,        # 5x uncommon
    "epic": 60,         # 3x rare (9/7)
    "legendary": 15,    # 4x epic (9/7)
    "mythic": 5,        # 3x legendary (9/7)
}

# 升档累积概率 (用户原话精确数值)
# 累积: 0.1% (极端) → 5% (极边缘) → 20% (边缘) → 100% (中段)
TIER_BOOST_CUMULATIVE = [
    (0.001, 3),   # 极端 0.1% → +3 档
    (0.05, 2),    # 极边缘 4.9% → +2 档
    (0.20, 1),    # 边缘 15% → +1 档
    (1.01, 0),    # 中段 80% → +0 档
]

# 用户原话: rare 加 50 点权重 + 25% rare 概率
# 普通鱼提升到 rare 的权重 = (n + 50) × (1 + 0.25)
# 整体提升稀有度则对提升的所有升档权重都提升
# 公式: weight(升档 k) = R[目标] × Π(1 + mult) + Σ(add)
#       其中 Π/Σ 只对该目标稀有度的鱼饵加成

# 水域 tier 倍率 (放大稀有鱼权重, 让高 tier 水域产出更稀有)
TIER_MULTIPLIER = {
    1: {"common": 1.0, "uncommon": 1.0, "rare": 1.0, "epic": 1.0, "legendary": 1.0, "mythic": 1.0},
    2: {"common": 1.0, "uncommon": 1.0, "rare": 1.0, "epic": 1.0, "legendary": 1.0, "mythic": 1.0},
    3: {"common": 0.8, "uncommon": 1.0, "rare": 1.3, "epic": 1.5, "legendary": 1.5, "mythic": 1.5},
    4: {"common": 0.6, "uncommon": 0.8, "rare": 1.2, "epic": 1.5, "legendary": 2.0, "mythic": 2.0},
    5: {"common": 0.4, "uncommon": 0.6, "rare": 1.0, "epic": 1.5, "legendary": 2.5, "mythic": 3.0},
}

# 轮空权重 (按 tier: 越难水域轮空权重越大, 钓上鱼越难)
# 9/6 用户重新设计: 降低总体权重, 提升各级水域的中鱼率
# 8 tier SKIP_WEIGHT (匹配 8 水域)
# 池塘 3万 / 小溪 5万 / 水库 8万 / 河流 10万 / 湖泊 13万 / 近海 16万 / 深海 20万 / 深渊 25万
SKIP_WEIGHT = {
    1: 30000,    # 池塘: 中鱼率 ~55%
    2: 50000,    # 小溪: ~45%
    3: 80000,    # 水库: ~35%
    4: 100000,   # 河流: ~28%
    5: 130000,   # 湖泊: ~22%
    6: 160000,   # 近海: ~18%
    7: 200000,   # 深海: ~14%
    8: 250000,   # 深渊: ~10%
}

# 每 tick 中鱼率参考 (含 SKIP_WEIGHT, 池子 12 条普通鱼)
# tier 1: 12*500 / (12*500 + 80000) = 6000/86000 ≈ 7% 每 tick
# tier 5: 30*100 / (30*100 + 150000) = 3000/153000 ≈ 2% 每 tick
# 30 分钟 = 1800 ticks → tier 5 期望中鱼 36 条 (合理)

# 9/4: 池子空或 0 候选时强制扩展 (避免极端渔具完全无鱼)
EXPANSION_FALLBACK_DIETS = ["omnivore", "carnivore", "herbivore"]  # 顺序: 全食 → 肉 → 草
EXPANSION_FALLBACK_SIZES = ["small", "medium", "large", "tiny", "huge", "giant", "titan"]


def _sample_weight_with_boost(w_min: float, w_max: float) -> tuple[float, int]:
    """9/7: 单端高一端升档分布 (体重越高, boost_tier 越大)

    累积概率:
      0.1% 极端  → 顶部 0.05% 体重 → boost +3
      4.9% 极边缘 → 顶部 5% [0.95, 0.9995) → boost +2
      15% 边缘  → 顶部 15% [0.80, 0.95) → boost +1
      80% 中段  → 中段 [0.10, 0.80) → boost +0
    """
    r = random.random()
    if r < 0.001:
        # 极端 0.1% → 顶部 0.05%
        span = w_min + (w_max - w_min) * 0.9995
        return random.uniform(span, w_max), 3
    elif r < 0.05:
        # 极边缘 4.9% → 顶部 5% [0.95, 0.9995)
        span_low = w_min + (w_max - w_min) * 0.95
        span_high = w_min + (w_max - w_min) * 0.9995
        return random.uniform(span_low, span_high), 2
    elif r < 0.20:
        # 边缘 15% → 顶部 15% [0.80, 0.95)
        span_low = w_min + (w_max - w_min) * 0.80
        span_high = w_min + (w_max - w_min) * 0.95
        return random.uniform(span_low, span_high), 1
    else:
        # 中段 80% → [0.10, 0.80)
        span_low = w_min + (w_max - w_min) * 0.10
        span_high = w_min + (w_max - w_min) * 0.80
        return random.uniform(span_low, span_high), 0


def _compute_fish_total_weight(
    fish: dict,
    hook_effects: dict,
    bait_effects_list: list,
    rod_effects: dict,
    line_effects: dict,
    float_effects: dict,
    reel_effects: dict,
    skill_level: int,
    spot_tier: int,
) -> tuple[float, float, float, float]:
    """9/7 方案 C: 计算单条鱼 4 段升档权重 (不再累加)

    用户原话: "整体提升稀有度则对提升的所有升档权重都提升"
    新设计: 4 段独立权重, 装备加成只作用于对应段 (避免被低 base 鱼稀释)

    Args:
        fish: 候选鱼 dict
        所有 effects: 各装备 effects
        spot_tier: 水域 tier (影响 tier_mult)

    Returns:
        (w0, w1, w2, w3) — 4 段升档独立权重
    """
    base_rarity = fish.get("rarity", "common")
    base_rarity_idx = RARITY_LADDER.index(base_rarity) if base_rarity in RARITY_LADDER else 0
    tier_mult = TIER_MULTIPLIER.get(spot_tier, TIER_MULTIPLIER[2])

    # 收集所有鱼饵/钩的加成
    all_bonus_sources = list(bait_effects_list or [])
    if hook_effects:
        all_bonus_sources.append(hook_effects)
    if reel_effects:
        all_bonus_sources.append(reel_effects)
    # 鱼竿/线/浮漂的全局加成 (旧字段 rare_bonus)
    for src in [rod_effects, line_effects, float_effects]:
        if src:
            all_bonus_sources.append(src)

    # 全局乘法加成 (旧 rare_bonus 字段兼容)
    global_mult = 1.0
    for src in all_bonus_sources:
        old_rare = src.get("rare_bonus", 0.0)
        if old_rare:
            global_mult *= 1.0 + old_rare * 5

    # 鱼钩 size_class 加成 (应用到该目标稀有度对应的鱼)
    # 9/5: size 加成 - 直接使用钩尺寸权重值 (10-50%)
    # 9/7: 不再是筛子, _calc_hook_size_boost 统一处理
    size_boost = _calc_hook_size_boost(fish, hook_effects or {})

    # 鱼饵 diet 加成 (9/7 升级: 用 DIET_BOOST_MATRIX, 区分素/肉/杂)
    diet_boost = 1.0
    for b in (bait_effects_list or []):
        diet_boost *= _calc_diet_boost(fish, b)
    hab_boost = 1.0
    for b in (bait_effects_list or []):
        if any(h in b.get("habitat_filter", []) for h in fish.get("habitat", [])):
            hab_boost *= 1.2

    # 鱼饵特定鱼加成 (fish_bonus) - 一次性乘 (9/7 用统一函数)
    fish_bonus_mult = _calc_species_boost(fish, bait_effects_list or [])

    # 9/4: 鱼饵 rarity_bonus 加成 (新字段)
    # 新字段格式: {"rarity_bonus": {"rare": {"add": 50, "multiply": 0.25}}}
    # 9/7 方案 C: 4 段独立 → 只对应该段 rarity 的加成生效

    # 9/5: success_rate 加成 (浮漂 + 鱼轮词条) - 加到单条鱼权重
    success_bonus = 0.0
    for src in all_bonus_sources:
        sr = src.get("success_rate", 0)
        if isinstance(sr, (int, float)) and sr > 0:
            success_bonus += sr

    # 9/5: rarity_pct_bonus 加成 (鱼竿 + 词条) - 仅作用于非 common 鱼
    rarity_pct = 0.0
    for src in all_bonus_sources:
        rp = src.get("rarity_pct_bonus", 0)
        if isinstance(rp, (int, float)) and rp > 0:
            rarity_pct += rp

    # 9/5: habitat_xxx 加成 (鱼竿) - 9/7 已废弃 (水域加成设计取消, 鱼竿按 subcategory 区分用途)
    # 9/7: 不再读取 habitat_xxx, 鱼竿通过 subcategory (溪流/路亚/台钓/筏钓/海投) 区分
    habitat_mult = 1.0

    # 9/7 方案 C: 计算 4 段独立权重
    segment_weights = []
    for k in [0, 1, 2, 3]:
        target_idx = min(base_rarity_idx + k, len(RARITY_LADDER) - 1)
        target_rarity = RARITY_LADDER[target_idx]
        base_w = RARITY_BASE_WEIGHT.get(target_rarity, 100)
        base_w *= tier_mult.get(target_rarity, 1.0)

        # 9/7: rarity_bonus 加成 — 仅作用于对应 rarity 的段
        rarity_mult = 1.0
        rarity_add = 0.0
        for src in all_bonus_sources:
            r_bonus = src.get("rarity_bonus", {})
            if target_rarity in r_bonus:
                rb = r_bonus[target_rarity]
                rarity_mult *= 1.0 + rb.get("multiply", 0)
                rarity_add += rb.get("add", 0)

        # 9/7 公式: weight(k) = base_w × 全局乘区 + 加区 (无累加)
        final_w = (
            base_w
            * size_boost
            * diet_boost
            * hab_boost
            * fish_bonus_mult
            * global_mult
            * rarity_mult
            * habitat_mult
            + rarity_add
            + success_bonus
        )

        # rarity_pct_bonus: 仅非 common (base_rarity_idx > 0) 才生效
        if base_rarity_idx > 0 and rarity_pct > 0:
            final_w *= (1 + rarity_pct / 100.0)

        final_w = max(final_w, 0.01)
        segment_weights.append(final_w)

    return tuple(segment_weights)


def _build_weight_pool(
    candidates: list,
    spot_tier: int,
    hook_effects: dict,
    bait_effects_list: list,
    rod_effects: dict,
    line_effects: dict,
    float_effects: dict,
    reel_effects: dict,
    skill_level: int,
) -> tuple[list, list]:
    """9/7 方案 C: 每条鱼生成 4 个独立条目 (target_rarity 标注)

    同一 base 鱼 → 池中 4 个条目, 每个对应一段升档目标
    抽中哪个条目, 该条目标注的 target_rarity 就是最终稀有度
    装备加成只作用于对应段 (避免低 base 鱼稀释稀有段权重)

    Returns:
        items: list[dict] — 每个 dict 含 fish + target_rarity 字段
        weights: list[float]
    """
    items = []
    weights = []

    for fish in candidates:
        w0, w1, w2, w3 = _compute_fish_total_weight(
            fish, hook_effects, bait_effects_list,
            rod_effects, line_effects, float_effects, reel_effects,
            skill_level, spot_tier
        )
        base_rarity = fish.get("rarity", "common")
        base_rarity_idx = RARITY_LADDER.index(base_rarity) if base_rarity in RARITY_LADDER else 0

        for k, w in enumerate([w0, w1, w2, w3]):
            target_idx = min(base_rarity_idx + k, len(RARITY_LADDER) - 1)
            target_rarity = RARITY_LADDER[target_idx]
            # 9/7: 每个 entry 标注 target_rarity (抽中即用)
            entry = dict(fish)  # shallow copy
            entry["_target_rarity"] = target_rarity
            entry["_boost_tier"] = k
            items.append(entry)
            weights.append(w)

    # 加 SKIP
    skip_w = SKIP_WEIGHT.get(spot_tier, 95000)
    items.append("SKIP")
    weights.append(skip_w)

    return items, weights


def _expand_candidates_if_empty(candidates: list, hook_effects: dict, bait_effects_list: list, all_fish: list) -> list:
    """池子过窄 (< 5 条) 时扩展候选 (按 diet → size 放宽)

    9/7 改造: 不仅扩 diet, 还扩 size (用 EXPANSION_FALLBACK_SIZES 顺序加 size)
    9/4防刷 2.0: 不再用 MIN_CANDIDATES_THRESHOLD 轮空, 而是扩展池子
    """
    if len(candidates) >= 5:
        return candidates

    # 收集当前过滤的 diet 和 size 限制
    bait_diets = set()
    for b in (bait_effects_list or []):
        for d in b.get("target_diet", []):
            bait_diets.add(d)
    hook_size_weights = hook_effects.get("target_size_weights", {})

    # 9/7: 扩展 size 池 - 累计允许的 size_class
    allowed_sizes = set(hook_size_weights.keys()) if hook_size_weights else set()
    added_sizes = set()

    # 扩展策略: 逐步放宽 diet → size → 全池
    for diet in EXPANSION_FALLBACK_DIETS:
        # 收集本次循环新加的鱼
        new_fish = []
        for f in all_fish:
            if diet == "omnivore" or f.get("diet", "omnivore") == diet:
                if hook_size_weights:
                    sc = _fish_size(f)
                    if sc in allowed_sizes or sc in added_sizes:
                        new_fish.append(f)
                else:
                    new_fish.append(f)
        # 去重追加
        existing_ids = {f.get("id") for f in candidates}
        for f in new_fish:
            if f.get("id") not in existing_ids:
                candidates.append(f)
                existing_ids.add(f.get("id"))
        if len(candidates) >= 5:
            return candidates

    # 9/7: 如果还是不够, 放宽 size 限制 (按 EXPANSION_FALLBACK_SIZES 顺序加更多 size)
    if len(candidates) < 5:
        for sc in EXPANSION_FALLBACK_SIZES:
            added_sizes.add(sc)
            existing_ids = {f.get("id") for f in candidates}
            for f in all_fish:
                if _fish_size(f) == sc and f.get("id") not in existing_ids:
                    candidates.append(f)
                    existing_ids.add(f.get("id"))
            if len(candidates) >= 5:
                break

    return candidates


def roll_catch(
    user: dict,
    spot_id: str,
    rod_effects: dict,
    bait_effects_list: list,
    line_effects: dict = {},
    hook_effects: dict = {},
    float_effects: dict = {},
    reel_effects: dict = {},
) -> Optional[dict]:
    """每 tick 调用一次：决定是否中鱼 (9/4 权重池系统)

    Args:
        user: 用户数据 dict
        spot_id: 水域 ID
        rod_effects: 鱼竿 effects dict
        bait_effects_list: 鱼饵 effects dict 列表
        line_effects: 鱼线 effects dict
        hook_effects: 鱼钩 effects dict
        float_effects: 浮漂 effects dict
        reel_effects: 鱼轮 effects dict

    9/4 新设计:
      候选池加权 + 轮空权重 SKIP_WEIGHT → random.choices 抽
      单条鱼概率 = fish_weight / (总鱼权重 + SKIP_WEIGHT)
      极端渔具锁定 1 条鱼 → 该鱼 5/150000 概率 (用户报告的"极低但非零")
    """
    _ensure_loaded()

    spot = get_spot(spot_id)
    if not spot:
        return None

    skill_level = get_fishing_skill_level(user)
    tier = spot.get("tier", 1)

    # 1. 候选鱼池构建
    habitat_tags = spot.get("habitat_tags", [])
    candidates = [f for f in FISHES.values() if any(h in f.get("habitat", []) for h in habitat_tags)]
    if not candidates:
        return None

    # 鱼饵 target_diet + habitat_filter 软过滤 (9/7: 改筛子为 boost, 避免候选池=0)
    # - diet 严筛 → 用 DIET_BOOST_MATRIX 加成 (target_diet 仍作用, 但保留所有鱼种)
    # - habitat 严筛 → 用 habitat_filter 加成 (保留所有鱼, 仅加权)
    # 9/7: 鱼饵不再"过滤"鱼, 只"加权"——避免新玩家用拟饵/特定饵钓不到鱼
    bait_diets = set()
    bait_habitats = set()
    for b in (bait_effects_list or []):
        for d in b.get("target_diet", []):
            bait_diets.add(d)
        for h in b.get("habitat_filter", []):
            bait_habitats.add(h)

    # 鱼钩 size_class 过滤 (池子过窄时扩展, 9/4 防刷 2.0)
    hook_size_weights = hook_effects.get("target_size_weights", {})
    if hook_size_weights:
        # 9/7 改造: 鱼钩 size 仍是筛子 (新手保护), 但候选过窄时扩展
        # 严格过滤
        candidates = [f for f in candidates if _fish_size(f) in hook_size_weights]
        # 池子过窄时扩展 (放宽 diet + size)
        candidates = _expand_candidates_if_empty(candidates, hook_effects, bait_effects_list, list(FISHES.values()))

    # 2. 构建权重池 (含 SKIP)
    items, weights = _build_weight_pool(
        candidates, tier, hook_effects, bait_effects_list,
        rod_effects, line_effects, float_effects, reel_effects,
        skill_level
    )

    # 3. 加权抽样
    picked = random.choices(items, weights=weights, k=1)[0]
    if picked == "SKIP":
        # 9/4: 轮空 = 仍消耗 tick, 但不上鱼
        return None

    fish = picked  # 9/7 方案 C: 已含 _target_rarity 和 _boost_tier 字段
    final_rarity = fish["_target_rarity"]
    boost_tier = fish["_boost_tier"]

    # 4. 抽尺寸 (单端高一端, 抽到的 boost_tier 与体重位置一致)
    w_min, w_max = fish["weight_range"]
    weight, _ = _sample_weight_with_boost(w_min, w_max)
    # 浮漂/鱼竿 size 加成 (在 weight 基础上加一点点)
    rod_size_bonus = rod_effects.get("min_size_bonus", 0.0)
    line_size_bonus = line_effects.get("min_size_bonus", 0.0)
    sensitivity = float_effects.get("sensitivity", 0)
    sensitivity_bonus = sensitivity * 0.03
    total_size_bonus = rod_size_bonus + line_size_bonus + sensitivity_bonus
    weight = weight * (1 + total_size_bonus)
    weight = round(weight, 2)

    # 5. final_rarity 已在 _build_weight_pool 抽签时确定
    # 9/7 方案 C: 抽中的 _target_rarity 就是最终稀有度, 不再二次升档
    # (升档概率已融入池权重: 抽到哪一段的 entry = 出该稀有度)
    base_rarity = fish.get("rarity", "common")
    base_rarity_idx = RARITY_LADDER.index(base_rarity) if base_rarity in RARITY_LADDER else 0
    final_rarity_idx = RARITY_LADDER.index(final_rarity)

    # legendary + 升档 → 100% mythic (9/4 保留规则, 增强体验)
    if base_rarity == "legendary" and boost_tier >= 1:
        final_rarity = "mythic"
        final_rarity_idx = RARITY_LADDER.index("mythic")

    # 用 size_label 字段 (鱼原始 size_thresholds 切分)
    size_label = _classify_size(fish, weight)

    # 6. 断竿/断线机制 - 9/6 重设: 鱼竿和鱼线承载力独立计算, 不累加
    # 鱼竿承载 = 鱼重上限, 超过则按概率断竿 (损坏装备)
    # 鱼线承载 = 鱼重上限, 超过则按概率断线 (失鱼)
    # 通用断线/断竿概率 (用户原话):
    #   超载 0-10% → 30% 概率断
    #   超载 10-20% → 60% 概率断
    #   超载 20-30% → 90% 概率断
    #   超载 >30% → 100% 概率断
    # 默认: 竹竿 2kg (覆盖 tiny/small 部分) + 棉线 1kg (覆盖 tiny 满)
    # 判定顺序 (9/6): 先断线 → 如果线断了则不判定断竿, 避免鱼竿消耗太大
    rod_load_max = rod_effects.get("load_capacity_max", 2)
    line_load_max = line_effects.get("load_capacity_max", 1)

    def _break_prob(overload_pct: float) -> float:
        """超载% → 通用断竿/断线概率"""
        if overload_pct <= 0:
            return 0.0
        if overload_pct <= 0.10:
            return 0.30
        elif overload_pct <= 0.20:
            return 0.60
        elif overload_pct <= 0.30:
            return 0.90
        else:
            return 1.00

    _fname = fish.get("name") or fish.get("id") or fish.get("fish_id") or "未知鱼"

    # 6.1 先判定断线 (鱼重 vs 线载) - 用户 9/6 要求线优先
    if weight > line_load_max:
        line_overload_pct = (weight - line_load_max) / line_load_max
        line_break_chance = _break_prob(line_overload_pct)
        if random.random() < line_break_chance:
            return {
                "_line_break": True,
                "fish_id": _fname,
                "fish_name": _fname,
                "fish": fish,
                "weight": weight,
                "size_label": size_label,
                "estimated_price": 0,
                "overload_pct": round(line_overload_pct * 100, 1),
                "line_load_max": line_load_max,
                "rarity": final_rarity,
                "boost_tier": boost_tier,
            }
        # 线没断 (虽然超载), 继续判定断竿

    # 6.2 断竿检测 (鱼重 vs 竿载, 仅在线没断时)
    if weight > rod_load_max:
        rod_overload_pct = (weight - rod_load_max) / rod_load_max
        rod_break_chance = _break_prob(rod_overload_pct)
        if random.random() < rod_break_chance:
            return {
                "_rod_break": True,
                "fish_id": _fname,
                "fish_name": _fname,
                "fish": fish,
                "weight": weight,
                "size_label": size_label,
                "estimated_price": 0,
                "overload_pct": round(rod_overload_pct * 100, 1),
                "rod_load_max": rod_load_max,
                "rarity": final_rarity,
                "boost_tier": boost_tier,
            }

    # 长度 = 异速生长公式
    _size_idx = size_label_index(fish, size_label)
    length_size_factor = 1.0 + (_size_idx * 0.20)
    _base_len = 25.0 * (max(weight, 0.001) ** (1.0 / 3.0))
    length_cm = round(_base_len * length_size_factor * random.uniform(0.85, 1.15), 1)

    # 7. 估算售价 (用最终稀有度)
    # 9/8: 去掉 size_factor (size_label 加成) 和 skill_value (钓技等级价值加成)
    #      改用重量相对中位数的 ±10% 加成
    rarity_mult_price = RARITY_LADDER.index(final_rarity) - RARITY_LADDER.index(base_rarity) if base_rarity in RARITY_LADDER else 0
    rarity_price_mult = (1.5 ** rarity_mult_price)
    # 9/8: 重量加成 - 基于 weight_range 中位数, ±10%
    wr = fish.get("weight_range", []) or []
    if len(wr) >= 2 and wr[1] > 0:
        median_w = (wr[0] + wr[1]) / 2
        if median_w > 0:
            ratio = (weight - median_w) / median_w
            ratio = max(-1.0, min(1.0, ratio))  # 钳位 [-1, +1]
            weight_bonus = 1.0 + ratio * 0.10  # ±10%
        else:
            weight_bonus = 1.0
    else:
        weight_bonus = 1.0
    # 9/5: price_bonus 加成 (浮漂 + 词条) - 累计所有 source 的 price_bonus 百分比
    price_bonus_pct = 0.0
    for src in [rod_effects, line_effects, float_effects, reel_effects] + (bait_effects_list or []):
        if not src:
            continue
        pv = src.get("price_bonus_pct", 0) or src.get("price_bonus", 0)
        if isinstance(pv, (int, float)) and pv > 0:
            price_bonus_pct += pv
    estimated_price = int(fish["base_price"] * rarity_price_mult * weight_bonus * (1 + price_bonus_pct / 100.0))

    return {
        "fish_id": fish["name"],
        "fish": fish,
        "weight": weight,
        "size_label": size_label,
        "length_cm": length_cm,
        "estimated_price": estimated_price,
        "rarity": final_rarity,
        "base_rarity": base_rarity,
        "boost_tier": boost_tier,
    }


def size_label_index(fish: dict, size_label: str) -> int:
    labels = fish.get("size_labels", [])
    try:
        return labels.index(size_label)
    except ValueError:
        return 0


# 长度系数（用于长度估算）：异速生长公式 length ≈ 25 × weight^(1/3)
_LENGTH_ALLO_K = 25.0
# 每档 size_label 缩放：索引 0=1.0, 1=1.20, 2=1.44, ...
_LENGTH_SIZE_FACTOR_PER_LEVEL = 0.20
_DEFAULT_LABELS = ["普通", "大", "巨", "传说"]


def length_for_size_label(size_label: str, fish: dict = None, weight: float = None) -> float:
    """根据 size_label + weight 计算长度 cm。用于历史数据兜底。

    优先 weight：异速生长 length ≈ 25 × weight^(1/3) × size_factor
    无 weight 时：按 size_label 索引给个保守中位
    """
    import random as _r
    labels = (fish or {}).get("size_labels", _DEFAULT_LABELS)
    try:
        idx = labels.index(size_label)
    except ValueError:
        idx = 0
    size_factor = 1.0 + idx * _LENGTH_SIZE_FACTOR_PER_LEVEL
    if weight is None or weight <= 0:
        # 兜底：取经验中位区间的中点 (普通 22cm / 大 40cm / 巨 65cm / 传说 100cm)
        fallback_midpoints = [22.0, 40.0, 65.0, 100.0]
        return round(fallback_midpoints[min(idx, len(fallback_midpoints) - 1)], 1)
    return round(_LENGTH_ALLO_K * (weight ** (1.0 / 3.0)) * size_factor, 1)


def format_length(length_cm) -> str:
    """把 float cm 渲染成 '42.3cm' / '40cm' 紧凑格式。"""
    if length_cm is None:
        return ""
    if isinstance(length_cm, float) and length_cm.is_integer():
        return f"{int(length_cm)}cm"
    return f"{length_cm:g}cm"


def format_length_compact(length_cm) -> str:
    """9/8: 紧凑模式 — <1cm 显示 mm, 1-99.99cm 保留 2 位, 100-999cm 整数 cm, ≥1m 用 m

    范围:
      < 1cm      → mm 整数 (例: 0.5cm → "5mm")
      1-99.99cm  → cm 2 位小数 (例: 12.3cm → "12.30cm")
      100-999cm  → cm 整数 (例: 580cm → "580cm")
      ≥ 1000cm   → m 2 位小数 (例: 1500cm → "15.00m")
      ≥ 10000cm  → m 整数 (例: 25000cm → "250m")
    """
    if length_cm is None:
        return ""
    try:
        c = float(length_cm)
    except (TypeError, ValueError):
        return str(length_cm)
    if c < 0:
        return f"-{format_length_compact(-c)}"
    if c < 1.0:
        mm = round(c * 10)
        return f"{mm}mm" if mm > 0 else "1mm"  # <0.05cm 显示 1mm 不显示 0
    if c < 100.0:
        return f"{c:.2f}cm"
    if c < 1000.0:
        return f"{int(round(c))}cm"
    if c < 10000.0:
        return f"{c / 100:.2f}m"
    return f"{int(round(c / 100))}m"


def format_weight(weight_kg) -> str:
    """9/8: 把重量渲染成 3-5 字符 + 单位 的紧凑格式

    < 1kg       → grams 整数 (例: 0.42kg → "420g")
    1-99.99kg   → kg + 2 位小数 (例: 12.34kg → "12.34kg")
    100-1999kg  → kg 整数 (例: 580kg → "580kg")
    2000-9999kg → t + 2 位小数 (例: 5500kg → "5.50t")
    ≥ 10000kg   → t 整数 (例: 25000kg → "25t")
    """
    if weight_kg is None:
        return ""
    try:
        w = float(weight_kg)
    except (TypeError, ValueError):
        return str(weight_kg)
    if w < 0:
        return f"-{format_weight(-w)}"
    if w < 1.0:
        grams = round(w * 1000)
        if grams == 0:
            return f"{int(round(w * 1000))}g"
        return f"{grams}g"
    if w < 100.0:
        return f"{w:.2f}kg"
    if w < 2000.0:
        return f"{int(round(w))}kg"
    if w < 10000.0:
        # 9/8: 处理 9999kg 边界 (向下取整到 2 位)
        tons = int(w) // 1000  # 整数吨 (向下取整)
        remainder = w - tons * 1000
        if remainder < 1:
            return f"{tons}.00t" if tons < 10 else f"{tons}t"
        # 2 位小数克
        frac = int(remainder / 10)  # 9999 → tons=9, remainder=999, frac=99 → 9.99t
        return f"{tons}.{frac:02d}t" if tons < 10 else f"{tons}t"
    return f"{int(round(w / 1000))}t"


# ============================================================
# 结算：把鱼加入用户数据
# ============================================================

def apply_catch(user: dict, catch: dict, now_iso: str, reel_effects: dict = {}, all_effects: dict = None) -> None:
    """结算一条鱼：写入 fish_caught / fish_records / biggest_catch / 累计。"""
    fish_name = catch["fish_id"]
    weight = catch["weight"]
    size_label = catch["size_label"]
    length_cm = catch.get("length_cm")
    # 9/8: 解包升档信息, 写入 inventory 让卖价能按升档计算
    final_rarity = catch.get("rarity", catch.get("fish", {}).get("rarity", "common"))  # 9/8
    base_rarity = catch.get("base_rarity", final_rarity)
    boost_tier = catch.get("boost_tier", 0)

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
        "size_label": size_label, "length_cm": length_cm,
        "time": now_iso,
    })
    # 只保留最近 50 条
    if len(fishing["fish_records"]) > 50:
        fishing["fish_records"] = fishing["fish_records"][-50:]

    # 最大单条
    prev_biggest = fishing.get("biggest_catch", {}).get("weight", 0)
    if weight > prev_biggest:
        fishing["biggest_catch"] = {
            "fish": fish_name, "weight": weight,
            "size_label": size_label, "length_cm": length_cm,
        }

    # lifetime_stats
    lifetime = user.setdefault("lifetime_stats", {})
    lifetime["total_fish_caught"] = lifetime.get("total_fish_caught", 0) + 1
    if weight > lifetime.get("biggest_fish_weight", 0):
        lifetime["biggest_fish_weight"] = weight

    # 写入 inventory（每条鱼作为单件，保留完整信息）
    inventory = user.setdefault("inventory", [])
    inventory.append({
        "id": fish_name,
        "name": fish_name,
        "type": "fish",
        "weight": weight,
        "size_label": size_label,
        "length_cm": length_cm,
        "rarity": final_rarity,  # 9/8: 存升档后稀有度, 卖价按升档计算
        "base_rarity": base_rarity,  # 9/8: 基础稀有度 (供显示/调试)
        "boost_tier": boost_tier,  # 9/8: 升档次数
        "time": now_iso,
    })

    # 9/4: 钓鱼经验公式调整 (新 30 级曲线, 前期快后期慢)
    # 旧公式 10 + (tier-1)*5 太膨胀, 普通鱼 10 exp → 30 分钟满级 Lv9
    # 新公式 5 + (tier-1)*2: 普通鱼 5 exp → 30 分钟 Lv8
    fish_def = FISHES.get(fish_name, {})
    rarity = fish_def.get("rarity", "common")
    tier = fish_def.get("tier", 1)
    rarity_bonus = {"common": 0, "uncommon": 5, "rare": 10, "epic": 25, "legendary": 60, "mythic": 150}.get(rarity, 0)
    size_bonus = {"小": 0, "中": 3, "大": 10}.get(size_label, 0)
    exp_gain = 5 + (tier - 1) * 2 + rarity_bonus + size_bonus
    # 鱼自身稀有度倍率
    exp_gain *= {"common": 1.0, "uncommon": 1.1, "rare": 1.2, "epic": 1.5, "legendary": 2.0, "mythic": 3.0}.get(rarity, 1.0)
    # 9/3晚: exp_bonus 加成 (所有装备 source 累加)
    # 9/5: 用 all_effects 参数统一查总 exp_bonus
    if all_effects:
        total_exp_bonus = get_entry_value(all_effects, "exp_bonus")
    else:
        # 兼容旧调用 (只有 reel)
        total_exp_bonus = get_entry_value(reel_effects, "exp_bonus")
    if total_exp_bonus > 0:
        exp_gain *= (1 + total_exp_bonus)
    exp_gain = int(exp_gain)
    # 写入 skill_exp
    skill_exp = user.setdefault("skill_exp", {})
    old_exp = skill_exp.get("钓鱼", 0)
    new_exp = old_exp + exp_gain
    skill_exp["钓鱼"] = new_exp
    old_level = max(0, old_exp // 100)
    new_level = max(0, new_exp // 100)
    # 记录升级 (调用方负责展示)
    user.setdefault("fishing", {})["_last_levelup"] = {
        "from": old_level, "to": new_level,
        "exp_gain": exp_gain, "total_exp": new_exp,
    }


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
