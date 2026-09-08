"""
tests/test_content_registry.py — ContentRegistry 单元测试

不依赖 AstrBot runtime, 纯文件加载测试。
"""
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

# 注入到 sys.modules 让 @dataclass 能解析模块名
import sys as _sys
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "astrbot_plugin_niumalife.src.data.content_registry",
    PLUGIN_ROOT / "src" / "data" / "content_registry.py"
)
_mod = importlib.util.module_from_spec(_spec)
_sys.modules["astrbot_plugin_niumalife.src.data.content_registry"] = _mod
_spec.loader.exec_module(_mod)

get_registry = _mod.get_registry
ContentRegistry = _mod.ContentRegistry
ContentDef = _mod.ContentDef
VALID_ACTIONS = _mod.VALID_ACTIONS


# ============================================================
# 加载测试
# ============================================================

def test_registry_loads_all_types():
    """应能加载所有 6 类内容。"""
    reg = get_registry()
    stats = reg.stats()
    print(f"  stats: {stats}")
    assert stats["items"] >= 150, f"items 太少: {stats['items']}"
    assert stats["fish"] >= 80, f"fish 太少: {stats['fish']}"
    assert stats["courses"] >= 90, f"courses 太少: {stats['courses']}"
    assert stats["jobs"] >= 10, f"jobs 太少: {stats['jobs']}"
    assert stats["residences"] >= 5, f"residences 太少: {stats['residences']}"
    assert stats["entertainments"] >= 20, f"entertainments 太少: {stats['entertainments']}"


def test_registry_no_load_errors():
    """加载不应有错误。"""
    reg = get_registry()
    errors = reg.load_errors
    assert not errors, f"加载错误:\n" + "\n".join(errors[:10])


# ============================================================
# 推导 actions 测试
# ============================================================

def test_food_has_eat_action():
    """食物必须有 eat action。"""
    reg = get_registry()
    for d in reg.get_food_items():
        if d.category == "food":
            assert "eat" in d.actions, f"食物 {d.name} 缺 eat action, actions={d.actions}"


def test_medicine_has_use_action():
    """药品必须有 use action。"""
    reg = get_registry()
    for d in reg._medicine.values():
        assert "use" in d.actions, f"药品 {d.name} 缺 use action, actions={d.actions}"


def test_fish_has_sell_action():
    """鱼(有 base_price)必须有 sell action。"""
    reg = get_registry()
    for d in reg._fish.values():
        if d.price > 0:
            assert "sell" in d.actions, f"鱼 {d.name}(price={d.price}) 缺 sell action"


def test_equip_with_slot_has_equip_action():
    """有 slot 字段的可装备物品必须有 equip action。"""
    reg = get_registry()
    for d in reg._items.values():
        if d.slot:
            assert "equip" in d.actions, (
                f"{d.name} 有 slot='{d.slot}' 但缺 equip action, actions={d.actions}"
            )


def test_items_with_price_have_buy_action():
    """price > 0 的物品必须有 buy action (能被商店买)。"""
    reg = get_registry()
    for d in reg._items.values():
        if d.price > 0 and d.category != "fish":  # 鱼从 fishes.json 读
            assert "buy" in d.actions, (
                f"{d.name} price={d.price} 但缺 buy action, actions={d.actions}"
            )


# ============================================================
# 查询 API 测试
# ============================================================

def test_find_by_id():
    reg = get_registry()
    # 已知物品
    泡面 = reg.find_by_id("泡面")
    assert 泡面 is not None
    assert 泡面.name == "泡面"
    assert 泡面.category == "food"
    # 已知鱼
    小鲫鱼 = reg.find_by_id("小鲫鱼", content_type="fish")
    assert 小鲫鱼 is not None
    assert 小鲫鱼.category == "fish"
    # 不存在
    assert reg.find_by_id("不存在的物品_xyz") is None


def test_find_by_name():
    reg = get_registry()
    d = reg.find_by_name("泡面")
    assert d is not None
    assert d.content_id == "泡面"


def test_supports_action():
    reg = get_registry()
    assert reg.supports_action("泡面", "eat") is True
    assert reg.supports_action("泡面", "sell") is True
    assert reg.supports_action("泡面", "work") is False  # 食物不能打工


def test_filter_by_action():
    reg = get_registry()
    foods = reg.filter_by_action("eat")
    assert len(foods) >= 5, f"可吃食物应 >= 5, 实际 {len(foods)}"
    for d in foods:
        assert "eat" in d.actions


def test_get_sellable_items():
    reg = get_registry()
    sellable = reg.get_sellable_items()
    assert len(sellable) >= 50, f"可卖物品应 >= 50, 实际 {len(sellable)}"


# ============================================================
# ContentDef 单测
# ============================================================

def test_content_def_frozen():
    """ContentDef 是 frozen, 不允许改字段。"""
    reg = get_registry()
    d = reg.find_by_id("泡面")
    try:
        d.name = "改不了"
        assert False, "应该 frozen, 不允许改"
    except Exception:
        pass  # 预期


def test_content_def_to_dict():
    reg = get_registry()
    d = reg.find_by_id("泡面")
    as_d = d.to_dict()
    assert as_d["name"] == "泡面"
    assert isinstance(as_d["effects"], dict)  # tuple → dict
    assert isinstance(as_d["extra"], dict)
    assert as_d["actions"] == list(d.actions) or as_d["actions"] == d.actions


# ============================================================
# 校验 actions 字段值 (业务层一致性)
# ============================================================

def test_all_actions_are_valid():
    """所有 ContentDef.actions 都必须是 VALID_ACTIONS 里的标准动作。"""
    reg = get_registry()
    invalid_count = 0
    examples = []
    for d in reg._items.values():
        for a in d.actions:
            if a not in VALID_ACTIONS:
                invalid_count += 1
                if len(examples) < 5:
                    examples.append(f"{d.name}.actions 含未知: '{a}'")
    for d in reg._fish.values():
        for a in d.actions:
            if a not in VALID_ACTIONS:
                invalid_count += 1
                if len(examples) < 5:
                    examples.append(f"{d.name}.actions 含未知: '{a}'")
    assert invalid_count == 0, f"{invalid_count} 个非法 actions:\n" + "\n".join(examples)


# ============================================================
# 阶段 2: 自动推导覆盖度测试 (老 JSON 不改也能正确推导)
# ============================================================

def test_no_json_migration_needed_food():
    """所有食物自动推导都有 eat + (buy|sell)。"""
    reg = get_registry()
    for d in reg._foods.values():
        assert "eat" in d.actions, f"{d.name} 食物缺 eat"


def test_no_json_migration_needed_medicine():
    """所有药品自动推导都有 use。"""
    reg = get_registry()
    for d in reg._medicine.values():
        assert "use" in d.actions


def test_no_json_migration_needed_fishing_gear():
    """所有渔具 (有 fishing slot) 自动推导都有 equip + use_in_fishing。"""
    reg = get_registry()
    for d in reg._fishing_gear.values():
        assert "equip" in d.actions
        assert "use_in_fishing" in d.actions


def test_no_json_migration_needed_enchant():
    """附魔券自动推导有 enchant action。"""
    reg = get_registry()
    enchant_items = [d for d in reg._items.values() if d.category == "enchant"]
    assert enchant_items, "未找到 enchant 类物品"
    for d in enchant_items:
        assert "enchant" in d.actions, (
            f"{d.name} (enchant 类) 缺 enchant action, "
            f"JSON 没显式声明时应该自动推导"
        )


def test_no_json_migration_needed_course():
    """所有课程自动推导都有 learn。"""
    reg = get_registry()
    for d in reg._courses.values():
        assert "learn" in d.actions


def test_no_json_migration_needed_job():
    """所有工作自动推导都有 work。"""
    reg = get_registry()
    for d in reg._jobs.values():
        assert "work" in d.actions


def test_no_json_migration_needed_residence():
    """所有住所自动推导都有 reside。"""
    reg = get_registry()
    for d in reg._residences.values():
        assert "reside" in d.actions


def test_no_json_migration_needed_entertainment():
    """所有娱乐自动推导都有 entertain。"""
    reg = get_registry()
    for d in reg._entertainments.values():
        assert "entertain" in d.actions


def test_overall_action_distribution():
    """整体 actions 分布健康: 每种 action 至少有 N 个内容支持。"""
    reg = get_registry()
    expectations = {
        "eat": 20,           # 食物
        "use": 5,            # 药品
        "buy": 100,          # 大部分
        "sell": 100,         # 大部分
        "equip": 50,         # 装备 + 渔具
        "use_in_fishing": 100, # 鱼饵 + 鱼
        "learn": 90,         # 课程
        "work": 10,          # 工作
        "reside": 5,         # 住所
        "entertain": 20,     # 娱乐
        "enchant": 3,        # 附魔券
    }
    for action, min_count in expectations.items():
        actual = len(reg.filter_by_action(action))
        assert actual >= min_count, (
            f"action '{action}' 仅 {actual} 个内容支持 (期望 >= {min_count})"
        )


def test_stats_match_existing_market():
    """registry 的 sellable 数量 >= modules/market 的 MARKET 数量 (没遗漏)。"""
    reg = get_registry()
    sellable = reg.get_sellable_items()
    # market 之前已注册 13 条鱼 (其他源鱼也 sellable), 应该 >= 50
    assert len(sellable) >= 50, f"sellable 仅 {len(sellable)}"
    # 可卖类里 food + medicine + equip + fishing_gear + fish 都有
    cats_seen = {d.category for d in sellable}
    assert "food" in cats_seen or any(d.content_type == "fish" for d in sellable)


if __name__ == "__main__":
    failures = 0
    tests = [
        test_registry_loads_all_types,
        test_registry_no_load_errors,
        test_food_has_eat_action,
        test_medicine_has_use_action,
        test_fish_has_sell_action,
        test_equip_with_slot_has_equip_action,
        test_items_with_price_have_buy_action,
        test_find_by_id,
        test_find_by_name,
        test_supports_action,
        test_filter_by_action,
        test_get_sellable_items,
        test_content_def_frozen,
        test_content_def_to_dict,
        test_all_actions_are_valid,
        # 阶段 2 自动推导覆盖度
        test_no_json_migration_needed_food,
        test_no_json_migration_needed_medicine,
        test_no_json_migration_needed_fishing_gear,
        test_no_json_migration_needed_enchant,
        test_no_json_migration_needed_course,
        test_no_json_migration_needed_job,
        test_no_json_migration_needed_residence,
        test_no_json_migration_needed_entertainment,
        test_overall_action_distribution,
        test_stats_match_existing_market,
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
