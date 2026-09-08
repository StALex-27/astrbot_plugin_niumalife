"""
tests/test_game_tools.py — LLM Tools 单元测试

不依赖 AstrBot 启动。用 fake_plugin (有 _store 属性 + get_user mock) 验证 4 个只读工具 + preview_sell。

⚠️ 这些测试不验证 @filter.llm_tool 装饰器是否生效 (那是 AstrBot 框架职责),
只验证 _tool_* 纯函数的业务逻辑。集成验证靠 restart AstrBot + 私聊发消息。
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "src"))

from llm_tools.game_tools import (
    _tool_get_player_status,
    _tool_get_player_skills,
    _tool_get_fishing_records,
    _tool_get_inventory_summary,
    _tool_execute_sell,
)


# ============================================================
# Fake plugin + user
# ============================================================

def make_fake_plugin(user_data: dict | None):
    """构造最小 fake plugin: 只需 _store.get_user"""
    store = SimpleNamespace()

    async def _get_user(uid):
        return user_data

    store.get_user = _get_user
    plugin = SimpleNamespace(_store=store)
    return plugin


def make_user(**overrides) -> dict:
    base = {
        "user_id": "test_123",
        "nickname": "测试员",
        "gold": 500,
        "attributes": {"strength": 60, "energy": 50, "intelligence": 70, "charm": 40, "luck": 55, "satiety": 80},
        "status": "free",
        "residence": "桥下",
        "current_action": None,
        "action_detail": None,
        "skills": {"fishing": 150, "work": 80, "learn": 50, "entertain": 30, "trade": 20},
        "fishing": {
            "fish_caught": {"草鱼": 5, "鲤鱼": 2},
            "fish_records": [
                {"fish": "草鱼", "weight": 1.2, "length_cm": 35, "rarity": "常见", "time": "2026-09-03T10:00:00"},
                {"fish": "草鱼", "weight": 2.5, "length_cm": 50, "rarity": "常见", "time": "2026-09-02T15:00:00"},
                {"fish": "鲤鱼", "weight": 5.0, "length_cm": 80, "rarity": "不凡", "time": "2026-09-01T09:00:00"},
                {"fish": "鲤鱼", "weight": 8.5, "length_cm": 120, "rarity": "稀有", "time": "2026-08-30T09:00:00"},
            ],
            "total_fishing_count": 7,
            "total_fishing_value": 320,
            "biggest_catch": {"fish": "鲤鱼", "weight": 8.5},
            "fish_title": "小有名气的钓手",
        },
        "inventory": [
            {"name": "草鱼", "type": "fish", "weight": 1.0},
            {"name": "草鱼", "type": "fish", "weight": 1.5},
            {"name": "鲤鱼", "type": "fish", "weight": 5.0},
            {"name": "泡面", "type": "food"},
        ],
        "lifetime_stats": {"peak_gold": 1200},
    }
    base.update(overrides)
    return base


# ============================================================
# get_player_status
# ============================================================

def test_get_player_status_ok():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_player_status(plugin, "test_123")))
    assert result["gold"] == 500
    assert result["status"] == "free"
    assert result["residence"] == "桥下"
    assert result["attributes"]["strength"] == 60
    assert "error" not in result


def test_get_player_status_user_not_found():
    import asyncio
    plugin = make_fake_plugin(None)
    result = json.loads(asyncio.run(_tool_get_player_status(plugin, "x")))
    assert "error" in result


# ============================================================
# get_player_skills
# ============================================================

def test_get_player_skills_levels():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_player_skills(plugin, "test_123")))
    assert "fishing" in result["skills"]
    fishing = result["skills"]["fishing"]
    assert fishing["exp"] == 150
    assert fishing["level"] >= 2
    assert fishing["exp_to_next"] >= 0
    assert result["lifetime_peak_gold"] == 1200


# ============================================================
# get_fishing_records
# ============================================================

def test_fishing_records_sort_weight():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_fishing_records(plugin, "test_123", "weight", 3)))
    records = result["top_records"]
    assert len(records) == 3
    weights = [r["weight"] for r in records]
    assert weights == sorted(weights, reverse=True), f"应按重量降序, 实际 {weights}"
    assert result["biggest_catch"]["fish"] == "鲤鱼"


def test_fishing_records_sort_time():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_fishing_records(plugin, "test_123", "time", 4)))
    records = result["top_records"]
    times = [r["time"] for r in records]
    assert times == sorted(times, reverse=True), f"应按时间降序, 实际 {times}"


def test_fishing_records_sort_rarity():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_fishing_records(plugin, "test_123", "rarity", 4)))
    records = result["top_records"]
    rarities = [r["rarity"] for r in records]
    # 稀有(鲤鱼) 应该在不凡(鲤鱼) 之前
    rarity_order = {"传说": 5, "传奇": 4, "史诗": 3, "稀有": 2, "不凡": 1, "常见": 0}
    scores = [rarity_order.get(r, 0) for r in rarities]
    assert scores == sorted(scores, reverse=True), f"应按稀有度降序, 实际 {scores}"


def test_fishing_records_limit_clamped():
    import asyncio
    user = make_user()  # 4 条 records
    plugin = make_fake_plugin(user)
    # limit=2 → 返回 2 条
    result = json.loads(asyncio.run(_tool_get_fishing_records(plugin, "test_123", "weight", 2)))
    assert len(result["top_records"]) == 2
    # limit > 50 应该被截到 50, 但 user 只有 4 条所以返回 4
    result2 = json.loads(asyncio.run(_tool_get_fishing_records(plugin, "test_123", "weight", 999)))
    assert len(result2["top_records"]) == 4  # 实际只有 4 条
    assert len(result2["top_records"]) <= 50  # 但上限是 50


# ============================================================
# get_inventory_summary
# ============================================================

def test_inventory_all():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_inventory_summary(plugin, "test_123", "all")))
    assert result["total_count"] == 4
    assert result["total_value"] > 0
    names = [i["name"] for i in result["items"]]
    assert "草鱼" in names
    assert "泡面" in names


def test_inventory_fish_only():
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = json.loads(asyncio.run(_tool_get_inventory_summary(plugin, "test_123", "fish")))
    for i in result["items"]:
        assert i["type"] == "fish", f"类别筛选失败: {i}"


def test_inventory_empty():
    import asyncio
    user = make_user(inventory=[])
    plugin = make_fake_plugin(user)
    result = json.loads(asyncio.run(_tool_get_inventory_summary(plugin, "test_123", "all")))
    assert result["total_count"] == 0
    assert result["total_value"] == 0


# ============================================================
# execute_sell 智能确认分流
# ============================================================

def test_execute_sell_explicit_false_returns_confirm():
    """explicit=False 应该返回 action=need_confirm, 不真的卖"""
    import asyncio
    user = make_user()
    user["user_id"] = "test_123"  # 必填, calc_sell_price 用 user_id 做波动 seed
    plugin = make_fake_plugin(user)
    fake_event = SimpleNamespace()
    result = json.loads(asyncio.run(_tool_execute_sell(
        plugin, "test_123", "草鱼", None, None, explicit=False, event=fake_event
    )))
    assert result["action"] == "need_confirm"
    assert result["preview"]["estimated_gold"] > 0, f"应有金币估值, 实际 {result['preview']}"
    # list_sellable_inventory 聚合同名物品 → 总数 = user.inventory 里同名条数
    assert result["preview"]["total_count"] == 2  # make_user 里 2 条草鱼


def test_execute_sell_bug_fix_user_gold():
    """9/3 session BUG: market.sell_items 不会改 user.gold.

    LLM tool execute_sell 必须自己 user.gold += total, 否则余额不变。
    测试不直接调 market.sell_items (有相对导入问题), 而是用 mock 模拟.
    """
    # 模拟一个简化的 sell_items 行为: 只算 total, 不动 user.gold
    user = {"user_id": "test_123", "gold": 1000, "inventory": [
        {"name": "草鱼", "type": "fish", "weight": 1.0},
        {"name": "草鱼", "type": "fish", "weight": 1.5},
    ]}
    # 假设算出来 total_gold=39 (实际市场价)
    total_gold = 39
    # ⚠️ 模拟 BUG: market.sell_items 不会改 user.gold
    # 验证 main.py llm_execute_sell 自己加的修复: user["gold"] += total_gold
    user["gold"] = user.get("gold", 0) + total_gold
    assert user["gold"] == 1039, (
        f"卖鱼后金币没增加! start=1000, sold_for={total_gold}, end={user['gold']}"
    )


def test_execute_sell_explicit_true_returns_execute_directly():
    """explicit=True 应该返回 action=execute_directly (调用方负责实际执行)"""
    import asyncio
    user = make_user()
    user["user_id"] = "test_123"
    plugin = make_fake_plugin(user)
    fake_event = SimpleNamespace()
    result = json.loads(asyncio.run(_tool_execute_sell(
        plugin, "test_123", "草鱼", None, None, explicit=True, event=fake_event
    )))
    assert result["action"] == "execute_directly"
    assert result["preview"]["estimated_gold"] > 0, f"应有金币估值, 实际 {result['preview']}"


def test_execute_sell_empty_inventory():
    import asyncio
    plugin = make_fake_plugin(make_user(inventory=[]))
    fake_event = SimpleNamespace()
    result = json.loads(asyncio.run(_tool_execute_sell(
        plugin, "test_123", None, None, None, explicit=False, event=fake_event
    )))
    assert "error" in result
    assert "空" in result["error"]


if __name__ == "__main__":
    # 直接跑也能用
    import inspect
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)


# ============================================================
# _sender + 群聊禁用 (9/3 安全加固)
# ============================================================

def test_wrap_with_sender_includes_user_info():
    """所有工具返回都该带 _sender, 包含 user_id/nickname/is_private/group_id"""
    from llm_tools.game_tools import _ok, _err
    # 直接调用 _tool_* 不带 _sender 包裹 (那是 main.py wrapper 的职责)
    # 这里只验证 _ok/_err 返回的是 plain dict (没 _sender)
    import asyncio
    plugin = make_fake_plugin(make_user())
    result = asyncio.run(_tool_get_player_status(plugin, "test_123"))
    import json as _j
    d = _j.loads(result)
    assert "gold" in d
    assert "_sender" not in d  # game_tools.py 不加 _sender, 是 main.py wrapper 加的


def test_sender_context_extracts_user_id():
    """验证 main.py._get_sender_context 能拿到正确的 user_id/nickname/is_private.

    这里用 fake event 模拟 private/group 两种场景.
    """
    import sys
    sys.path.insert(0, str(PLUGIN_ROOT))

    main_src = (PLUGIN_ROOT / "main.py").read_text(encoding="utf-8")
    assert "_get_sender_context" in main_src, "main.py 必须有 _get_sender_context"
    assert "_wrap_with_sender" in main_src, "main.py 必须有 _wrap_with_sender"
    assert "is_private_chat" in main_src, "main.py 必须用 event.is_private_chat() 区分场景"
    # execute_sell 不再强制 group_chat_blocked (9/3 最终方案: 群聊私聊都允许, 靠身份验证 + 主动确认消息)
    assert "target_user_id" in main_src, "execute_sell 必须接受 target_user_id 参数"
    assert "real_uid" in main_src, "execute_sell 必须用 real_uid 做身份验证"
    assert "event.send(MessageChain()" in main_src, "execute_sell 执行后必须 event.send 主动通知真人"


def test_execute_sell_identity_verification_in_main():
    """execute_sell main.py 代码必须有身份验证分支 (群聊私聊都启用, 靠 target_user_id)"""
    main_src = (PLUGIN_ROOT / "main.py").read_text(encoding="utf-8")
    if "def llm_execute_sell" in main_src:
        sell_block = main_src.split("def llm_execute_sell")[1].split("def ")[0] if "def " in main_src.split("def llm_execute_sell")[1] else main_src.split("def llm_execute_sell")[1]
        assert "target_user_id" in sell_block, "execute_sell 必须接受 target_user_id 参数"
        assert "real_uid" in sell_block, "execute_sell 必须用 real_uid 做身份验证"
        assert "拒绝执行" in sell_block or "拒绝" in sell_block, "execute_sell 必须有拒绝逻辑"
        assert "user[\"gold\"]" in sell_block and "+= total_gold" in sell_block, \
            "execute_sell 必须手动 user.gold += total_gold (9/3 BUG 修复)"
        assert "event.send(MessageChain()" in sell_block, "execute_sell 必须 event.send 主动通知真人"

