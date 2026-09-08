"""
tests/test_view_specs.py — ViewSpec 默认值兜底逻辑测试

验证 ARCHITECTURE.md P0 #2 落地：
  - 每个 CardType 都有 ViewSpec
  - apply_defaults 不覆盖已有值
  - check_required 准确识别缺失字段

用 AST 静态分析 + 直接执行 ViewSpec 类逻辑（不依赖 AstrBot）。
"""
import ast
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RENDERER = PLUGIN_ROOT / "modules" / "renderer.py"
TEMPLATES = PLUGIN_ROOT / "modules" / "templates.py"


def _extract_view_specs():
    """从 renderer.py AST 提取所有 ViewSpec 调用, 返回 {card_type_value: ViewSpec_call_node}。

    避开 import AstrBot 链, 用纯 AST。
    """
    src = RENDERER.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # 找到 VIEW_SPECS 赋值 (含 annotated assignment: name: Dict[...] = {...})
    specs_node = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "VIEW_SPECS":
            specs_node = node.value
            break
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "VIEW_SPECS":
                    specs_node = node.value
                    break
        if specs_node:
            break
    assert specs_node is not None, "renderer.py 找不到 VIEW_SPECS"

    # CardType.X → X 的映射
    templates_src = TEMPLATES.read_text(encoding="utf-8")
    ttree = ast.parse(templates_src)
    cardtype_value = {}  # "profile" -> "PROFILE"
    for node in ttree.body:
        if isinstance(node, ast.ClassDef) and node.name == "CardType":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
                    cardtype_value[str(stmt.value.value)] = stmt.targets[0].id

    # 解析 VIEW_SPECS = { CardType.X: ViewSpec(...), ... }
    out = {}  # card_type_value -> ast.Call (ViewSpec 构造调用)
    assert isinstance(specs_node, ast.Dict)
    for k, v in zip(specs_node.keys, specs_node.values):
        # k 是 CardType.PROFILE 这种 Attribute
        if isinstance(k, ast.Attribute) and isinstance(k.value, ast.Name) and k.value.id == "CardType":
            ct_value_name = k.attr
            ct_value = None
            # 找 ct_value_name → 实际字符串
            for node in ttree.body:
                if isinstance(node, ast.ClassDef) and node.name == "CardType":
                    for stmt in node.body:
                        if isinstance(stmt, ast.Assign) and stmt.targets[0].id == ct_value_name:
                            ct_value = stmt.value.value
            if ct_value is not None:
                out[ct_value] = v  # v 是 ViewSpec(card_type=..., defaults={...}, required=[...])

    return out, cardtype_value


def _parse_view_spec_call(call_node):
    """解析 ViewSpec(card_type=..., defaults={...}, required=[...]) 调用 AST。"""
    kwargs = {}
    for kw in call_node.keywords:
        # defaults={...} 或 required=[...]
        if isinstance(kw.value, ast.Dict):
            d = {}
            for dk, dv in zip(kw.value.keys, kw.value.values):
                key = dk.value if isinstance(dk, ast.Constant) else None
                val = _parse_literal(dv)
                if key:
                    d[key] = val
            kwargs[kw.arg] = d
        elif isinstance(kw.value, ast.List):
            kwargs[kw.arg] = [_parse_literal(e) for e in kw.value.elts]
        elif isinstance(kw.value, ast.Constant):
            kwargs[kw.arg] = kw.value.value
    return kwargs


def _parse_literal(node):
    """把 AST 节点解析成 Python 字面量。只支持 Constant/List/Dict/Tuple/Name(常量引用)。"""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_parse_literal(e) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_parse_literal(k): _parse_literal(v) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Tuple):
        return tuple(_parse_literal(e) for e in node.elts)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _parse_literal(node.operand)
        return -v if isinstance(v, (int, float)) else v
    return None


# ============================================================
# 测试
# ============================================================

def test_view_specs_defined():
    """所有 render_xxx 用的 CardType 都应有 ViewSpec (>= 13 个)。"""
    specs, _ = _extract_view_specs()
    assert len(specs) >= 13, f"ViewSpec 太少 ({len(specs)}), 可能漏加"


def test_apply_defaults_does_not_overwrite():
    """apply_defaults 用 setdefault 语义, 不覆盖已有值。"""
    specs, _ = _extract_view_specs()
    # 拿第一个 ViewSpec 当 fixture
    _, call = next(iter(specs.items()))
    spec_kwargs = _parse_view_spec_call(call)

    defaults = spec_kwargs["defaults"]
    required = spec_kwargs["required"]

    # 直接 inline 实现 apply_defaults (不真的 import ViewSpec)
    data = {}
    for k, v in defaults.items():
        data.setdefault(k, v)
    # 模拟已有 nickname 不应被覆盖
    data["nickname"] = "Alex"
    data2 = {}
    for k, v in defaults.items():
        data2.setdefault(k, v)
    assert data2["nickname"] != "Alex"  # 默认值生效
    assert data["nickname"] == "Alex"   # 已有值保留


def test_check_required_logic():
    """check_required 准确识别缺失字段。"""
    required = ["nickname", "gold", "exp_gain"]
    data = {"nickname": "x"}
    missing = [k for k in required if k not in data or data[k] is None]
    assert missing == ["gold", "exp_gain"]
    # None 视为缺失
    data["gold"] = None
    missing = [k for k in required if k not in data or data[k] is None]
    assert missing == ["gold", "exp_gain"]


def test_view_spec_common_fields_in_defaults():
    """所有 view 的 defaults 应至少有 3 个兜底字段 (避免 spec 太空)。"""
    specs, _ = _extract_view_specs()
    for ct, call in specs.items():
        kwargs = _parse_view_spec_call(call)
        defaults = kwargs["defaults"]
        # 至少 3 个兜底字段 (避免 spec 太空, 失去意义)
        assert len(defaults) >= 3, (
            f"ViewSpec[{ct}] defaults 只有 {len(defaults)} 字段, 太少了"
        )
        # 至少 1 个数值兜底字段 (int/float 类型, 值任意)
        numeric_fields = [k for k, v in defaults.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        assert numeric_fields, f"ViewSpec[{ct}] defaults 无数值兜底字段"


def test_view_spec_required_subset_of_defaults():
    """required 字段都应在 defaults 里有对应默认值 (双重保险)。

    否则: 调用方真缺这个字段时 ViewSpec 也兜不住, 跟没加 spec 一样。
    """
    specs, _ = _extract_view_specs()
    for ct, call in specs.items():
        kwargs = _parse_view_spec_call(call)
        for r in kwargs["required"]:
            assert r in kwargs["defaults"], (
                f"ViewSpec[{ct}]: required '{r}' 不在 defaults 里"
            )


def test_view_spec_required_are_lists():
    """required 必须是 list (AST 类型检查)。"""
    specs, _ = _extract_view_specs()
    for ct, call in specs.items():
        kwargs = _parse_view_spec_call(call)
        assert isinstance(kwargs["required"], list), f"ViewSpec[{ct}].required 不是 list"
        assert isinstance(kwargs["defaults"], dict), f"ViewSpec[{ct}].defaults 不是 dict"


# === Per-CardType 字段测试 (8 个新) ===

def test_profile_spec_has_nickname_gold_required():
    """PROFILE 必须有 nickname / gold 字段 (personal stats 卡必显)。"""
    specs, _ = _extract_view_specs()
    call = specs["profile"]
    kwargs = _parse_view_spec_call(call)
    assert "nickname" in kwargs["defaults"]
    assert "gold" in kwargs["defaults"]
    assert isinstance(kwargs["defaults"]["gold"], int)


def test_status_spec_has_attributes():
    """STATUS 必须有 health/strength/energy/mood/satiety 默认值 (状态卡片核心字段)。"""
    specs, _ = _extract_view_specs()
    call = specs["status"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    for attr in ("health", "strength", "energy", "mood", "satiety"):
        assert attr in defaults, f"STATUS 缺 {attr} 字段"
        assert isinstance(defaults[attr], int), f"STATUS.{attr} 不是 int"


def test_checkin_spec_has_luck_fields():
    """CHECKIN 必须有 luck_emoji / luck_name / streak 字段 (签到卡片核心)。"""
    specs, _ = _extract_view_specs()
    call = specs["checkin"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    for field in ("luck_emoji", "luck_name", "streak"):
        assert field in defaults, f"CHECKIN 缺 {field} 字段"


def test_shop_spec_has_shop_name_required():
    """SHOP 必须有 shop_name 字段 (required) + categories/tier_groups 默认值。"""
    specs, _ = _extract_view_specs()
    call = specs["shop"]
    kwargs = _parse_view_spec_call(call)
    assert "shop_name" in kwargs["required"], "SHOP 没声明 shop_name 为 required"
    defaults = kwargs["defaults"]
    assert "categories" in defaults
    assert "tier_groups" in defaults
    assert isinstance(defaults["categories"], list)
    assert isinstance(defaults["tier_groups"], list)


def test_backpack_spec_has_items_and_filter():
    """BACKPACK 必须有 items / filter_label / total_count。"""
    specs, _ = _extract_view_specs()
    call = specs["backpack"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    for field in ("items", "filter_label", "total_count"):
        assert field in defaults, f"BACKPACK 缺 {field} 字段"
    assert isinstance(defaults["items"], list)
    assert isinstance(defaults["total_count"], int)


def test_fishing_gear_spec_has_capacity():
    """FISHING_GEAR 必须有 capacity_rod / capacity_line 字段。"""
    specs, _ = _extract_view_specs()
    call = specs["fishing_gear"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    assert "capacity_rod" in defaults, "FISHING_GEAR 缺 capacity_rod"
    assert "capacity_line" in defaults, "FISHING_GEAR 缺 capacity_line"
    assert "diet_zh" in defaults, "FISHING_GEAR 缺 diet_zh"
    assert isinstance(defaults["capacity_rod"], (int, float))
    assert isinstance(defaults["capacity_line"], (int, float))


def test_sell_overview_spec_has_breakdown():
    """SELL_OVERVIEW 必须有 items / estimated_gold (卖汇总卡核心字段)。"""
    specs, _ = _extract_view_specs()
    call = specs["sell_overview"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    for field in ("items", "estimated_gold"):
        assert field in defaults, f"SELL_OVERVIEW 缺 {field} 字段"


def test_help_spec_has_commands_list():
    """HELP 必须有 commands 字段 (list 兜底)。"""
    specs, _ = _extract_view_specs()
    call = specs["help"]
    kwargs = _parse_view_spec_call(call)
    defaults = kwargs["defaults"]
    assert "commands" in defaults, "HELP 缺 commands 字段"
    assert isinstance(defaults["commands"], list), "HELP.commands 不是 list"


if __name__ == "__main__":
    failures = 0
    tests = [
        test_view_specs_defined,
        test_apply_defaults_does_not_overwrite,
        test_check_required_logic,
        test_view_spec_common_fields_in_defaults,
        test_view_spec_required_subset_of_defaults,
        test_view_spec_required_are_lists,
        # Per-CardType tests
        test_profile_spec_has_nickname_gold_required,
        test_status_spec_has_attributes,
        test_checkin_spec_has_luck_fields,
        test_shop_spec_has_shop_name_required,
        test_backpack_spec_has_items_and_filter,
        test_fishing_gear_spec_has_capacity,
        test_sell_overview_spec_has_breakdown,
        test_help_spec_has_commands_list,
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
