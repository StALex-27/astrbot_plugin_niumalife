"""
tests/test_user_view.py — UserView 访问层单元测试

不依赖 AstrBot, 纯函数测试。验证:
- 所有 getter 在 user 缺字段时返默认值（不抛 KeyError）
- 子模块视图 (fishing/checkin) 老数据兼容
- mutator (add_gold/set_status) 正确改 dict
- 模板视图 (view_for_xxx_card) 字段齐全
"""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

# 直接 import 不经过 src/data/__init__.py (后者会触发 user_repository 导入链)
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "user_view", PLUGIN_ROOT / "src" / "data" / "user_view.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# 一次性把模块内容提到模块级
get_gold = _mod.get_gold
get_status = _mod.get_status
get_nickname = _mod.get_nickname
get_residence = _mod.get_residence
get_attributes = _mod.get_attributes
get_skills = _mod.get_skills
get_inventory = _mod.get_inventory
get_equipped = _mod.get_equipped
get_all_equipped = _mod.get_all_equipped
get_settings = _mod.get_settings
get_action_detail = _mod.get_action_detail
get_fishing = _mod.get_fishing
get_fish_caught = _mod.get_fish_caught
get_biggest_catch = _mod.get_biggest_catch
get_fish_title = _mod.get_fish_title
get_checkin = _mod.get_checkin
get_lifetime_stats = _mod.get_lifetime_stats
get_daily_stats = _mod.get_daily_stats
get_pressures = _mod.get_pressures
get_active_debuffs = _mod.get_active_debuffs
get_stock_holdings = _mod.get_stock_holdings
set_status = _mod.set_status
add_gold = _mod.add_gold
add_fish = _mod.add_fish
add_fish_record = _mod.add_fish_record
set_biggest_catch = _mod.set_biggest_catch
equip_item = _mod.equip_item
unequip_slot = _mod.unequip_slot
view_for_profile_card = _mod.view_for_profile_card
view_for_fish_dex_card = _mod.view_for_fish_dex_card
view_for_fishing_gear_card = _mod.view_for_fishing_gear_card
view_for_backpack_card = _mod.view_for_backpack_card
get_setting = _mod.get_setting
ensure_settings_defaults = _mod.ensure_settings_defaults


# ============================================================
# Fixture: 完整 user dict (模拟 create_user 后的格式)
# ============================================================

def make_full_user():
    """模拟 user_repository.create_user 返回的完整结构。"""
    return {
        "user_id": "test_user_123",
        "nickname": "测试玩家",
        "status": "空闲",
        "gold": 1000,
        "residence": "城中村",
        "attributes": {
            "health": 80, "strength": 70, "mood": 60,
            "satiety": 50, "energy": 90, "sanity": 75,
        },
        "skills": {"钓鱼": {"level": 5, "exp": 100}},
        "inventory": [
            {"id": "草鱼", "name": "草鱼", "weight": 0.42, "type": "fish"},
            {"id": "泡面", "name": "泡面", "quantity": 3, "type": "food"},
        ],
        "equipped_items": {
            "fishing_rod": {"id": "竹竿", "effects": {"fishing_bonus": 0.1}},
            "hook": {"id": "袖钩"},
            # float / bait / line / reel 故意不装
        },
        "stock_holdings": {"NIU001": 100},
        "action_detail": {"type": "工作中", "job_id": "外卖员"},
        "fishing": {
            "fish_caught": {"草鱼": 3, "鲤鱼": 1},
            "fish_records": [{"fish_name": "草鱼", "weight": 0.42}],
            "total_fishing_count": 4,
            "total_fishing_value": 500,
            "biggest_catch": {"fish_name": "草鱼", "weight": 0.42},
            "fish_title": "初级渔夫",
        },
        "checkin": {
            "last_date": "2026-09-05",
            "streak": 7,
            "total_days": 30,
            "total_gold": 3000,
            "lucky_drops": 5,
            "active_buffs": [{"name": "好运", "expires_at": "..."}],
            "last_luck": 75,
        },
        "body_pressure": 10,
        "mind_pressure": 20,
        "active_debuffs": [],
        "lifetime_stats": {
            "total_gold_earned": 5000,
            "peak_gold": 3000,
            "total_fish_caught": 4,
        },
        "daily_stats": {},
        "settings": {
            "sub_group_daily": True,
            "notification_enabled": True,
        },
    }


# ============================================================
# 基础字段访问
# ============================================================

def test_getters_on_full_user():
    """完整 user dict 上所有 getter 返回正确值。"""
    user = make_full_user()
    assert get_gold(user) == 1000
    assert get_status(user) == "空闲"
    assert get_nickname(user) == "测试玩家"
    assert get_residence(user) == "城中村"
    assert get_attributes(user)["health"] == 80
    assert "钓鱼" in get_skills(user)
    assert len(get_inventory(user)) == 2
    assert get_equipped(user, "fishing_rod")["id"] == "竹竿"
    assert get_equipped(user, "float") is None  # 没装
    assert len(get_all_equipped(user)) == 2
    assert get_settings(user)["notification_enabled"] is True
    assert get_action_detail(user)["job_id"] == "外卖员"


def test_getters_on_minimal_user():
    """极小 user dict 上所有 getter 不抛 KeyError, 返默认值。"""
    user = {"user_id": "x"}  # 只有 user_id
    assert get_gold(user) == 0
    assert get_status(user) == "空闲"
    assert get_nickname(user) == "未知"
    assert get_residence(user) == "桥下"
    assert get_attributes(user) == {}
    assert get_skills(user) == {}
    assert get_inventory(user) == []
    assert get_equipped(user, "any_slot") is None
    assert get_all_equipped(user) == {}
    assert get_settings(user) == {}
    assert get_action_detail(user) is None


def test_getters_on_empty_user():
    """空 dict 不抛。"""
    for func in [get_gold, get_status, get_nickname, get_residence,
                get_attributes, get_skills, get_inventory,
                get_all_equipped, get_settings, get_lifetime_stats,
                get_daily_stats, get_stock_holdings, get_active_debuffs]:
        result = func({})
        assert result is not None, f"{func.__name__}({{}}) 返回 None"


# ============================================================
# 子模块视图
# ============================================================

def test_fishing_view_compat():
    """fishing 子模块视图对老数据 (缺字段) 自动补默认。"""
    # 老数据只有部分字段
    user = {"fishing": {"fish_caught": {"草鱼": 1}}}
    view = get_fishing(user)
    assert view["fish_caught"] == {"草鱼": 1}
    assert view["fish_records"] == []
    assert view["total_fishing_count"] == 0
    assert view["total_fishing_value"] == 0
    assert view["biggest_catch"] == {}
    assert view["fish_title"] == ""


def test_fishing_view_empty_user():
    """无 fishing 字段的用户也能正常返。"""
    view = get_fishing({})
    assert view["fish_caught"] == {}
    assert view["fish_records"] == []
    assert view["fish_title"] == ""


def test_checkin_view_compat():
    """checkin 子模块视图对老数据自动补默认。"""
    user = {"checkin": {"streak": 5}}
    view = get_checkin(user)
    assert view["streak"] == 5
    assert view["last_date"] is None
    assert view["total_days"] == 0
    assert view["active_buffs"] == []
    assert view["last_luck"] == 50


def test_pressures():
    """压力视图。"""
    user = {"body_pressure": 30, "mind_pressure": 40}
    p = get_pressures(user)
    assert p == {"body": 30, "mind": 40}

    # 老数据缺字段
    assert get_pressures({}) == {"body": 0, "mind": 0}


# ============================================================
# Mutator
# ============================================================

def test_set_status():
    user = {}
    set_status(user, "工作中")
    assert user["status"] == "工作中"


def test_add_gold_positive_and_negative():
    user = {"gold": 100}
    assert add_gold(user, 50) == 150
    assert add_gold(user, -30) == 120
    # 缺字段
    user2 = {}
    assert add_gold(user2, 10) == 10
    assert user2["gold"] == 10


def test_add_fish_creates_dicts():
    """add_fish 自动创建嵌套 dict (老数据兼容)。"""
    user = {}  # 无 fishing 字段
    add_fish(user, "草鱼", 2)
    assert user["fishing"]["fish_caught"]["草鱼"] == 2
    add_fish(user, "草鱼", 1)
    assert user["fishing"]["fish_caught"]["草鱼"] == 3
    add_fish(user, "鲤鱼", 1)
    assert user["fishing"]["fish_caught"]["鲤鱼"] == 1


def test_add_fish_record():
    user = {}
    add_fish_record(user, {"fish_name": "草鱼", "weight": 0.42})
    add_fish_record(user, {"fish_name": "鲤鱼", "weight": 1.5})
    assert len(user["fishing"]["fish_records"]) == 2


def test_set_biggest_catch():
    """更大重量的鱼覆盖, 否则保留。"""
    user = {"fishing": {"biggest_catch": {"fish_name": "草鱼", "weight": 0.5}}}
    assert set_biggest_catch(user, {"fish_name": "鲤鱼", "weight": 1.0}) is True
    assert user["fishing"]["biggest_catch"]["fish_name"] == "鲤鱼"
    assert set_biggest_catch(user, {"fish_name": "小虾", "weight": 0.1}) is False
    assert user["fishing"]["biggest_catch"]["fish_name"] == "鲤鱼"


def test_equip_and_unequip():
    user = {"equipped_items": {}}
    item = {"id": "竹竿"}
    equip_item(user, "fishing_rod", item)
    assert user["equipped_items"]["fishing_rod"] == item
    removed = unequip_slot(user, "fishing_rod")
    assert removed == item
    assert "fishing_rod" not in user["equipped_items"]
    # 没装的卸 None
    assert unequip_slot(user, "nonexistent") is None


# ============================================================
# 模板视图
# ============================================================

def test_view_for_profile_card_fields():
    """档案卡片视图字段齐全。"""
    user = make_full_user()
    view = view_for_profile_card(user)
    required = {"nickname", "gold", "residence", "status", "streak", "total_days",
                "fish_count", "fish_value", "fish_species", "fish_title",
                "health", "strength", "mood", "satiety", "energy", "sanity"}
    missing = required - set(view.keys())
    assert not missing, f"档案视图缺字段: {missing}"


def test_view_for_fish_dex_card():
    """鱼塘图鉴视图。"""
    user = make_full_user()
    all_fish = {"草鱼": {}, "鲤鱼": {}, "草虾": {}}
    view = view_for_fish_dex_card(user, all_fish)
    assert view["completion_pct"] == 2 / 3 * 100
    assert "草鱼" in view["fish_caught"]
    assert "鲤鱼" in view["fish_caught"]


def test_view_for_fishing_gear_card():
    """渔具视图：装备/未装备槽正确分类。"""
    user = make_full_user()
    view = view_for_fishing_gear_card(user)
    assert "fishing_rod" in view["gear"]
    assert "hook" in view["gear"]
    assert "line" in view["empty_slots"]
    assert "float" in view["empty_slots"]
    assert view["equipped_count"] == 2


def test_view_for_backpack_card():
    user = make_full_user()
    view = view_for_backpack_card(user, filter_label="鱼")
    assert view["total_count"] == 2
    assert len(view["items"]) == 2
    assert view["filter_label"] == "鱼"


# === 9/6: 老玩家 settings 默认值 ===

def test_ensure_settings_defaults_fills_missing():
    """老玩家 (无 settings 字段) 调用后自动补全默认."""
    user = {"user_id": "u1", "nickname": "Alex"}  # 无 settings
    ensure_settings_defaults(user)
    settings = user.get("settings", {})
    assert settings["notification_enabled"] is False  # opt-in 默认
    assert settings["sub_group_daily"] is True
    assert settings["sell_confirm_threshold"] == 1000


def test_ensure_settings_defaults_preserves_existing():
    """老玩家已显式改过的设置不会被默认值覆盖."""
    user = {"settings": {"notification_enabled": True}}  # 老玩家开了通知
    ensure_settings_defaults(user)
    assert user["settings"]["notification_enabled"] is True  # 保留
    assert user["settings"]["sub_group_daily"] is True  # 但补齐其他默认


def test_get_setting_returns_default_for_missing_key():
    """get_setting 自动从 _DEFAULT_SETTINGS 拿 fallback."""
    user = {}  # 完全空
    assert get_setting(user, "notification_enabled") is False
    assert get_setting(user, "sell_confirm_threshold") == 1000
    # 用户自定义 fallback 也工作
    assert get_setting(user, "any_key", default="custom") == "custom"


if __name__ == "__main__":
    failures = 0
    tests = [
        # 基础访问
        test_getters_on_full_user,
        test_getters_on_minimal_user,
        test_getters_on_empty_user,
        # 子模块
        test_fishing_view_compat,
        test_fishing_view_empty_user,
        test_checkin_view_compat,
        test_pressures,
        # Mutator
        test_set_status,
        test_add_gold_positive_and_negative,
        test_add_fish_creates_dicts,
        test_add_fish_record,
        test_set_biggest_catch,
        test_equip_and_unequip,
        # 模板视图
        test_view_for_profile_card_fields,
        test_view_for_fish_dex_card,
        test_view_for_fishing_gear_card,
        test_view_for_backpack_card,
        # 9/6: 老玩家 settings 默认值
        test_ensure_settings_defaults_fills_missing,
        test_ensure_settings_defaults_preserves_existing,
        test_get_setting_returns_default_for_missing_key,
    ]
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            print(f"FAIL  {t.__name__}\n      {e}")
            failures += 1
        except Exception as e:
            print(f"ERROR {t.__name__}\n      {type(e).__name__}: {e}")
            failures += 1
    print(f"\n{len(tests)} tests, {failures} failures")
    sys.exit(0 if failures == 0 else 1)
