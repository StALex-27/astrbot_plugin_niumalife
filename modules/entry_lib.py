"""9/4晚: 渔具词条系统 - 公共词条库 + resolve_effects

设计:
- 渔具公共词条库: 所有渔具共享 (消耗性鱼饵除外)
- 词条数值: (base + flat_词条1 + flat_词条2 + ...) * (1 + pct_词条1% + pct_词条2% + ...)
- rarity_mult 范围随机 (mythic 最高 2.0-2.5), 持久化到 inventory entry
- 同词条合并累加
- max_hook_slots 不受 rarity_mult 影响
"""
import random
from typing import Optional

# 9/4晚: rarity 基础数值倍率范围 (避免循环引用, 复制 item.py 中的字典)
RARITY_BONUS_COUNT = {
    "common":    0,
    "uncommon":  1,
    "rare":      2,
    "epic":      3,
    "legendary": 4,
    "mythic":    5,
}

RARITY_MULT_RANGE = {
    "common":    (1.00, 1.00),
    "uncommon":  (1.05, 1.15),
    "rare":      (1.15, 1.35),
    "epic":      (1.35, 1.65),
    "legendary": (1.65, 2.00),
    "mythic":    (2.00, 2.50),
}


def get_entry_value(effects: dict, key: str) -> float:
    """获取词条最终值 - 同时支持 flat 和 *_pct 字段

    返回: flat 值 + pct 值 / 100.0 (pct 转 decimal)
    """
    flat = effects.get(key, 0.0)
    pct = effects.get(f"{key}_pct", 0.0)
    if not isinstance(flat, (int, float)):
        flat = 0.0
    if not isinstance(pct, (int, float)):
        pct = 0.0
    return flat + pct / 100.0

RARITY_RANK = {
    "common": 0, "uncommon": 1, "rare": 2,
    "epic": 3, "legendary": 4, "mythic": 5,
}

# 9/4晚: 公共词条库 - 数值范围 (在 common 等级)
COMMON_ENTRY_LIB = {
    # --- flat 类型: 加入权重 ---
    "success_rate":          {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    # 水域加成
    "habitat_pond":          {"min": 8, "max": 15, "type": "flat", "scale": "flat"},
    "habitat_river":         {"min": 8, "max": 15, "type": "flat", "scale": "flat"},
    "habitat_reservoir":     {"min": 8, "max": 15, "type": "flat", "scale": "flat"},
    "habitat_coast":         {"min": 8, "max": 15, "type": "flat", "scale": "flat"},
    "habitat_deep_sea":      {"min": 8, "max": 15, "type": "flat", "scale": "flat"},
    # 稀有度加成 (固定值)
    "rarity_common_bonus":   {"min": 3, "max": 8, "type": "flat", "scale": "flat"},   # 非 common 鱼权重+ N
    "rarity_legendary_bonus": {"min": 1, "max": 3, "type": "flat", "scale": "flat"},   # legendary 鱼权重+ N
    "rarity_mythic_bonus":   {"min": 1, "max": 2, "type": "flat", "scale": "flat"},   # mythic 鱼权重+ N
    # 尺寸加成
    "size_titan_bonus":      {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_giant_bonus":      {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_huge_bonus":       {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_large_bonus":      {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_medium_bonus":     {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_small_bonus":      {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    "size_tiny_bonus":       {"min": 5, "max": 10, "type": "flat", "scale": "flat"},
    # 食性加成
    "diet_carnivore_bonus":  {"min": 5, "max": 15, "type": "flat", "scale": "flat"},
    "diet_herbivore_bonus":  {"min": 5, "max": 15, "type": "flat", "scale": "flat"},
    "diet_omnivore_bonus":   {"min": 5, "max": 15, "type": "flat", "scale": "flat"},
    # 体力消耗减免 (固定值, 上限 6, 最低消耗 1)
    "stamina_reduce":        {"min": 1, "max": 2, "type": "flat", "scale": "flat"},
    # 鱼饵不消耗概率 (%)
    "bait_no_consume":       {"min": 5, "max": 15, "type": "pct", "scale": "pct"},

    # --- pct 类型: 百分比加成 ---
    "rarity_pct_bonus":      {"min": 5, "max": 15, "type": "pct", "scale": "pct"},   # 非 common 鱼权重 ×(1+N%)
    "exp_bonus":             {"min": 10, "max": 20, "type": "pct", "scale": "pct"},  # 钓鱼经验 ×(1+N%)
    "price_bonus":           {"min": 5, "max": 15, "type": "pct", "scale": "pct"},   # 鱼价值 ×(1+N%)
    "load_capacity":         {"min": 5, "max": 15, "type": "pct", "scale": "pct"},   # 承载力 ×(1+N%)
}

# 9/4晚: 特殊词条 (限制 slot/rarity)
SPECIAL_ENTRY = {
    # max_hook_slots 不受 rarity_mult 影响, 只在神话级鱼竿出现
    "max_hook_slots": {"min": 1, "max": 1, "type": "flat", "only": "fishing_rod", "min_rarity": "mythic", "no_mult": True},
    # 9/5: 鱼钩 bait_slots+1 词条 - 仅传说/神话鱼钩 (稀有度5-6级) 出现
    "bait_slots": {"min": 1, "max": 1, "type": "flat", "only": "hook", "min_rarity": "legendary", "no_mult": True},
}


def _entry_allowed(entry_id: str, slot: str, rarity: str) -> bool:
    """检查词条是否对当前 slot/rarity 可用"""
    if entry_id in SPECIAL_ENTRY:
        spec = SPECIAL_ENTRY[entry_id]
        if spec.get("only") and spec["only"] != slot:
            return False
        if spec.get("min_rarity"):
            if RARITY_RANK.get(rarity, 0) < RARITY_RANK.get(spec["min_rarity"], 0):
                return False
    return True


def resolve_effects(
    item: dict,
    rarity: Optional[str] = None,
    rarity_mult: Optional[float] = None,
    rng: random.Random = None,  # type: ignore
) -> dict:
    """根据 rarity 解析装备实际生效的词条

    Args:
        item: 物品定义 (来自 items.json)
        rarity: 稀有度 (从 inventory entry 读, 缺省 common)
        rarity_mult: 持久化的倍率 (从 inventory entry 读, 缺省随机抽)
        rng: 随机数生成器 (测试用)

    Returns:
        解析后的 effects 字典 (含基础属性 + 词条)
    """
    _rng = rng if rng is not None else random
    rarity = rarity or "common"

    base = item.get("base_effects", {})
    pool = list(item.get("bonus_pool", []))
    bonus_count = RARITY_BONUS_COUNT.get(rarity, 0)
    mult_range = RARITY_MULT_RANGE.get(rarity, (1.0, 1.0))

    # 1. 抽取 rarity_mult (持久化场景下从 entry 读)
    if rarity_mult is None:
        rarity_mult = round(_rng.uniform(*mult_range), 3)
    else:
        rarity_mult = float(rarity_mult)

    slot = item.get("slot", "")

    # 2. 基础词条处理
    final = {}
    flat_sums = {}    # flat 累加
    pct_sums = {}     # pct 累加

    for k, v in base.items():
        if not isinstance(v, (int, float)):
            final[k] = v
            continue

        # max_hook_slots 不受 rarity_mult 影响
        if k == "max_hook_slots":
            final[k] = int(v)
            continue

        # load_capacity_max 基础属性按 rarity_mult 缩放
        if k == "load_capacity_max":
            final[k] = round(v * rarity_mult, 2)
            continue

        # 其他视为词条数值 (base 中的词条基础值)
        # 9/4晚: 跳过非词条字段 (装备专属属性, 在 calc 时单独处理)
        if k in {"habitat_filter", "target_diet", "target_size_weights", "duration_reduce"}:
            final[k] = v if k == "duration_reduce" else v  # 原样保留
            continue
        entry = COMMON_ENTRY_LIB.get(k, {"type": "flat"})
        scaled = v * rarity_mult
        if entry["type"] == "pct":
            pct_sums[k] = pct_sums.get(k, 0) + scaled
        else:
            flat_sums[k] = flat_sums.get(k, 0) + scaled

    # 3. 抽取 bonus 词条
    if bonus_count > 0 and pool:
        # 过滤受限词条
        allowed_pool = [e for e in pool if _entry_allowed(e, slot, rarity)]
        if allowed_pool:
            chosen_count = min(bonus_count, len(allowed_pool))
            chosen = _rng.sample(allowed_pool, chosen_count)
            for entry_id in chosen:
                if entry_id in SPECIAL_ENTRY:
                    entry = SPECIAL_ENTRY[entry_id]
                else:
                    entry = COMMON_ENTRY_LIB.get(entry_id)
                if not entry:
                    continue
                val = _rng.randint(entry["min"], entry["max"])
                # 特殊词条 (no_mult) 不乘 rarity_mult
                if not entry.get("no_mult"):
                    val = val * rarity_mult
                if entry["type"] == "pct":
                    pct_sums[entry_id] = pct_sums.get(entry_id, 0) + val
                else:
                    flat_sums[entry_id] = flat_sums.get(entry_id, 0) + val

    # 4. 应用公式 (base + flat) * (1 + pct/100)
    # 9/4晚公式设计:
    # - flat 词条: 直接累加 (base 缺失时, flat 单独生效) - 存 final[k]
    # - pct 词条: 单独累加成百分比 (1+10%+15%+...) - 存 final[k+"_pct"]
    # - 计算端: 鱼的售价 = base_price * (1 + price_bonus_pct/100)
    all_keys = set(list(flat_sums.keys()) + list(pct_sums.keys()))
    for k in all_keys:
        flat = flat_sums.get(k, 0)
        pct = pct_sums.get(k, 0)
        # flat: 只在有值时写入 final
        if flat != 0:
            final[k] = round(flat, 2)
        # pct: 单独存为 *_pct 后缀字段
        if pct != 0:
            final[f"{k}_pct"] = round(pct, 2)

    return final


def make_inventory_entry(item_id: str, rarity: str = "common", rng: random.Random = None) -> dict:  # type: ignore
    """生成一个 inventory entry (含 rarity + rarity_mult 持久化)"""
    _rng = rng if rng is not None else random
    mult_range = RARITY_MULT_RANGE.get(rarity, (1.0, 1.0))
    rarity_mult = round(_rng.uniform(*mult_range), 3)
    return {
        "id": item_id,
        "rarity": rarity,
        "rarity_mult": rarity_mult,
    }


def get_item_rarity(entry: dict) -> str:
    """从 inventory entry 读 rarity"""
    return entry.get("rarity", "common")


def get_entry_rarity_mult(entry: dict) -> float:
    """从 inventory entry 读持久化的 rarity_mult"""
    return float(entry.get("rarity_mult", 1.0))
