"""9/6 v9.5: 鱼竿数据测试 (业务数据在 items.json)."""
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

# 直接 import 模块 (避免 sys.path 干扰)
from modules.gear_builder import build_rod_items, resolve_item_id, ITEM_ALIASES
from modules.constants import ITEMS


def _reload_module():
    """9/6 v9.5: 重载模块以获取最新 ITEM_ALIASES (因为它是模块级 dict).

    build_rod_items() 会修改模块级 ITEM_ALIASES, 但 from-import
    拿到的是绑定时的初始空 dict 引用 (对可变 dict 来说是引用而非拷贝).
    """
    import importlib
    import modules.gear_builder
    importlib.reload(modules.gear_builder)
    return modules.gear_builder


def _rods():
    """从 ITEMS 提取所有鱼竿 (slot=fishing_rod)."""
    return {k: v for k, v in ITEMS.items() if isinstance(v, dict) and v.get('slot') == 'fishing_rod'}


def _lines():
    """从 ITEMS 提取所有鱼线 (type=鱼线)."""
    return {k: v for k, v in ITEMS.items() if isinstance(v, dict) and v.get('type') == '鱼线'}


def test_rod_count():
    """1 初始 + 25 主线 + 3 顶级 = 29 件鱼竿."""
    templates = json.loads(
        (PLUGIN_ROOT / "data/config/gear_templates.json").read_text(encoding="utf-8")
    )
    items = build_rod_items(templates)
    # v9.5: build_rod_items 返回空 dict
    assert len(items) == 0, f"v9.5: 期望 0 件, 实际 {len(items)}"

    # 重新加载模块获取最新 ITEM_ALIASES
    _gb = _reload_module()
    _gb.build_rod_items(templates)  # 触发 alias 重新加载
    assert len(_gb.ITEM_ALIASES) > 0, "别名表应该已加载"
    print(f"✓ 别名表 {len(_gb.ITEM_ALIASES)} 项已加载")

    # 实际鱼竿数据
    rods = _rods()
    print(f"✓ 鱼竿总数 {len(rods)} 件 (期望 29 = 1 初始 + 25 主线 + 3 顶级)")
    assert len(rods) == 29, f"期望 29 件, 实际 {len(rods)}"

    # 顶级 3 件
    top_ids = {'龙王竿', '龙神竿', '星海竿'}
    top = {k: v for k, v in rods.items() if k in top_ids}
    assert len(top) == 3, f"期望 3 件顶级, 实际 {len(top)}"
    print(f"✓ 顶级龙王竿 {len(top)} 件")


def test_rod_initial_bamboo():
    """竹竿是初始装备, 承载 2kg."""
    rods = _rods()
    bamboo = rods.get('竹竿')
    assert bamboo is not None, "缺少 '竹竿'"
    assert bamboo['tier'] == 0, f"竹竿 tier 应=0, 实际 {bamboo['tier']}"
    assert bamboo['base_effects']['load_capacity_max'] == 2.0, \
        f"竹竿 load 应=2kg, 实际 {bamboo['base_effects']['load_capacity_max']}"
    print("✓ 竹竿 tier=0, load=2kg")


def test_rod_naming():
    """新鱼竿命名: 材质(玻纤/碳纤/...)+ 型号(溪流/路亚/台钓/筏钓/海投)竿."""
    rods = _rods()
    expected_materials = ['玻纤', '碳纤', '高碳', '钛合金', '纳米']
    expected_models = ['溪流', '路亚', '台钓', '筏钓', '海投']
    # 5 材质 × 5 型号 = 25 主线
    for m in expected_materials:
        for w in expected_models:
            name = f"{m}{w}竿"
            assert name in rods, f"缺少 '{name}'"
    print(f"✓ 25 件主线命名正确 ({len(expected_materials)} 材质 × {len(expected_models)} 型号)")

    # 顶级
    for tname in ['龙王竿', '龙神竿', '星海竿']:
        assert tname in rods, f"缺少顶级 '{tname}'"
    print("✓ 3 件顶级命名正确")


def test_load_progression():
    """load_capacity_max 按 x² 平滑曲线从 5kg 升到 50000kg."""
    rods = _rods()
    # 25 件主线 (除竹竿) 承载应单调递增
    main_rods = []
    for m in ['玻纤', '碳纤', '高碳', '钛合金', '纳米']:
        for w in ['溪流', '路亚', '台钓', '筏钓', '海投']:
            name = f"{m}{w}竿"
            cap = rods[name]['base_effects']['load_capacity_max']
            main_rods.append((name, cap))
    caps = [c for _, c in main_rods]
    assert caps == sorted(caps), f"承载应单调递增: 实际 {caps}"
    assert min(caps) >= 5, f"最低承载应≥5kg, 实际 {min(caps)}"
    assert max(caps) <= 50000, f"最高承载应≤50000kg, 实际 {max(caps)}"
    print(f"✓ 承载单调递增: {min(caps)}kg -> {max(caps)}kg")

    # 顶级
    top_caps = [rods[n]['base_effects']['load_capacity_max'] for n in ['龙王竿', '龙神竿', '星海竿']]
    assert top_caps == sorted(top_caps), f"顶级承载应递增: {top_caps}"
    assert top_caps[-1] >= 1000000, f"星海竿承载应≥1,000,000kg"
    print(f"✓ 顶级承载递增: {top_caps}")


def test_unlock_levels_spread():
    """解锁等级覆盖 0-30 (竹竿=0 作为初始装备)."""
    rods = _rods()
    all_unlocks = [r['unlock_requirements']['min_fishing_level'] for r in rods.values()]
    # 竹竿 = 0 (初始装备, 无需解锁)
    assert min(all_unlocks) == 0, f"最低解锁应=0 (竹竿), 实际 {min(all_unlocks)}"
    assert max(all_unlocks) <= 50, f"最高解锁应≤50, 实际 {max(all_unlocks)}"
    print(f"✓ 解锁等级范围: {min(all_unlocks)} - {max(all_unlocks)}")


def test_aliases_resolve():
    """验证别名解析: 老 ID 映射到新 ID."""
    templates = json.loads(
        (PLUGIN_ROOT / "data/config/gear_templates.json").read_text(encoding="utf-8")
    )
    build_rod_items(templates)  # 触发 ITEM_ALIASES 加载

    # 老 ID 测试 (别名映射)
    assert resolve_item_id("玻璃钢竿") == "玻纤溪流竿"
    assert resolve_item_id("玻璃纤维竿") == "碳纤溪流竿"
    assert resolve_item_id("路亚竿") == "玻纤路亚竿"
    assert resolve_item_id("筏竿") == "玻纤筏钓竿"
    assert resolve_item_id("矶竿") == "玻纤海投竿"
    assert resolve_item_id("深海钓竿") == "玻纤海投竿"
    assert resolve_item_id("传说鱼竿") == "龙王竿"
    assert resolve_item_id("神话鱼竿") == "星海竿"

    # 新 ID 测试 (原样返回)
    assert resolve_item_id("玻纤溪流竿") == "玻纤溪流竿"
    assert resolve_item_id("纳米海投竿") == "纳米海投竿"
    assert resolve_item_id("龙王竿") == "龙王竿"

    # 不存在 ID 测试 (原样返回, 不抛错)
    assert resolve_item_id("不存在的竿") == "不存在的竿"
    assert resolve_item_id("") == ""
    assert resolve_item_id("竹竿") == "竹竿"
    print("✓ 别名解析 8 个老鱼竿 ID + 边界用例全通过")


def test_rod_effects_progression():
    """验证鱼竿数值梯度随 tier 提升 (承载单调递增)."""
    rods = _rods()
    # 比较 5 件型号跨 tier 1-5
    for w in ['溪流', '路亚', '台钓']:
        caps = []
        for m in ['玻纤', '碳纤', '高碳', '钛合金', '纳米']:
            rod = rods[f"{m}{w}竿"]
            caps.append(rod['base_effects']['load_capacity_max'])
        assert caps == sorted(caps), f"{w}竿 load 应递增: {caps}"
    print(f"✓ 溪流/路亚/台钓竿 load_capacity_max 单调递增")


def test_lines_count():
    """26 普通 + 5 顶级 = 31 件鱼线."""
    lines = _lines()
    assert len(lines) == 31, f"期望 31 件鱼线, 实际 {len(lines)}"
    print(f"✓ 鱼线总数 {len(lines)} 件 (26 普通 + 5 顶级)")


def test_line_naming():
    """鱼线命名: 1 棉线 + 材质+基础/编织/强化/精密/大师线."""
    lines = _lines()
    models = ['基础线', '编织线', '强化线', '精密线', '大师线']
    materials = ['尼龙', '碳纤', 'PE', '合金', '石墨烯']
    # 1 棉线
    assert '棉线' in lines, "缺少 '棉线'"
    # 5 材质 × 5 型号 = 25 普通 (材质在前, 型号在后)
    for mat in materials:
        for mod in models:
            assert f"{mat}{mod}" in lines, f"缺少 '{mat}{mod}'"
    # 顶级 5 件
    for top in ['龙王线', '龙神线', '星辰线', '星海线', '命运线']:
        assert top in lines, f"缺少顶级线 '{top}'"
    print(f"✓ 1 棉线 + 25 普通 + 5 顶级鱼线命名正确")


def test_line_load_progression():
    """鱼线承载应随型号和材质增加."""
    lines = _lines()
    # 同材质跨型号
    for mat in ['尼龙', '碳纤']:
        caps = [lines[f"{mat}{mod}"]['base_effects']['load_capacity_max']
                for mod in ['基础线', '编织线', '强化线', '精密线', '大师线']]
        assert caps == sorted(caps), f"{mat}线 load 应递增: {caps}"
    # 同型号跨材质
    for mod in ['基础线', '编织线', '强化线']:
        caps = [lines[f"{mat}{mod}"]['base_effects']['load_capacity_max']
                for mat in ['尼龙', '碳纤', 'PE', '合金']]
        assert caps == sorted(caps), f"{mod} load 应递增: {caps}"
    print("✓ 鱼线承载单调递增 (跨型号 + 跨材质)")


if __name__ == "__main__":
    test_rod_count()
    test_rod_initial_bamboo()
    test_rod_naming()
    test_load_progression()
    test_unlock_levels_spread()
    test_aliases_resolve()
    test_rod_effects_progression()
    test_lines_count()
    test_line_naming()
    test_line_load_progression()
    print("\n所有 gear_builder 测试通过 ✓")
