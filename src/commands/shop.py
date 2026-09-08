"""
商店命令 V3 - 卡片渲染版
9/4: 所有输出统一卡片

命令:
  /商店                    - 整合页面 (4 分类各 6 种)
  /商店 <分类>             - 完整列表 (按 tier 排序)
  /买 <物品名> [数量]      - 购买 (独立指令)
  /购买 <物品名> [数量]    - 同 /买
"""
import random

from astrbot.api.event import AstrMessageEvent

from ...modules.shop import (
    format_shop_unified,
    format_shop_category,
    buy_item,
    get_sellable_items,
    get_shop_display_items,
    CATEGORY_NAMES,
    CATEGORY_EMOJI,
    format_effects_short,
    check_unlock_requirements,
)
from ...modules.templates import CardType
from ...modules.item import ITEMS, RARITY_NAMES, rarity_hex  # 9/6: rarity 染色


CATEGORY_ALIASES = {
    "食物": "food", "吃": "food", "食": "food",
    # 9/4晚: 道具栏只收纳 药品 + 附魔券
    "道具": "props", "物": "props",
    "药品": "props", "药": "props", "医疗": "props",
    "附魔": "props", "附魔券": "props", "卷轴": "props",
    "装备": "equip", "装备店": "equip", "服装": "equip",
    # 工具 = 装备类 (slot=tool)
    "工具": "equip", "杂物工具": "equip",
    "渔具": "fishing", "钓鱼": "fishing", "鱼具": "fishing", "钓鱼用品": "fishing",
    "日用品": "daily", "日用": "daily", "百货": "daily",
}

# 次级分类 (subcategory / slot) 中文别名
SUBCATEGORY_ALIASES = {
    # 食物子分类
    "烘焙": "baked", "面包": "baked",
    "饮料": "drink", "饮品": "drink",
    "速食": "instant", "泡面": "instant", "方便面": "instant",
    "套餐": "meal", "正餐": "meal",
    "零食": "snack", "零嘴": "snack",
    "补品": "tonic", "滋补": "tonic",
    "能量饮料": "energy_drink",
    "生鲜": "fresh", "海鲜": "fresh",
    "蛋白": "protein",
    "大餐": "power_meal",
    # 药品子分类
    "止痛药": "painkiller", "止痛": "painkiller", "镇痛": "painkiller",
    "感冒": "cold", "感冒药": "cold",
    "急救": "firstaid", "创可贴": "firstaid",
    "睡眠": "sleep", "安眠": "sleep",
    "胃药": "stomach",
    "补剂": "supplement", "维生素": "supplement",
    # 装备子分类
    "衣服": "clothing", "服装": "clothing", "上衣": "clothing",
    "头部": "head", "帽子": "head",
    "配饰": "accessory", "项链": "neck", "腰带": "waist", "钱包": "accessory",
    "手机": "phone", "数码": "phone", "电子产品": "phone",
    "工具": "tool", "杂物工具": "tool",
    # 渔具子分类 (9/7 全部加 fishing_ 前缀)
    "鱼竿": "fishing_rod", "竿": "fishing_rod", "钓竿": "fishing_rod",
    "鱼线": "fishing_line", "线": "fishing_line", "主线": "fishing_line", "子线": "fishing_line",
    "鱼钩": "fishing_hook", "钩": "fishing_hook", "钓钩": "fishing_hook",
    "鱼饵": "fishing_bait", "饵": "fishing_bait", "饵料": "fishing_bait",
    "拟饵": "fishing_lure", "假饵": "fishing_lure", "鱼形饵": "fishing_lure",
    "浮漂": "fishing_float", "漂": "fishing_float", "浮子": "fishing_float", "漂子": "fishing_float",
    "鱼轮": "fishing_reel", "轮": "fishing_reel", "卷线器": "fishing_reel",
    "涉水裤": "fishing_waders", "钓鱼裤": "fishing_waders", "下水裤": "fishing_waders",
    # 电子 / 数码
    "电子产品": "electronics", "电器": "electronics",
    # 日常
    "电子产品": "electronics", "电器": "electronics",
    "家居": "household", "家用": "household",
    "户外": "outdoor", "露营": "outdoor",
    "个护": "personal", "洗护": "personal",
}

# 稀有度别名
RARITY_ALIASES = {
    "普通": "common", "凡": "common",
    "高级": "uncommon", "绿": "uncommon",
    "稀有": "rare", "蓝": "rare", "珍稀": "rare",
    "史诗": "epic", "紫": "epic", "史诗级": "epic",
    "传说": "legendary", "黄": "legendary", "传奇": "legendary",
    "神话": "mythic", "红": "mythic", "至尊": "mythic",
}


def _resolve_category(arg: str) -> str | None:
    arg_lower = arg.lower()
    if arg in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[arg]
    if arg_lower in ("food", "medicine", "equip", "fishing", "daily"):
        return arg_lower
    return None


def _resolve_subcategory(arg: str) -> str | None:
    """解析次级分类（鱼竿/鱼线/鱼钩/鱼饵...）"""
    if arg in SUBCATEGORY_ALIASES:
        return SUBCATEGORY_ALIASES[arg]
    arg_lower = arg.lower()
    if arg_lower in SUBCATEGORY_ALIASES.values():
        return arg_lower
    return None


def _resolve_rarity(arg: str) -> str | None:
    """解析稀有度"""
    if arg in RARITY_ALIASES:
        return RARITY_ALIASES[arg]
    arg_lower = arg.lower()
    if arg_lower in ("common", "uncommon", "rare", "epic", "legendary", "mythic"):
        return arg_lower
    return None


def _resolve_tier(arg: str) -> int | None:
    """解析 tier: '3', 'T3', 'tier3'"""
    arg_lower = arg.lower()
    if arg_lower.startswith("tier") or arg_lower.startswith("t"):
        try:
            return int(arg_lower.replace("tier", "").replace("t", ""))
        except ValueError:
            return None
    try:
        return int(arg)
    except ValueError:
        return None


def filter_items(items: list, *, category: str = None, subcategory: str = None,
                 tier: int = None, rarity: str = None, user: dict = None) -> list:
    """通用筛选器: 按 category / subcategory / tier / rarity 过滤 + 解锁条件

    Args:
        items: [(item_id, item_info), ...]
        category: food/medicine/equip/fishing/daily/None
        subcategory: fishing_rod/line/hook/.../None
        tier: 1-6 / None
        rarity: common/uncommon/rare/epic/legendary/mythic / None
        user: 用于解锁过滤
    """
    result = []
    for iid, info in items:
        if not isinstance(info, dict):
            continue
        # 1. category 过滤（用 _classify_item）
        if category:
            from ...modules.shop import _classify_item
            if _classify_item(info) != category:
                continue
        # 2. subcategory 过滤 (匹配 subcategory 或 slot)
        if subcategory:
            if info.get("subcategory") != subcategory and info.get("slot") != subcategory:
                continue
        # 3. tier 过滤
        if tier is not None:
            if info.get("tier", 1) != tier:
                continue
        # 4. rarity 过滤
        if rarity:
            if info.get("rarity") != rarity:
                continue
        # 5. 解锁过滤
        if user:
            unlocked, _ = check_unlock_requirements(user, info)
            if not unlocked:
                continue
        result.append((iid, info))
    return result


_RARITY_DOT = {"common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "mythic": "🔴"}


def _item_to_card(item_id: str, item_info: dict, user: dict) -> dict:
    rarity = item_info.get("rarity", "common")
    # 9/7: ContentRegistry 把 description/type/unlock_requirements 存在 extra 子 dict,
    #       必须先扁平化才能让模板拿到
    extra = item_info.get("extra", {}) if isinstance(item_info.get("extra"), dict) else {}
    effects = item_info.get("effects") or extra.get("effects") or {}
    description = item_info.get("description") or extra.get("description") or ""
    item_type = item_info.get("type") or extra.get("type") or item_info.get("subcategory", "物品")
    price = item_info.get("price", 0)
    user_gold = int(user.get("gold", 0))
    # 金币不足则锁住
    locked = price > 0 and user_gold < price
    # 解锁条件
    unlocked, unlock_reason = check_unlock_requirements(user, item_info)
    return {
        "item_id": item_id,
        "name": item_info.get("name", item_id),
        "emoji": item_info.get("emoji", "📦"),
        "price": price,
        "tier": item_info.get("tier", 1),
        "rarity": rarity,
        "rarity_dot": _RARITY_DOT.get(rarity, "⚪"),
        "rarity_color": rarity_hex(rarity),  # 9/6: UI hex 颜色
        "rarity_cn": RARITY_NAMES.get(rarity, ""),  # 9/6: 中文标签
        "type": item_type,
        "description": description,
        "effects_text": format_effects_short(effects, max_len=70),
        "locked": locked or not unlocked,
        "unlock_reason": unlock_reason if not unlocked else "",
    }


async def run_shop_logic(event: AstrMessageEvent, store, parser, sender, plugin=None):
    """商店命令逻辑 V3 - 卡片渲染.

    9/6: 改用 sender.send_card() 替代 2 处 try/except + renderer.render_shop(...) 样板。
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    _, args = parser.parse(event)

    # 无参数: 整合页面
    if not args:
        # 9/4: 先过滤未解锁, 再随机 6 件 (保证 6 件)
        all_groups = get_sellable_items()
        categories = []
        for cat_key in ["food", "props", "equip", "fishing"]:
            items = all_groups.get(cat_key, [])
            if user:
                items = [
                    (iid, info) for iid, info in items
                    if check_unlock_requirements(user, info)[0]
                ]
            if not items:
                continue
            # 随机 6 件 (不够就全显示)
            sample = items if len(items) <= 6 else random.sample(items, 6)
            categories.append({
                "key": cat_key,
                "name": CATEGORY_NAMES.get(cat_key, cat_key),
                "emoji": CATEGORY_EMOJI.get(cat_key, "📦"),
                "item_list": [_item_to_card(iid, info, user) for iid, info in sample],
            })
        # 9/6: 改用 sender.send_card() (CardType.SHOP 渲染模板)
        data = {
            "user_id": str(event.get_sender_id()),
            "nickname": user.get("nickname", "未知"),
            "gold": int(user.get("gold", 0)),
            "shop_name": "商店",
            "section_title": "商店",
            "categories": categories,
        }
        async for r in sender.send_card(
            event, CardType.SHOP, data,
            fallback_text=format_shop_unified(plugin, user),
        ):
            yield r
        return

    sub_cmd = args[0]
    sub_args = args[1:]  # 剩余参数 (tier / rarity / etc.)

    # /商店 列表 - 列出所有可用筛选维度
    if sub_cmd in ("列表", "分类", "list", "help"):
        lines = ["📋 商店筛选指令:\n"]
        lines.append("大类: 食物 / 道具 / 装备 / 渔具 / 日用品")
        lines.append("次类: 鱼竿 / 鱼线 / 鱼钩 / 鱼饵 / 拟饵 / 浮漂 / 鱼轮 / 涉水裤")
        lines.append("      衣服 / 头部 / 配饰 / 手机 / 工具")
        lines.append("      烘焙 / 饮料 / 速食 / 套餐 / 零食 / 补品")
        lines.append("      止痛药 / 感冒药 / 急救 / 睡眠 / 胃药")
        lines.append("\n按 tier: tier 3 / tier 5")
        lines.append("按稀有: 传说 / 史诗 / 稀有")
        lines.append("\n复合: /商店 鱼竿 tier 3")
        lines.append("      /商店 装备 传说")
        lines.append("      /商店 鱼线 tier 4 5")
        yield event.plain_result("\n".join(lines))
        return

    # /商店 买
    if sub_cmd == "买" or sub_cmd == "购买":
        if len(args) < 2:
            yield event.plain_result("📋 格式: /商店 买 <物品名> [数量]\n例: /商店 买 蚯蚓 10")
            return
        item_name = args[1]
        quantity = 1
        if len(args) > 2:
            try:
                quantity = int(args[2])
                if quantity <= 0:
                    yield event.plain_result("❌ 数量必须 > 0")
                    return
            except ValueError:
                yield event.plain_result(f"❌ 无效数量: {args[2]}")
                return
        item_id = None
        for iid, item in ITEMS.items():
            if not isinstance(item, dict):
                continue
            if item.get("name") == item_name or iid == item_name:
                item_id = iid
                break
        if not item_id:
            yield event.plain_result(f"❌ 找不到物品: {item_name}")
            return
        success, msg = buy_item(plugin, user, item_id, quantity)
        if success:
            await store.update_user(user_id, user)
        yield event.plain_result(msg)
        return

    # /商店 <筛选1> [筛选2] [...] - 多维筛选
    # 解析 sub_cmd 和 sub_args
    filters = {}
    filter_args = [sub_cmd] + sub_args
    page_title = "商店"
    for arg in filter_args:
        # 跳过空
        if not arg:
            continue
        # tier 关键字
        if arg.lower() in ("tier", "t"):
            continue
        # 数字 (可能是 tier)
        if arg.isdigit():
            t = _resolve_tier(arg)
            if t and "tier" not in filters:
                filters["tier"] = t
                continue
        # tierX / TX
        if arg.lower().startswith(("tier", "t")) and arg[1:].isdigit() if arg[0].lower() == "t" else False:
            t = _resolve_tier(arg)
            if t and "tier" not in filters:
                filters["tier"] = t
                continue
        # category
        cat = _resolve_category(arg)
        if cat and "category" not in filters:
            filters["category"] = cat
            page_title = CATEGORY_NAMES.get(cat, cat)
            continue
        # subcategory
        sub = _resolve_subcategory(arg)
        if sub and "subcategory" not in filters:
            filters["subcategory"] = sub
            page_title = arg
            continue
        # rarity
        rar = _resolve_rarity(arg)
        if rar and "rarity" not in filters:
            filters["rarity"] = rar
            page_title = f"{arg}级物品"
            continue

    if not filters:
        # /商店 <未识别> - 提示帮助
        yield event.plain_result(
            f"❌ 未识别指令: /商店 {sub_cmd}\n"
            "用法:\n"
            "  /商店            - 整合页面\n"
            "  /商店 <大类>     - 食物/药品/装备/渔具/日用品\n"
            "  /商店 <次类>     - 鱼竿/鱼线/鱼钩/鱼饵/拟饵/...\n"
            "  /商店 tier <N>   - 按 tier 筛选\n"
            "  /商店 <稀有度>   - 普通/高级/稀有/史诗/传说/神话\n"
            "  /商店 <次类> tier 3 - 复合筛选\n"
            "  /商店 列表       - 查看所有筛选维度\n"
            "  /买 <物品名>     - 购买"
        )
        return

    # 应用筛选
    all_items = []
    for items in get_sellable_items().values():
        all_items.extend(items)
    filtered = filter_items(all_items, user=user, **filters)

    if not filtered:
        yield event.plain_result(
            f"📋 {page_title} 没有匹配物品 (未解锁或无此分类)\n"
            "提示: 用 /商店 列表 查看可用筛选"
        )
        return

    # 9/7 重构: 按 subcategory 分栏 + 每栏按 rarity 降序
    RARITY_ORDER = {"mythic": 6, "legendary": 5, "epic": 4, "rare": 3, "uncommon": 2, "common": 1}
    SUBCAT_NAME = {
        "fishing_rod": "🎣 鱼竿",
        "fishing_line": "🪢 鱼线",
        "fishing_hook": "🪝 鱼钩",
        "fishing_bait": "🪱 鱼饵",
        "fishing_lure": "🎏 拟饵",
        "fishing_float": "🟡 浮漂",
        "fishing_reel": "🎡 鱼轮",
        "fishing_waders": "👖 涉水裤",
        "baked": "🥖 烘焙",
        "drink": "🥤 饮料",
        "instant": "🍜 速食",
        "meal": "🍱 套餐",
        "snack": "🍪 零食",
        "tonic": "💊 补品",
        "energy_drink": "⚡ 能量饮料",
        "fresh": "🐟 生鲜",
        "protein": "🥩 蛋白",
        "power_meal": "🍲 大餐",
        "painkiller": "💊 止痛药",
        "cold": "🤧 感冒药",
        "firstaid": "🩹 急救",
        "sleep": "🌙 睡眠药",
        "stomach": "💊 胃药",
        "supplement": "💊 补剂",
        "clothing": "👕 衣服",
        "head": "🎩 头部",
        "accessory": "💍 配饰",
        "neck": "📿 项链",
        "waist": "👔 腰带",
        "phone": "📱 手机",
        "tool": "🔧 工具",
        "household": "🏠 家居",
        "outdoor": "⛰️ 户外",
        "personal": "🧴 个护",
        "electronics": "🔌 电子产品",
    }

    # 按 subcategory 分组
    by_subcat = {}
    for item_id, item in filtered:
        subcat = item.get("subcategory", "其他")
        by_subcat.setdefault(subcat, []).append((item_id, item))

    subcat_groups = []
    for subcat, items_in_sub in by_subcat.items():
        # 每栏按 rarity 降序 + 同稀有度按 price 升
        items_sorted = sorted(
            items_in_sub,
            key=lambda x: (-RARITY_ORDER.get(x[1].get("rarity", "common"), 0), x[1].get("price", 0)),
        )
        subcat_groups.append({
            "subcategory": subcat,
            "subcategory_name": SUBCAT_NAME.get(subcat, subcat),
            "item_list": [_item_to_card(iid, info, user) for iid, info in items_sorted],
        })
    # subcategory 按 item 数降序（多的在前）
    subcat_groups.sort(key=lambda g: -len(g["item_list"]))

    # 9/7: 改用 sender.send_card() (subcat_groups 模式 + rarity 降序)
    data = {
        "user_id": str(event.get_sender_id()),
        "nickname": user.get("nickname", "未知"),
        "gold": int(user.get("gold", 0)),
        "shop_name": str(page_title),
        "section_title": page_title,
        "subcat_groups": subcat_groups,
    }
    async for r in sender.send_card(
        event, CardType.SHOP, data,
        fallback_text=format_shop_category(None, plugin, user, subcat_groups, page_title),
    ):
        yield r
    return


async def run_buy_logic(event: AstrMessageEvent, store, parser, plugin=None):
    """独立购买指令 V2 - 9/4: 加解锁条件检查 + 写完整 inventory 字段

    用法:
      /买 蚯蚓 10
      /购买 碳素竿
      /买 泡面
    """
    user_id = str(event.get_sender_id())
    user = await store.get_user(user_id)

    if not user:
        yield event.plain_result("📋 你还没有注册！\n先输入 /签到 注册")
        return

    _, args = parser.parse(event)

    if not args:
        yield event.plain_result(
            "📋 /买 用法:\n"
            "  /买 <物品名> [数量]\n"
            "  /购买 <物品名> [数量]\n"
            "  例: /买 蚯蚓 10\n"
            "  例: /买 碳素竿"
        )
        return

    item_name = args[0]
    quantity = 1
    if len(args) > 1:
        try:
            quantity = int(args[1])
            if quantity <= 0:
                yield event.plain_result("❌ 数量必须 > 0")
                return
        except ValueError:
            yield event.plain_result(f"❌ 无效数量: {args[1]}")
            return

    # 找物品
    item_id = None
    for iid, item in ITEMS.items():
        if not isinstance(item, dict):
            continue
        if item.get("name") == item_name or iid == item_name:
            item_id = iid
            break

    if not item_id:
        yield event.plain_result(
            f"❌ 找不到物品: {item_name}\n"
            f"提示: 用 /商店 查看可购买商品"
        )
        return

    # 1. 解锁条件检查 (9/4 新增)
    item_info = ITEMS[item_id]
    unlocked, unlock_reason = check_unlock_requirements(user, item_info)
    if not unlocked:
        yield event.plain_result(
            f"🔒 {item_info.get('name', item_id)} 未解锁\n"
            f"  原因: {unlock_reason}\n"
            f"  提示: 提升对应能力后再来购买"
        )
        return

    # 2. 购买 (含金币检查)
    success, msg = buy_item(plugin, user, item_id, quantity)
    if success:
        await store.update_user(user_id, user)
    yield event.plain_result(msg)
