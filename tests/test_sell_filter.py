"""9/6: sell.py 按稀有度过滤测试 — 验证 ≤max_rarity 语义."""
import sys, os, importlib.util
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# 9/6: 直接 import _helpers.py (避免 src.commands 包拉 astrbot)
sys.path.insert(0, str(PLUGIN_ROOT / "src" / "commands"))
# 还需要 _helpers.py 的内部依赖: market.py 路径
# _helpers 不依赖任何其他内部模块, 直接 import 即可

parse_filter_tokens, apply_item_filter, format_filter_label = (
    __import__("_helpers").parse_filter_tokens,
    __import__("_helpers").apply_item_filter,
    __import__("_helpers").format_filter_label,
)
_h = __import__("_helpers")


# === 假 FISHES 定义 (rarity) ===
_FISHES = {
    "草鱼": {"name": "草鱼", "rarity": "common", "size_labels": ["小", "大", "巨"]},
    "鲫鱼": {"name": "鲫鱼", "rarity": "uncommon", "size_labels": ["小", "大", "巨"]},
    "鳜鱼": {"name": "鳜鱼", "rarity": "rare", "size_labels": ["小", "大", "巨"]},
    "龙鱼": {"name": "龙鱼", "rarity": "epic", "size_labels": ["小", "大", "巨"]},
    "金鳟": {"name": "金鳟", "rarity": "legendary", "size_labels": ["小", "大", "巨"]},
}


def _inv_with_fish_defs(items):
    """把 _fish_def 注入到每个 fish 项 (模拟 _item_rarity 优先用 item._fish_def 路径)."""
    out = []
    for it in items:
        x = dict(it)
        if x.get("type") == "fish":
            name = x.get("name")
            if name in _FISHES:
                x["_fish_def"] = _FISHES[name]
        out.append(x)
    return out


def test_parse_max_rarity_field():
    """parse_filter_tokens 输出 max_rarity (不是 min_rarity)."""
    filt = parse_filter_tokens(["鱼", "稀有"])
    assert filt["category"] == "fish", filt
    assert filt["max_rarity"] == 2, filt  # 稀有 = 索引 2
    assert "min_rarity" not in filt, "应已重命名为 max_rarity"


def test_apply_filter_le_rare():
    """/卖 鱼 稀有 → 卖 ≤稀有的鱼 (common + uncommon + rare)."""
    items = _inv_with_fish_defs([
        {"type": "fish", "name": "草鱼"},  # common
        {"type": "fish", "name": "鲫鱼"},  # uncommon
        {"type": "fish", "name": "鳜鱼"},  # rare
        {"type": "fish", "name": "龙鱼"},  # epic (不应)
        {"type": "fish", "name": "金鳟"},  # legendary (不应)
    ])
    filt = parse_filter_tokens(["鱼", "稀有"])
    out = apply_item_filter(items, filt, _FISHES)
    names = {it["name"] for it in out}
    assert names == {"草鱼", "鲫鱼", "鳜鱼"}, names
    # 显式断言龙鱼/金鳟不在
    assert "龙鱼" not in names
    assert "金鳟" not in names


def test_apply_filter_le_common():
    """/卖 鱼 常见 → 只卖 common (≤0)."""
    items = _inv_with_fish_defs([
        {"type": "fish", "name": "草鱼"},
        {"type": "fish", "name": "鲫鱼"},
        {"type": "fish", "name": "鳜鱼"},
    ])
    filt = parse_filter_tokens(["鱼", "常见"])
    out = apply_item_filter(items, filt, _FISHES)
    names = [it["name"] for it in out]
    assert names == ["草鱼"], names


def test_apply_filter_le_legendary():
    """/卖 鱼 传奇 → 全卖 (≤4 全部)."""
    items = _inv_with_fish_defs([
        {"type": "fish", "name": "草鱼"},
        {"type": "fish", "name": "金鳟"},
    ])
    filt = parse_filter_tokens(["鱼", "传奇"])
    out = apply_item_filter(items, filt, _FISHES)
    assert len(out) == 2


def test_apply_filter_no_rarity():
    """无稀有度 token → 不过滤."""
    items = _inv_with_fish_defs([
        {"type": "fish", "name": "草鱼"},
        {"type": "fish", "name": "金鳟"},
    ])
    filt = parse_filter_tokens(["鱼"])
    out = apply_item_filter(items, filt, _FISHES)
    assert len(out) == 2


def test_format_label_shows_le():
    """format_filter_label 显示 ≤稀有 形式."""
    filt = parse_filter_tokens(["鱼", "稀有"])
    label = format_filter_label(filt)
    assert "≤稀有" in label, label
    assert "稀有起" not in label, "不应再用 '起' 措辞"


def test_rare_token_alias_english():
    """英文 'rare' 也能识别."""
    filt = parse_filter_tokens(["鱼", "rare"])
    assert filt["max_rarity"] == 2, filt


def test_rarity_token_with_keep():
    """/卖 鱼 稀有 留大 1 — 复合用例."""
    items = _inv_with_fish_defs([
        {"type": "fish", "name": "草鱼", "weight": 0.3},
        {"type": "fish", "name": "鲫鱼", "weight": 0.5},
        {"type": "fish", "name": "鳜鱼", "weight": 1.0},
        {"type": "fish", "name": "龙鱼", "weight": 2.0},  # epic, 不应入选
    ])
    filt = parse_filter_tokens(["鱼", "稀有"])
    out = apply_item_filter(items, filt, _FISHES)
    # 应剩草鱼/鲫鱼/鳜鱼 (无龙鱼)
    names = {it["name"] for it in out}
    assert names == {"草鱼", "鲫鱼", "鳜鱼"}, names


if __name__ == "__main__":
    tests = [
        test_parse_max_rarity_field,
        test_apply_filter_le_rare,
        test_apply_filter_le_common,
        test_apply_filter_le_legendary,
        test_apply_filter_no_rarity,
        test_format_label_shows_le,
        test_rare_token_alias_english,
        test_rarity_token_with_keep,
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