"""
content_registry.py — 内容注册中心（统一所有配置数据）

设计目标：
- 物品/鱼/食物/课程/工作/股票/技能等配置数据走单一注册入口
- 业务层通过 ContentRegistry 查：name → 所属 category / tier / slot / effects / 可装备性
- 加新内容只改 source json + 在 registry 加 1 行声明，自动同步到 market/render/llm
- 不替代 items.json/fishes.json（仍是 source of truth），只是叠加元信息 (actions 字段)

加载方式：
- 启动时一次性从所有 source JSON 读入内存，构造 ContentDef
- 懒加载：第一次访问 ContentRegistry.instance() 时才加载

向后兼容：
- source JSON 没有 actions 字段时, registry 根据 category/subcategory/slot 字段**自动推导**
  默认 actions (用户不用手填也能跑)
- 有 actions 字段时优先用 JSON 声明
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


# ============================================================
# 标准动作枚举 (替代散落的 if/elif)
# ============================================================

# 这些是合法的 actions 值, 业务层注册逻辑时按这里列
VALID_ACTIONS = frozenset({
    "sell",        # 可卖
    "buy",         # 可买
    "eat",         # 可吃 (食物)
    "use",         # 可使用 (药品/通用)
    "equip",       # 可装备 (装备/渔具)
    "use_in_fishing",  # 鱼饵/钓具参与钓鱼
    "learn",       # 可学习 (课程)
    "work",        # 可打工 (工作)
    "reside",      # 可居住 (住所)
    "entertain",   # 可娱乐 (娱乐项目)
    "enchant",     # 可附魔
})


@dataclass(frozen=True)
class ContentDef:
    """单条内容声明。

    字段语义和 source JSON 一一对应 (只是命名更 Pythonic):
      - content_type: "item" | "fish" | "course" | "job" | "residence" | "entertainment"
      - content_id:   在所属 json 里的 key (e.g. "泡面", "小鲫鱼")
      - name:         中文名
      - category:     大类 ("food" | "medicine" | "equip" | "fishing" | "fish" | ...)
      #      - subcategory: 子分类 (item 用, e.g. "instant" | "fishing_bait" | "fishing_lure")
      - tier:         等级 (1-5+)
      - rarity:       稀有度 (common/uncommon/rare/epic/legendary/mythic)
      - price:        商店价 (0 = 不可买/非卖)
      - is_stackable: 是否可堆叠
      - is_equippable: 是否可装备
      - slot:         装备槽 (fishing_rod / line / hook / float / bait / reel)
      - effects:      使用效果 {key: value}
      - emoji:        图标
      - actions:      支持的操作 (sell/buy/eat/equip/...)
      - extra:        原 JSON 的其它字段 (e.g. fish 的 habitat/weight_range)
    """
    content_type: str
    content_id: str
    name: str
    category: str = ""
    subcategory: str = ""
    tier: int = 1
    rarity: str = "common"
    price: int = 0
    is_stackable: bool = True
    is_equippable: bool = False
    slot: str = ""
    effects: Tuple[Tuple[str, Any], ...] = ()  # 改用 tuple of tuples 才能 frozen
    emoji: str = "📦"
    actions: Tuple[str, ...] = ()
    extra: Tuple[Tuple[str, Any], ...] = ()

    @property
    def effects_dict(self) -> dict:
        return dict(self.effects)

    @property
    def extra_dict(self) -> dict:
        return dict(self.extra)

    def supports(self, action: str) -> bool:
        return action in self.actions

    def to_dict(self) -> dict:
        """转回普通 dict (LLM 工具/渲染器需要)"""
        d = asdict(self)
        d["effects"] = self.effects_dict
        d["extra"] = self.extra_dict
        return d


# ============================================================
# 自动推导 actions (用户 JSON 没填时给合理默认)
# ============================================================

def _auto_actions(category: str, slot: str = "", is_stackable: bool = True,
                  price: int = 0, subcategory: str = "") -> tuple:
    """根据 category/slot/price 推导默认 actions。

    业务规则:
      - 有 slot: 可 equip
      - 鱼饵/拟饵 (bait/lure slot): use_in_fishing
      - food: 可 eat
      - medicine: 可 use
      - enchant: 可 enchant (附魔券被附魔操作使用)
      - price > 0: 可 buy + sell
    """
    actions = []
    cat = (category or "").lower()

    # 装备类
    if slot:
        actions.append("equip")
        if slot in (
            "fishing_rod", "fishing_line", "fishing_hook", "fishing_float",
            "fishing_bait", "fishing_lure", "fishing_reel", "fishing_waders"
        ):
            actions.append("use_in_fishing")

    # 食物/药品
    if cat == "food":
        actions.append("eat")
    elif cat == "medicine":
        actions.append("use")

    # 附魔券类 (enchant category + 可附魔物品)
    if cat in ("enchant", "scroll"):
        actions.append("enchant")

    # 价格 > 0 默认可买可卖
    if price and price > 0:
        actions.append("buy")
        actions.append("sell")

    return tuple(dict.fromkeys(actions))  # 去重保序


def subcategory_in_fishing_bait(slot: str) -> bool:
    # 9/7 命名统一: 全部加 fishing_ 前缀
    return slot in ("fishing_bait", "fishing_lure", "fishing_reel", "fishing_line", "fishing_hook", "fishing_float", "fishing_rod")


# ============================================================
# Registry 单例
# ============================================================

class ContentRegistry:
    """全局内容注册表，启动时一次性加载"""

    _instance: Optional["ContentRegistry"] = None

    def __init__(self):
        self._items: Dict[str, ContentDef] = {}
        self._fish: Dict[str, ContentDef] = {}
        self._foods: Dict[str, ContentDef] = {}  # 引用 ITEMS 里 category=food 的子集
        self._medicine: Dict[str, ContentDef] = {}
        self._equip: Dict[str, ContentDef] = {}  # category="equipment" 或 slot 非空非 fishing
        self._fishing_gear: Dict[str, ContentDef] = {}
        self._courses: Dict[str, ContentDef] = {}
        self._jobs: Dict[str, ContentDef] = {}
        self._residences: Dict[str, ContentDef] = {}
        self._entertainments: Dict[str, ContentDef] = {}
        self._by_action: Dict[str, List[ContentDef]] = {}
        self._by_name: Dict[str, ContentDef] = {}  # 中文名 → ContentDef (LLM 模糊匹配用)
        self._loaded = False
        self._load_errors: List[str] = []

    @classmethod
    def instance(cls) -> "ContentRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_all()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试用: 重置单例"""
        cls._instance = None

    # ============================================================
    # 加载
    # ============================================================

    def _load_all(self) -> None:
        """从所有 source JSON 加载"""
        # 计算 CONFIG_DIR: src/data/content_registry.py → ../../../data/config
        config_dir = Path(__file__).parent.parent.parent / "data" / "config"
        self._load_items(config_dir / "items.json")
        self._load_fish(config_dir / "fishes.json")
        self._load_courses(config_dir / "courses.json")
        self._load_jobs(config_dir / "jobs.json")
        self._load_residences(config_dir / "residences.json")
        self._load_entertainments(config_dir / "entertainments.json")
        self._build_indexes()
        self._loaded = True

    def _load_items(self, path: Path) -> None:
        """从 items.json 加载, 分类入 _items/_foods/_medicine/_equip/_fishing_gear"""
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_item_def(content_id, raw)
            except Exception as e:
                self._load_errors.append(f"items.json: {content_id} 加载失败: {e}")
                continue

            self._items[content_id] = d
            cat = (d.category or "").lower()
            # 装备/渔具分类: category 字段 OR slot 字段
            # 9/7 命名统一: 全部加 fishing_ 前缀
            is_fishing_slot = d.slot in (
                "fishing_rod", "fishing_line", "fishing_hook", "fishing_float",
                "fishing_bait", "fishing_lure", "fishing_reel", "fishing_waders"
            )
            if cat == "food":
                self._foods[content_id] = d
            elif cat == "medicine":
                self._medicine[content_id] = d
            elif is_fishing_slot:
                self._fishing_gear[content_id] = d
            elif cat in ("equipment", "equip") or d.slot:
                self._equip[content_id] = d

    def _load_fish(self, path: Path) -> None:
        """从 fishes.json 加载 (注: 鱼也算内容, 但 actions 不同: sell/eat/use_in_fishing)"""
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_fish_def(content_id, raw)
            except Exception as e:
                self._load_errors.append(f"fishes.json: {content_id} 加载失败: {e}")
                continue
            self._fish[content_id] = d

    def _load_courses(self, path: Path) -> None:
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_course_def(content_id, raw)
                self._courses[content_id] = d
            except Exception as e:
                self._load_errors.append(f"courses.json: {content_id} 加载失败: {e}")

    def _load_jobs(self, path: Path) -> None:
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_job_def(content_id, raw)
                self._jobs[content_id] = d
            except Exception as e:
                self._load_errors.append(f"jobs.json: {content_id} 加载失败: {e}")

    def _load_residences(self, path: Path) -> None:
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_residence_def(content_id, raw)
                self._residences[content_id] = d
            except Exception as e:
                self._load_errors.append(f"residences.json: {content_id} 加载失败: {e}")

    def _load_entertainments(self, path: Path) -> None:
        data = self._read_json(path)
        for content_id, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                d = self._make_entertainment_def(content_id, raw)
                self._entertainments[content_id] = d
            except Exception as e:
                self._load_errors.append(f"entertainments.json: {content_id} 加载失败: {e}")

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        # 过滤 string value 的"注释"key (_comment / _meta / _rarity_weight)
        return {k: v for k, v in data.items() if isinstance(v, (dict, list))}

    # ============================================================
    # 构造 ContentDef
    # ============================================================

    def _make_item_def(self, content_id: str, raw: dict) -> ContentDef:
        category = raw.get("category", "")
        slot = raw.get("slot", "") or ""
        price = int(raw.get("price", 0) or 0)
        subcategory = raw.get("subcategory", "") or ""

        # 取 actions: JSON 显式声明 > 自动推导
        declared = raw.get("actions")
        if declared and isinstance(declared, (list, tuple)):
            actions = tuple(a for a in declared if a in VALID_ACTIONS)
        else:
            actions = _auto_actions(category, slot, raw.get("stackable", True), price)
            # fishing 子分类特殊处理 (鱼饵 / 拟饵 / 装备)
            if subcategory in ("fishing_bait", "fishing_lure"):
                actions = tuple(dict.fromkeys(list(actions) + ["use_in_fishing"]))

        # 9/7: 鱼竿/装备 base_effects 是主字段 (e.g. load_capacity, habitat_pond),
        #      同时也支持顶层 effects 字段 (食物/道具用)
        merged_effects = dict(raw.get("base_effects") or {})
        if raw.get("effects"):
            merged_effects.update(raw["effects"])
        return ContentDef(
            content_type="item",
            content_id=content_id,
            name=raw.get("name", content_id),
            category=category,
            subcategory=subcategory,
            tier=int(raw.get("tier", 1) or 1),
            rarity=raw.get("rarity", "common"),
            price=price,
            is_stackable=bool(raw.get("stackable", True)),
            is_equippable=bool(slot),
            slot=slot,
            effects=tuple(merged_effects.items()),
            emoji=raw.get("emoji", "📦"),
            actions=actions,
            extra=tuple(
                (k, v) for k, v in raw.items()
                if k not in {
                    "name", "category", "subcategory", "tier", "rarity",
                    "price", "stackable", "slot", "effects", "emoji",
                    "actions", "_comment", "base_effects",
                }
            ),
        )

    def _make_fish_def(self, content_id: str, raw: dict) -> ContentDef:
        # 鱼: 默认 sell + eat (鱼可以吃) + use_in_fishing (钓鱼产物)
        declared = raw.get("actions")
        if declared and isinstance(declared, (list, tuple)):
            actions = tuple(a for a in declared if a in VALID_ACTIONS)
        else:
            base_price = int(raw.get("base_price", 0) or 0)
            actions = ("sell", "eat", "use_in_fishing") if base_price > 0 else ("eat", "use_in_fishing")

        return ContentDef(
            content_type="fish",
            content_id=content_id,
            name=raw.get("name", content_id),
            category="fish",
            tier=int(raw.get("tier", 1) or 1),
            rarity=raw.get("rarity", "common"),
            price=int(raw.get("base_price", 0) or 0),
            is_stackable=True,
            is_equippable=False,
            effects=tuple((k, v) for k, v in (raw.get("effects") or {}).items()),
            emoji=raw.get("emoji", "🐟"),
            actions=actions,
            extra=tuple(
                (k, v) for k, v in raw.items()
                if k not in {
                    "name", "category", "tier", "rarity", "emoji",
                    "actions", "_comment", "effects",
                }
            ),
        )

    def _make_course_def(self, content_id: str, raw: dict) -> ContentDef:
        price = int(raw.get("price", 0) or 0)
        declared = raw.get("actions")
        if declared and isinstance(declared, (list, tuple)):
            actions = tuple(a for a in declared if a in VALID_ACTIONS)
        else:
            actions = ("learn",) if price > 0 else ("learn",)  # 课程永远可学

        return ContentDef(
            content_type="course",
            content_id=content_id,
            name=raw.get("name", content_id),
            category="course",
            tier=int(raw.get("tier", 1) or 1),
            price=price,
            emoji=raw.get("emoji", "📚"),
            actions=actions,
            extra=tuple((k, v) for k, v in raw.items() if k not in {
                "name", "tier", "price", "emoji", "actions", "_comment",
            }),
        )

    def _make_job_def(self, content_id: str, raw: dict) -> ContentDef:
        return ContentDef(
            content_type="job",
            content_id=content_id,
            name=raw.get("name", content_id),
            category="job",
            tier=int(raw.get("tier", 1) or 1),
            price=int(raw.get("reward_gold", 0) or 0),  # 工作"价"=奖励
            emoji=raw.get("emoji", "💼"),
            actions=("work",),
            extra=tuple((k, v) for k, v in raw.items() if k not in {
                "name", "tier", "reward_gold", "emoji", "_comment",
            }),
        )

    def _make_residence_def(self, content_id: str, raw: dict) -> ContentDef:
        return ContentDef(
            content_type="residence",
            content_id=content_id,
            name=raw.get("name", content_id),
            category="residence",
            tier=int(raw.get("tier", 1) or 1),
            price=int(raw.get("rent_per_day", 0) or 0),
            emoji=raw.get("emoji", "🏠"),
            actions=("reside",),
            extra=tuple((k, v) for k, v in raw.items() if k not in {
                "name", "tier", "rent_per_day", "emoji", "_comment",
            }),
        )

    def _make_entertainment_def(self, content_id: str, raw: dict) -> ContentDef:
        return ContentDef(
            content_type="entertainment",
            content_id=content_id,
            name=raw.get("name", content_id),
            category="entertainment",
            tier=int(raw.get("tier", 1) or 1),
            price=int(raw.get("price_per_hour", raw.get("price", 0)) or 0),
            emoji=raw.get("emoji", "🎮"),
            actions=("entertain",),
            extra=tuple((k, v) for k, v in raw.items() if k not in {
                "name", "tier", "price", "price_per_hour", "emoji", "_comment",
            }),
        )

    # ============================================================
    # 索引 (by_action / by_name)
    # ============================================================

    def _build_indexes(self) -> None:
        all_defs: List[ContentDef] = []
        all_defs.extend(self._items.values())
        all_defs.extend(self._fish.values())
        all_defs.extend(self._courses.values())
        all_defs.extend(self._jobs.values())
        all_defs.extend(self._residences.values())
        all_defs.extend(self._entertainments.values())

        for d in all_defs:
            self._by_name[d.name] = d
            for a in d.actions:
                self._by_action.setdefault(a, []).append(d)

    # ============================================================
    # 查询 API
    # ============================================================

    def find_by_id(self, content_id: str, content_type: str = "") -> Optional[ContentDef]:
        """按 id 精确查。content_type 不传则全表扫。"""
        if content_type:
            table = self._table_for_type(content_type)
            return table.get(content_id) if table else None
        # 全表扫
        for table in [self._items, self._fish, self._courses, self._jobs,
                      self._residences, self._entertainments]:
            if content_id in table:
                return table[content_id]
        return None

    def find_by_name(self, name: str) -> Optional[ContentDef]:
        """按中文名查 (LLM 工具模糊匹配用)。"""
        return self._by_name.get(name)

    def _table_for_type(self, content_type: str) -> Optional[Dict[str, ContentDef]]:
        return {
            "item": self._items,
            "fish": self._fish,
            "course": self._courses,
            "job": self._jobs,
            "residence": self._residences,
            "entertainment": self._entertainments,
        }.get(content_type)

    def supports_action(self, content_id: str, action: str) -> bool:
        """该内容是否支持某操作 (替代散落的 if/elif 链)。"""
        d = self.find_by_id(content_id)
        return d is not None and action in d.actions

    def filter_by_action(self, action: str, content_type: str = "") -> List[ContentDef]:
        """查所有支持某操作的内容 (LLM '我能吃什么' 常用)。"""
        if not content_type:
            return list(self._by_action.get(action, []))
        table = self._table_for_type(content_type)
        if not table:
            return []
        return [d for d in table.values() if action in d.actions]

    def get_sellable_items(self) -> List[ContentDef]:
        """返回所有可卖物品 (替代 modules/shop.py:get_sellable_items)。

        包含食物、药品、装备、渔具、鱼 (base_price > 0) 等。
        """
        return self.filter_by_action("sell")

    def get_food_items(self) -> List[ContentDef]:
        """所有食物 (含药品, 都可 eat/use)。"""
        return list(self._foods.values()) + list(self._medicine.values())

    # ============================================================
    # 诊断
    # ============================================================

    @property
    def load_errors(self) -> List[str]:
        return self._load_errors

    def stats(self) -> dict:
        return {
            "items": len(self._items),
            "fish": len(self._fish),
            "foods": len(self._foods),
            "medicine": len(self._medicine),
            "equip": len(self._equip),
            "fishing_gear": len(self._fishing_gear),
            "courses": len(self._courses),
            "jobs": len(self._jobs),
            "residences": len(self._residences),
            "entertainments": len(self._entertainments),
            "load_errors": len(self._load_errors),
        }


# 便捷单例
def get_registry() -> ContentRegistry:
    return ContentRegistry.instance()
