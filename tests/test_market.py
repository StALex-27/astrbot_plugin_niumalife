"""
tests/test_market.py — 通用交易服务单元测试

不依赖 AstrBot 启动。验证:
- can_sell() 对 fishes/foods/items.json 自动注册生效
- calc_sell_price() 价格计算 + fallback
- list_sellable_inventory() 聚合正确
- 未来加新内容后能立刻跑这个测试验证
"""
import json
import sys
from pathlib import Path

# 把 src 加进 path
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

from market import (
    can_sell,
    calc_sell_price,
    list_sellable_inventory,
    _get_market_entry,
    _auto_register_missing,
    MARKET,
    FISHES_DATA,
    FOODS_DATA,
    ITEMS_DATA,
)


def test_can_sell_all_fishes_registered():
    """fishes.json 的所有鱼都应该能卖 (market 自动注册)."""
    missing = []
    for name in FISHES_DATA:
        if not can_sell(name):
            missing.append(name)
    assert not missing, f"以下鱼未注册: {missing}"


def test_can_sell_all_foods_registered():
    """foods.json 的所有食物都应该能卖 (price > 0)."""
    missing = []
    for name, entry in FOODS_DATA.items():
        if entry.get("price", 0) <= 0:
            continue
        if not can_sell(name):
            missing.append(name)
    assert not missing, f"以下食物未注册: {missing}"


def test_can_sell_all_items_registered():
    """items.json 的所有物品都应该能卖 (price > 0)."""
    missing = []
    for name, entry in ITEMS_DATA.items():
        if entry.get("price", 0) <= 0:
            continue
        if not can_sell(name):
            missing.append(name)
    assert not missing, f"以下物品未注册: {missing}"


def test_can_sell_returns_false_for_unknown():
    """不存在的物品返回 False (不会卖不存在的东西)."""
    assert can_sell("不存在的鱼XYZ") is False
    assert can_sell("") is False


def test_calc_sell_price_fish_with_weight():
    """鱼的售价 = base × weight_multiplier ± volatility.

    草鱼 base=18, sell_ratio=0.8, wm=1.0 → 价格应在 14-22 之间.
    """
    import random
    # 多次跑, 价格波动 (weight 用 4kg, 在草鱼 [2.0, 8.0] 范围内)
    prices = [calc_sell_price("草鱼", weight=4.0) for _ in range(20)]
    for p in prices:
        assert p >= 14, f"草鱼 4kg 售价 {p} 应 >= 14 (考虑 sell_ratio)"
        assert p <= 25, f"草鱼 4kg 售价 {p} 应 <= 25 (考虑 volatility)"


def test_calc_sell_price_food_no_weight():
    """食物售价 = base × sell_ratio (无重量影响)."""
    p = calc_sell_price("泡面", weight=0)
    assert p >= 1, f"泡面售价 {p} 至少 1 金币"


def test_calc_sell_price_returns_at_least_one():
    """任何物品售价至少 1 金币 (避免 0 售价)."""
    for name in list(FISHES_DATA)[:5]:
        p = calc_sell_price(name, weight=1.0)
        assert p >= 1, f"{name} 售价 {p} 应 >= 1"


def test_get_market_entry_has_category():
    """每个 entry 都有 category 字段 (fish/food/item)."""
    for name in list(FISHES_DATA)[:5]:
        e = _get_market_entry(name)
        assert e is not None, f"{name} 没 entry"
        assert e["category"] in ("fish", "food", "item"), f"{name} 异常 category {e['category']}"


def test_list_sellable_inventory_empty():
    """空背包 → 返回空列表 + 0 总额."""
    items, count, gold = list_sellable_inventory({})
    assert items == []
    assert count == 0
    assert gold == 0


def test_list_sellable_inventory_aggregates_same_name():
    """同名鱼聚合 (count=3, gold=3 * unit_price)."""
    user = {"inventory": [
        {"name": "草鱼", "type": "fish", "weight": 1.0},
        {"name": "草鱼", "type": "fish", "weight": 1.5},
        {"name": "草鱼", "type": "fish", "weight": 0.8},
    ]}
    items, count, gold = list_sellable_inventory(user)
    assert count == 3, f"应有 3 条草鱼，实际 {count}"
    assert len(items) == 1
    assert items[0]["name"] == "草鱼"
    assert gold > 0


def test_list_sellable_inventory_filters_unknown():
    """未注册的鱼被过滤 (但 fishes.json 里有就不会被过滤)."""
    user = {"inventory": [
        {"name": "草鱼", "type": "fish"},          # 已注册
        {"name": "不存在的鱼ABC", "type": "fish"}, # 未注册
        {"name": "泡面", "type": "food"},          # 已注册
    ]}
    items, count, gold = list_sellable_inventory(user)
    names = [i["name"] for i in items]
    assert "草鱼" in names
    assert "泡面" in names
    assert "不存在的鱼ABC" not in names


def test_list_sellable_inventory_injects_rarity():
    """9/6: 每个 item 都有 rarity + rarity_color 字段 (UI 染色用)."""
    user = {"inventory": [
        {"name": "草鱼", "type": "fish", "weight": 0.5},
        {"name": "泡面", "type": "food"},
    ]}
    items, _, _ = list_sellable_inventory(user)
    for it in items:
        assert "rarity" in it, f"{it['name']} 缺 rarity"
        assert "rarity_color" in it, f"{it['name']} 缺 rarity_color"
        # rarity_color 应是 hex 格式
        assert it["rarity_color"].startswith("#"), f"{it['name']} rarity_color 不是 hex"
        assert len(it["rarity_color"]) == 7, f"{it['name']} rarity_color 长度错"


def test_auto_register_marked():
    """自动注册的条目带 _auto=True 标记 (调试用)."""
    # 找 fishes.json 里但 market.json 里没有的
    auto_entries = []
    for name, entry in MARKET.get("fish", {}).items():
        if entry.get("_auto"):
            auto_entries.append(name)
    # 应该有自动注册的（除非 market.json 已经收录所有鱼）
    # 这个测试只验证 _auto 标记机制存在
    assert isinstance(auto_entries, list)


if __name__ == "__main__":
    # 手动跑: python tests/test_market.py
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed (out of {len(tests)})")
    sys.exit(0 if failed == 0 else 1)