"""
tests/test_llm_tool_schemas.py — LLM 工具 docstring schema 自动校验

为什么需要这个测试：
- AstrBot 的 @filter.llm_tool 装饰器靠 docstring-parser 解析参数描述。
- 9/3 session 实证: 1 个工具的 docstring 缺类型标记 (string)/(number)
  会让装饰器拒绝加载 → 整个 plugin 启动失败。
- 工具数会持续增长（当前 31 个），靠人眼检查 100% 会漏。

校验规则（CHANGELOG 9/3 已明确）：
1. 每个 @filter.llm_tool(name="...") 方法必须有 docstring
2. docstring 必须包含 Args: 段（除只读 event 单参数工具外）
3. 每个 Args: 段中的参数必须有 (string)/(number)/(integer)/(boolean)/(array)/(object) 类型标记
4. 函数签名中的参数（除 self, event 外）必须都在 Args: 段中出现
5. Returns: 段必须存在

不依赖 AstrBot 运行时，纯静态分析 main.py 源码。
"""
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = PLUGIN_ROOT / "main.py"


def _extract_llm_tools():
    """提取所有 @filter.llm_tool 装饰的方法及其 docstring + 签名。"""
    source = MAIN_PY.read_text(encoding="utf-8")
    # 匹配: @filter.llm_tool(name="...")\n ... async def xxx(...) -> ...: """docstring"""
    pattern = re.compile(
        r'@filter\.llm_tool\(name="(\w+)"\)\s*\n'
        r'\s*async def (\w+)\(([^)]*)\)(?:\s*->\s*[^:]+)?:\s*'
        r'"""(.*?)"""',
        re.DOTALL,
    )
    tools = []
    for m in pattern.finditer(source):
        name, method, sig, doc = m.groups()
        # 解析签名参数 (除 self)
        sig_params = []
        for p in sig.split(","):
            p = p.strip()
            if not p or p == "self":
                continue
            # 去掉类型注解 + 默认值
            param_name = re.split(r"[:=]", p, 1)[0].strip()
            sig_params.append(param_name)
        tools.append(
            {
                "name": name,
                "method": method,
                "sig_params": sig_params,
                "doc": doc.strip(),
            }
        )
    return tools


def _extract_args_section(doc: str) -> str:
    """提取 Args: 段（Returns: / Note: 之前）。"""
    lines = doc.split("\n")
    in_args = False
    args_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Args:"):
            in_args = True
            continue
        if in_args:
            if stripped.startswith(("Returns:", "Note:", "Example:", "Raises:")):
                break
            args_lines.append(line)
    return "\n".join(args_lines)


def _parse_args(args_section: str) -> list[tuple[str, str | None]]:
    """解析 Args: 段里的参数列表，返回 [(name, type_marker_or_None)]。

    每个参数形式: `param_name(string): 描述` 或 `param_name: 描述`（缺类型标记）。
    """
    results = []
    for line in args_section.split("\n"):
        stripped = line.strip()
        if not stripped or not stripped[0].isalpha():
            continue
        # 匹配 "param_name(type_marker):" 或 "param_name:"
        m = re.match(r"^(\w+)\s*\((string|number|integer|boolean|array|object)\)\s*:?", stripped)
        if m:
            results.append((m.group(1), m.group(2)))
            continue
        # 缺类型标记
        m2 = re.match(r"^(\w+)\s*:?", stripped)
        if m2:
            results.append((m2.group(1), None))
    return results


# ============================================================
# 测试用例
# ============================================================

def test_llm_tools_count_minimum():
    """至少 20 个 LLM 工具（防止批量删工具）。"""
    tools = _extract_llm_tools()
    assert len(tools) >= 20, (
        f"LLM 工具数 {len(tools)} 过少，可能误删。请检查 main.py。"
    )
    print(f"  ✓ 找到 {len(tools)} 个 LLM 工具")


def test_all_llm_tools_have_docstring():
    """每个 LLM 工具必须有 docstring。"""
    tools = _extract_llm_tools()
    missing = [t["name"] for t in tools if not t["doc"]]
    assert not missing, f"以下工具缺 docstring: {missing}"


def test_all_llm_tools_have_returns_section():
    """每个 LLM 工具 docstring 必须含 Returns: 段（AstrBot 装饰器依赖）。"""
    tools = _extract_llm_tools()
    missing = [t["name"] for t in tools if "Returns:" not in t["doc"]]
    assert not missing, (
        f"以下工具缺 Returns: 段（会导致 @filter.llm_tool 拒绝加载）:\n"
        + "\n".join(f"  - {n}" for n in missing)
    )


def test_llm_tool_sigs_match_args():
    """函数签名中每个非 self/event 参数必须在 Args: 段中声明。"""
    tools = _extract_llm_tools()
    mismatches = []
    for t in tools:
        args_section = _extract_args_section(t["doc"])
        declared = {name for name, _ in _parse_args(args_section)}
        for param in t["sig_params"]:
            if param == "event":
                continue
            if param not in declared:
                mismatches.append((t["name"], param))
    assert not mismatches, (
        "以下工具签名参数未在 docstring Args: 中声明:\n"
        + "\n".join(f"  - {name}: 缺参数 '{p}'" for name, p in mismatches)
    )


def test_llm_tool_args_have_type_markers():
    """每个 Args: 段里的参数必须有 (string)/(number)/(integer)/(boolean)/(array)/(object) 类型标记。

    这是 CHANGELOG 9/3 实证过的硬性要求，缺标记会让装饰器拒绝加载。
    """
    tools = _extract_llm_tools()
    bad_tools = []
    for t in tools:
        args_section = _extract_args_section(t["doc"])
        parsed = _parse_args(args_section)
        # 没有 args_section 的工具（只接 event）跳过
        if not parsed:
            continue
        # 检查所有声明的参数都有类型标记
        missing_type = [name for name, type_marker in parsed if not type_marker]
        if missing_type:
            bad_tools.append((t["name"], missing_type))
    assert not bad_tools, (
        "以下工具的 Args 段缺类型标记 (string)/(number)/(integer)/(boolean)/(array)/(object) "
        "—— AstrBot 装饰器会拒绝加载整个 plugin:\n"
        + "\n".join(
            f"  - {n}: 缺类型标记的参数 {params}"
            for n, params in bad_tools
        )
    )


def test_no_duplicate_llm_tool_names():
    """每个 LLM 工具名必须唯一。"""
    tools = _extract_llm_tools()
    names = [t["name"] for t in tools]
    seen = set()
    dupes = []
    for n in names:
        if n in seen:
            dupes.append(n)
        seen.add(n)
    assert not dupes, f"重复的 LLM 工具名: {dupes}"


def test_known_critical_tools_exist():
    """关键工具必须存在（防止误删）。"""
    tools = _extract_llm_tools()
    names = {t["name"] for t in tools}
    required = {
        "execute_sell",        # LLM 卖物品写入工具（9/3 安全加固核心）
        "preview_sell",        # LLM 卖物品预览工具
        "get_player_status",   # LLM 查玩家状态
        "do_eat",              # LLM 吃东西写入工具
    }
    missing = required - names
    assert not missing, f"关键工具缺失: {missing}"


if __name__ == "__main__":
    # 直接运行时一个一个跑
    failures = 0
    tests = [
        test_llm_tools_count_minimum,
        test_all_llm_tools_have_docstring,
        test_all_llm_tools_have_returns_section,
        test_llm_tool_sigs_match_args,
        test_llm_tool_args_have_type_markers,
        test_no_duplicate_llm_tool_names,
        test_known_critical_tools_exist,
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
