"""
tests/test_item_detail.py — 物品详情查询单元测试

模拟 AstrBot runtime: plugin 作为包 `data.plugins.astrbot_plugin_niumalife.X` 加载.
所有相对 import 必须按 `from ...modules.item` 解析到完整路径.
"""
import sys
import os
import types
import importlib.util
import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = PLUGIN_ROOT.name  # "astrbot_plugin_niumalife"
FULL_PREFIX = f"data.plugins.{PLUGIN_NAME}"  # 模拟 AstrBot runtime 命名空间


# ============================================================
# 1. 创建完整的 plugin package 树 (模拟 AstrBot runtime)
# ============================================================
def make_pkg(full_name: str, rel_path: str):
    """创建包 module (含 __path__) 放入 sys.modules."""
    pkg = types.ModuleType(full_name)
    pkg.__path__ = [str(PLUGIN_ROOT / rel_path)]
    sys.modules[full_name] = pkg
    return pkg


# Top-level data.plugins
data_pkg = make_pkg("data", "/tmp/__fake_data__")
sys.modules["data"].__path__ = []  # not a real path
# Actually use real path for data/plugins/
DATA_PLUGINS = PLUGIN_ROOT.parent.parent  # data/plugins/
sys.modules["data"].__path__ = [str(DATA_PLUGINS)]

# 模拟 data.plugins
plugins_pkg = make_pkg("data.plugins", DATA_PLUGINS.name)

# Plugin itself
plugin_pkg = make_pkg(FULL_PREFIX, PLUGIN_NAME)

# Plugin's subpackages: modules/, src/, src/commands/, src/data/, src/fishing/
make_pkg(f"{FULL_PREFIX}.modules", f"{PLUGIN_NAME}/modules")
make_pkg(f"{FULL_PREFIX}.src", f"{PLUGIN_NAME}/src")
make_pkg(f"{FULL_PREFIX}.src.commands", f"{PLUGIN_NAME}/src/commands")
make_pkg(f"{FULL_PREFIX}.src.data", f"{PLUGIN_NAME}/src/data")
make_pkg(f"{FULL_PREFIX}.src.fishing", f"{PLUGIN_NAME}/src/fishing")


# ============================================================
# 2. 加载 plugin modules (用 FULL_PREFIX 路径)
# ============================================================
def load(full_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(
        full_name, str(PLUGIN_ROOT / rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# 注意: 用 FULL_PREFIX 路径加载, 这样相对 import 才能解析
# 注意: 先加载 constants/entry_lib (item.py 用 from .constants 等相对 import)
load(f"{FULL_PREFIX}.modules.constants", "modules/constants.py")
load(f"{FULL_PREFIX}.modules.entry_lib", "modules/entry_lib.py")
modules_item = load(f"{FULL_PREFIX}.modules.item", "modules/item.py")
load(f"{FULL_PREFIX}.modules.templates", "modules/templates.py")

user_view = load(f"{FULL_PREFIX}.src.data.user_view", "src/data/user_view.py")


# ============================================================
# 3. Mock fishing_manager (FISHES 静态 fixture)
# ============================================================
fm = types.ModuleType(f"{FULL_PREFIX}.src.fishing.fishing_manager")
fm.__package__ = f"{FULL_PREFIX}.src.fishing"

_FIXTURE_FISHES = {}
for k, v in json.loads((PLUGIN_ROOT / "data" / "config" / "fishes.json").read_text()).items():
    if isinstance(v, dict) and v.get("category") == "fish":
        _FIXTURE_FISHES[k] = v

fm.FISHES = _FIXTURE_FISHES
fm._ensure_loaded = lambda: None  # no-op (don't overwrite fixture)
fm.length_for_size_label = lambda *args, **kwargs: 30.0
fm.format_length = lambda cm: f"{cm}cm"
fm.format_length_compact = lambda cm: f"{cm}cm" if cm and cm >= 1 else (f"{int(round((cm or 0)*10))}mm" if cm else "1mm")  # 9/8: mock
fm.format_weight = lambda w: f"{w:.2f}kg" if w and w >= 1 else (f"{int(round((w or 0)*1000))}g" if w else "0g")  # 9/8: mock
sys.modules[f"{FULL_PREFIX}.src.fishing.fishing_manager"] = fm
print(f'📦 Mock FISHES: {len(_FIXTURE_FISHES)} 条')


# ============================================================
# 4. 加载 item_detail (核心被测对象)
# ============================================================
item_detail = load(f"{FULL_PREFIX}.src.commands.item_detail",
                   "src/commands/item_detail.py")


# ============================================================
# Tests
# ============================================================
def test_resolve_fish_in_inventory():
    user = {
        "inventory": [
            {"id": "草鱼", "name": "草鱼", "type": "fish", "weight": 5.2},
            {"id": "草鱼", "name": "草鱼", "type": "fish", "weight": 7.1},
        ]
    }
    r = item_detail._resolve_item("草鱼", user)
    assert r is not None, "草鱼 should resolve"
    assert r["is_fish"] is True
    assert r["quantity"] == 2
    print('✅ test_resolve_fish_in_inventory')


def test_resolve_item_stacked():
    user = {
        "inventory": [
            {"id": "竹竿", "name": "竹竿", "quantity": 1},
            {"id": "竹竿", "name": "竹竿", "quantity": 2},
        ]
    }
    r = item_detail._resolve_item("竹竿", user)
    assert r is not None
    assert r["is_fish"] is False
    assert r["quantity"] == 3
    print('✅ test_resolve_item_stacked')


def test_resolve_not_found():
    user = {"inventory": [{"id": "草鱼", "name": "草鱼", "type": "fish"}]}
    r = item_detail._resolve_item("不存在xyz", user)
    assert r is None
    print('✅ test_resolve_not_found')


def test_resolve_fish_fallback():
    """玩家没持有此鱼, 但 FISHES 有 — 应该 fallback."""
    user = {"inventory": []}
    r = item_detail._resolve_item("草鱼", user)
    assert r is not None, f"FISHES has 草鱼 but got {r}"
    assert r["is_fish"] is True
    assert r["quantity"] == 0  # 玩家没持有
    print('✅ test_resolve_fish_fallback')


def test_resolve_fish_partial_match():
    """模糊匹配鱼名."""
    user = {"inventory": [{"id": "蓝鲸", "name": "蓝鲸", "type": "fish", "weight": 50000}]}
    r = item_detail._resolve_item("蓝 鲸", user)  # 带空格
    assert r is not None
    assert r["is_fish"] is True
    print('✅ test_resolve_fish_partial_match')


def test_resolve_unknown_no_match():
    user = {"inventory": [{"id": "草鱼", "name": "草鱼", "type": "fish"}]}
    r = item_detail._resolve_item("不存在的鱼xyz123", user)
    assert r is None, f"应返回 None, 但返 {r}"
    print('✅ test_resolve_unknown_no_match')


def test_resolve_filter_tokens_no_match():
    user = {"inventory": [{"id": "草鱼", "name": "草鱼", "type": "fish"}]}
    r = item_detail._resolve_item("鱼", user)
    assert r is None, f"'鱼' 应不匹配, 但返 {r}"
    r = item_detail._resolve_item("大", user)
    assert r is None, f"'大' 应不匹配, 但返 {r}"
    print('✅ test_resolve_filter_tokens_no_match')


def test_build_view_fish():
    user = {"inventory": [], "nickname": "测试玩家"}
    item_result = {
        "source": "fish_def",
        "id": "草鱼",
        "name": "草鱼",
        "quantity": 2,
        "entries": [],
        "is_fish": True,
        "info": {
            "name": "草鱼",
            "rarity": "common",
            "weight_range": [2.0, 8.0],
            "habitat": ["pond", "river"],
            "tier": 3,
            "diet": "herbivore",
            "base_price": 5000,
            "desc": "四大家鱼之一",
        },
        "inventory_entry": None,
    }
    view = item_detail.build_item_detail_view(user, item_result)
    assert view["name"] == "草鱼"
    assert view["quantity"] == 2
    assert view["is_fish"] is True
    assert view["rarity"] == "common"
    assert view["rarity_cn"] == "普通"
    assert len(view["stats_rows"]) >= 3, f"stats_rows: {view['stats_rows']}"
    labels = [r["label"] for r in view["stats_rows"]]
    assert "🌊 水域" in labels
    assert "⚖️ 体重" in labels
    print('✅ test_build_view_fish')


# 9/7: 装备 inventory entry 只有 {id, name}, 没有 type 字段
def test_resolve_equipment_minimal_entry():
    user_with_equip = {
        "inventory": [
            {"id": "竹竿", "name": "竹竿"},  # 装备
        ]
    }
    r = item_detail._resolve_item("竹竿", user_with_equip)
    assert r is not None, f"竹竿装备应可解析, 但返 None"
    assert r["is_fish"] is False
    assert r["info"].get("category") == "equipment", f"info category 应是 equipment, 实际: {r['info']}"
    assert r["info"].get("subcategory") == "fishing_rod", f"info subcategory 应是 fishing_rod"
    print('✅ test_resolve_equipment_minimal_entry')


# 9/7: 装备 entry.name=原始名, 用户输入带稀有度前缀 (如 "优秀竹竿")
def test_resolve_equipment_with_rarity_prefix():
    user = {
        "inventory": [
            {"id": "竹竿", "name": "竹竿", "rarity": "uncommon"},  # 显示名 "优秀竹竿"
            {"id": "玻纤路亚竿", "name": "玻纤路亚竿", "rarity": "epic"},  # "史诗玻纤路亚竿"
        ]
    }
    # 用户输 "优秀竹竿" → 应解析到竹竿 (uncommon)
    r = item_detail._resolve_item("优秀竹竿", user)
    assert r is not None, "应解析成功 (剥离稀有度前缀后匹配)"
    assert r["name"] == "竹竿"
    assert r["info"]["subcategory"] == "fishing_rod"
    print('✅ test_resolve_equipment_with_rarity_prefix')

    # "史诗玻纤路亚竿" → 玻纤路亚竿 (epic)
    r = item_detail._resolve_item("史诗玻纤路亚竿", user)
    assert r is not None
    assert r["name"] == "玻纤路亚竿"
    print('✅ test_resolve_equipment_with_rarity_prefix: 史诗')

    # 不带前缀 "竹竿" 仍能解析
    r = item_detail._resolve_item("竹竿", user)
    assert r is not None
    assert r["name"] == "竹竿"
    print('✅ test_resolve_equipment_with_rarity_prefix: 无前缀')


# 9/7: _strip_rarity_prefix 单元测试
def test_strip_rarity_prefix():
    assert item_detail._strip_rarity_prefix("优秀竹竿") == "竹竿"
    assert item_detail._strip_rarity_prefix("史诗玻纤路亚竿") == "玻纤路亚竿"
    assert item_detail._strip_rarity_prefix("传说龙王竿") == "龙王竿"
    assert item_detail._strip_rarity_prefix("神话星海竿") == "星海竿"
    assert item_detail._strip_rarity_prefix("竹竿") == "竹竿"  # 无前缀
    # "普通" 不剥离
    assert item_detail._strip_rarity_prefix("普通xx") == "普通xx"
    print('✅ test_strip_rarity_prefix')


def test_build_view_equipment():
    user = {"inventory": [], "nickname": "测试玩家"}
    item_result = {
        "source": "inventory",
        "id": "玻纤路亚竿",
        "name": "玻纤路亚竿",
        "quantity": 1,
        "entries": [{"id": "玻纤路亚竿", "rarity": "rare", "effects": {"fishing_bonus_pct": 0.05}}],
        "is_fish": False,
        "info": {
            "name": "玻纤路亚竿",
            "rarity": "rare",
            "price": 500,
            "category": "fishing",
            "subcategory": "fishing_rod",
            "tier": 2,
            "unlock_level": 3,
            "desc": "玻纤材质路亚竿, 适合钓小鱼",
            "effects": {"fishing_bonus_pct": 0.05, "weight_capacity": 5.0},
        },
        "inventory_entry": {"id": "玻纤路亚竿", "rarity": "rare", "effects": {"fishing_bonus_pct": 0.05}},
    }
    view = item_detail.build_item_detail_view(user, item_result)
    assert view["name"] == "玻纤路亚竿"
    assert view["is_fish"] is False
    assert view["rarity"] == "rare"
    assert view["rarity_cn"] == "稀有"
    assert len(view["enchant_entries"]) > 0
    print('✅ test_build_view_equipment')


def test_build_view_equipment_category_equipment():
    """9/7: items.json 用 category='equipment', 应识别为渔具/装备."""
    user = {"inventory": [], "nickname": "测试玩家"}
    item_result = {
        "source": "inventory",
        "id": "竹竿",
        "name": "竹竿",
        "quantity": 1,
        "entries": [],
        "is_fish": False,
        "info": {
            "name": "竹竿",
            "rarity": "common",
            "price": 0,
            "category": "equipment",
            "subcategory": "fishing_rod",
            "tier": 0,
            "slot": "fishing_rod",
            "desc": "初始装备 - 简易竹竿, 适合溪流/水塘钓小鱼",
            "effects": {"weight_capacity": 2.0, "cast_distance": 3.0},
        },
        "inventory_entry": {"id": "竹竿", "name": "竹竿"},
    }
    view = item_detail.build_item_detail_view(user, item_result)
    assert view["name"] == "竹竿"
    assert view["is_fish"] is False
    assert view["rarity"] == "common"
    assert view["rarity_cn"] == "普通"
    # 9/7 修复: category=equipment + subcategory=rod 应该识别为"🎣 渔具"
    assert view["item_type_cn"] == "🎣 渔具", f"应为'🎣 渔具', 实际: '{view['item_type_cn']}'"
    print('✅ test_build_view_equipment_category_equipment')


def test_build_view_enchanted_fish():
    user = {"inventory": [], "nickname": "测试玩家"}
    item_result = {
        "source": "inventory",
        "id": "草鱼",
        "name": "草鱼",
        "quantity": 1,
        "entries": [],
        "is_fish": True,
        "info": {
            "name": "草鱼",
            "rarity": "common",
            "weight_range": [2.0, 8.0],
            "habitat": ["pond", "river"],
            "tier": 3,
            "diet": "herbivore",
            "base_price": 5000,
        },
        "inventory_entry": {"id": "草鱼", "rarity": "rare", "weight": 5.0},
    }
    view = item_detail.build_item_detail_view(user, item_result)
    assert view["rarity"] == "rare", "Should use entry.rarity"
    assert view["rarity_cn"] == "稀有"
    print('✅ test_build_view_enchanted_fish')


def test_fallback_text():
    view = {
        "name": "草鱼",
        "emoji": "🐟",
        "rarity_cn": "普通",
        "quantity": 2,
        "is_fish": True,
        "item_type_cn": "🐟 鱼类",
        "desc": "四大家鱼之一",
        "stats_rows": [{"label": "⚖️ 体重", "value": "2.0 ~ 8.0 kg"}],
        "enchant_entries": [],
        "buy_price": 0,
        "sell_price": 0,
        "show_price": False,
        "show_sell_price": False,
    }
    text = item_detail.get_fallback_text(view)
    assert "草鱼" in text
    assert "⚖️ 体重" in text
    print('✅ test_fallback_text')


def test_norm():
    assert item_detail._norm("草 鱼") == "草鱼"
    assert item_detail._norm("（海）") == "(海)"
    assert item_detail._norm("") == ""
    assert item_detail._norm("鲈鱼(海)") == "鲈鱼(海)"
    print('✅ test_norm')


# ============================================================
# Run all
# ============================================================
test_resolve_fish_in_inventory()
test_resolve_item_stacked()
test_resolve_not_found()
test_resolve_fish_fallback()
test_resolve_fish_partial_match()
test_resolve_unknown_no_match()
test_resolve_filter_tokens_no_match()
test_build_view_fish()
test_build_view_equipment()
test_build_view_enchanted_fish()
test_fallback_text()
test_norm()

test_resolve_equipment_minimal_entry()
test_resolve_equipment_with_rarity_prefix()
test_strip_rarity_prefix()

test_build_view_equipment_category_equipment()

print('\n🎉 所有 16 个测试通过 ✓')