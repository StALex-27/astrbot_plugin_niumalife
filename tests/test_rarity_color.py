"""9/6: rarity → color / label utility 测试."""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from modules.item import rarity_hex, RARITY_HEX_COLORS, RARITY_NAMES


def test_all_rarities_have_hex():
    """所有稀有度都有 hex 颜色定义."""
    for r in ["common", "uncommon", "rare", "epic", "legendary", "mythic"]:
        assert r in RARITY_HEX_COLORS, f"缺 {r}"
        # 必须 #RRGGBB 格式
        assert RARITY_HEX_COLORS[r].startswith("#") and len(RARITY_HEX_COLORS[r]) == 7


def test_rarity_hex_returns_color():
    """rarity_hex 返回字符串 (UI 用)."""
    color = rarity_hex("epic")
    assert isinstance(color, str)
    assert color.startswith("#")


def test_rarity_hex_fallback():
    """未知 rarity → common 灰."""
    assert rarity_hex("unknown_xxx") == "#9e9e9e"
    assert rarity_hex("") == "#9e9e9e"
    assert rarity_hex(None) == "#9e9e9e"


def test_rarity_hex_distinct_colors():
    """5 个主稀有度颜色应不同 (UI 视觉区分)."""
    colors = {RARITY_HEX_COLORS[r] for r in ["common", "uncommon", "rare", "epic", "legendary"]}
    assert len(colors) == 5, "颜色应不重复"


def test_items_json_all_have_rarity():
    """items.json 全部 163 个 item 都有 rarity (9/6 补齐 43 个缺失)."""
    import json
    cfg = json.loads((PLUGIN_ROOT / "data/config/items.json").read_text(encoding="utf-8"))
    missing = [k for k, v in cfg.items() if isinstance(v, dict) and "rarity" not in v]
    assert not missing, f"仍缺 rarity: {missing[:10]}"


def test_items_json_rarity_distribution():
    """分布合理 — 每个 tier 大致对应一个 rarity."""
    import json
    cfg = json.loads((PLUGIN_ROOT / "data/config/items.json").read_text(encoding="utf-8"))
    tier_to_rarities = {}
    for k, v in cfg.items():
        if isinstance(v, dict):
            t = int(v.get("tier", 0) or 0)
            r = v.get("rarity", "common")
            tier_to_rarities.setdefault(t, {}).setdefault(r, 0)
            tier_to_rarities[t][r] += 1
    # tier 1 → 主要 common
    if 1 in tier_to_rarities:
        common_in_t1 = tier_to_rarities[1].get("common", 0)
        total_t1 = sum(tier_to_rarities[1].values())
        assert common_in_t1 / total_t1 >= 0.9, f"tier 1 大部分应为 common, 实际 {tier_to_rarities[1]}"
    # tier 5 → 主要 legendary
    if 5 in tier_to_rarities:
        leg_in_t5 = tier_to_rarities[5].get("legendary", 0)
        total_t5 = sum(tier_to_rarities[5].values())
        # 9/6 v9.5: tier 5 鱼竿/线 epic 也合法 (纳米竿 epic, 碳纤巨物线 epic)
        assert leg_in_t5 / total_t5 >= 0.7, f"tier 5 主要应为 legendary, 实际 {tier_to_rarities[5]}"


if __name__ == "__main__":
    tests = [
        test_all_rarities_have_hex,
        test_rarity_hex_returns_color,
        test_rarity_hex_fallback,
        test_rarity_hex_distinct_colors,
        test_items_json_all_have_rarity,
        test_items_json_rarity_distribution,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} tests, {failed} failures")
    sys.exit(0 if failed == 0 else 1)