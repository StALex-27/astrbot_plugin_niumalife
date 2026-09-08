"""
tests/test_backpack_integration.py — 真实模拟 AstrBot runtime 跑 /背包
"""
import sys, types, importlib.util, json, asyncio
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = PLUGIN_ROOT.name
FULL_PREFIX = f"data.plugins.{PLUGIN_NAME}"
DATA_PLUGINS = PLUGIN_ROOT.parent.parent


# ============================================================
# 1. 模拟 AstrBot runtime plugin 包结构
# ============================================================
def make_pkg(full_name: str, rel_path: str):
    pkg = types.ModuleType(full_name)
    pkg.__path__ = [str(PLUGIN_ROOT / rel_path)]
    sys.modules[full_name] = pkg
    return pkg


sys.modules["data"] = make_pkg("data", DATA_PLUGINS.name)
sys.modules["data"].__path__ = [str(DATA_PLUGINS)]
make_pkg("data.plugins", DATA_PLUGINS.name)
make_pkg(FULL_PREFIX, PLUGIN_NAME)
make_pkg(f"{FULL_PREFIX}.modules", f"{PLUGIN_NAME}/modules")
make_pkg(f"{FULL_PREFIX}.src", f"{PLUGIN_NAME}/src")
make_pkg(f"{FULL_PREFIX}.src.commands", f"{PLUGIN_NAME}/src/commands")
make_pkg(f"{FULL_PREFIX}.src.data", f"{PLUGIN_NAME}/src/data")
make_pkg(f"{FULL_PREFIX}.src.fishing", f"{PLUGIN_NAME}/src/fishing")


# ============================================================
# 2. 加载 modules + user_view + helpers + item_detail + backpack
# ============================================================
def load(full_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(full_name, str(PLUGIN_ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


load(f"{FULL_PREFIX}.modules.constants", "modules/constants.py")
load(f"{FULL_PREFIX}.modules.entry_lib", "modules/entry_lib.py")
load(f"{FULL_PREFIX}.modules.item", "modules/item.py")
load(f"{FULL_PREFIX}.modules.templates", "modules/templates.py")
load(f"{FULL_PREFIX}.src.data.user_view", "src/data/user_view.py")
load(f"{FULL_PREFIX}.src.commands._helpers", "src/commands/_helpers.py")


# Mock fishing_manager BEFORE loading item_detail
fm = types.ModuleType(f"{FULL_PREFIX}.src.fishing.fishing_manager")
fm.__package__ = f"{FULL_PREFIX}.src.fishing"
fish_data = json.loads((PLUGIN_ROOT / "data/config/fishes.json").read_text())
fm.FISHES = {k: v for k, v in fish_data.items() if isinstance(v, dict) and v.get("category") == "fish"}
fm._ensure_loaded = lambda: None
fm.length_for_size_label = lambda *args, **kwargs: 30.0
fm.format_length = lambda cm: f"{cm}cm"
sys.modules[f"{FULL_PREFIX}.src.fishing.fishing_manager"] = fm

load(f"{FULL_PREFIX}.src.commands.item_detail", "src/commands/item_detail.py")
bp = load(f"{FULL_PREFIX}.src.commands.backpack", "src/commands/backpack.py")


# ============================================================
# 3. Mock event/store/sender
# ============================================================
class FakeResult:
    def __init__(self, text=""): self.text = text
    def __str__(self): return self.text


class FakeSender:
    def __init__(self):
        self.cards = []
        self.texts = []
    async def send_card(self, event, card_type, data, fallback_text=""):
        self.cards.append((card_type, data))
        yield FakeResult(f"[CARD {card_type}]: {data.get('name', '?')}")
        return


class FakeEvent:
    def __init__(self, msg):
        self.message_str = msg
        self._sender_id = "test_user"
    def get_sender_id(self): return self._sender_id
    def plain_result(self, text): return FakeResult(text)
    def stop_event(self): pass


class FakeStore:
    async def get_user(self, uid):
        return {
            "user_id": uid,
            "nickname": "测试玩家",
            "inventory": [
                {"id": "草鱼", "name": "草鱼", "type": "fish", "weight": 5.2, "rarity": "common"},
                {"id": "草鱼", "name": "草鱼", "type": "fish", "weight": 4.8, "rarity": "common"},
                {"id": "蓝鲸", "name": "蓝鲸", "type": "fish", "weight": 50000, "rarity": "mythic"},
                {"id": "面包", "name": "面包", "type": "food", "quantity": 3},
                {"id": "竹竿", "name": "竹竿", "type": "item", "quantity": 1},
            ]
        }


class FakeParser:
    def parse(self, event):
        parts = event.message_str.strip().split()
        if not parts: return "", []
        return parts[0], parts[1:]


# ============================================================
# 4. 跑所有场景
# ============================================================
async def main():
    sender = FakeSender()
    store = FakeStore()
    parser = FakeParser()

    def dump(label):
        print(f"\n  --- {label} ---")
        print(f"  cards: {len(sender.cards)}")
        for ct, d in sender.cards:
            if isinstance(d, dict):
                if 'items' in d:
                    items = d.get('items', [])
                    print(f"    type={ct}, items={len(items)}")
                    for it in items[:5]:
                        nm = it.get('name')
                        qty = it.get('quantity')
                        is_fish = it.get('is_fish')
                        print(f"      - {nm} qty={qty} fish={is_fish}")
                elif 'is_fish' in d and 'name' in d:
                    print(f"    type={ct}, name={d.get('name')}, is_fish={d.get('is_fish')}, rarity={d.get('rarity')}")
                else:
                    print(f"    type={ct}, keys={list(d.keys())[:5]}")
        sender.cards.clear()

    print("=" * 60)
    print("TEST 1: /背包 (无参数)")
    print("=" * 60)
    event = FakeEvent("背包")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("无参数")

    print("\n" + "=" * 60)
    print("TEST 2: /背包 鱼 (筛选类别)")
    print("=" * 60)
    event = FakeEvent("背包 鱼")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("鱼")

    print("\n" + "=" * 60)
    print("TEST 3: /背包 草鱼 (单条详情, 持有)")
    print("=" * 60)
    event = FakeEvent("背包 草鱼")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("草鱼")

    print("\n" + "=" * 60)
    print("TEST 4: /背包 蓝鲸 (单条详情, 持有)")
    print("=" * 60)
    event = FakeEvent("背包 蓝鲸")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("蓝鲸")

    print("\n" + "=" * 60)
    print("TEST 5: /背包 鲫鱼王 (单条详情, 未持有, fallback FISHES)")
    print("=" * 60)
    event = FakeEvent("背包 鲫鱼王")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("鲫鱼王")

    print("\n" + "=" * 60)
    print("TEST 6: /背包 不存在xyz (filter error)")
    print("=" * 60)
    event = FakeEvent("背包 不存在xyz")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("不存在xyz")

    print("\n" + "=" * 60)
    print("TEST 7: /背包 大 (筛选尺寸)")
    print("=" * 60)
    event = FakeEvent("背包 大")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("大")

    print("\n" + "=" * 60)
    print("TEST 8: /背包 草鱼 大 (单条详情优先, 因为草鱼 HIT)")
    print("=" * 60)
    event = FakeEvent("背包 草鱼 大")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("草鱼 大")

    print("\n" + "=" * 60)
    print("TEST 9: /背包 鱼 大 (筛选鱼+大, 因为'鱼' 不是物品名)")
    print("=" * 60)
    event = FakeEvent("背包 鱼 大")
    async for _ in bp.run_backpack_logic(event, store, parser, sender): pass
    dump("鱼 大")


asyncio.run(main())