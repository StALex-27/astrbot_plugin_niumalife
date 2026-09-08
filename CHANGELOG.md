# Changelog

> 所有重要修改一行记录：日期 / 类型标签 / 文件 / 一句话。
> 调试时优先 grep CHANGELOG 而非全源码。

格式：
```
## YYYY-MM-DD
- [Tag] file:path — 摘要
```

## 2026-09-08 (v0.1.10 — 钓鱼系统深度重构 + 视觉升级)

### 钓鱼机制
- [Fix] `src/fishing/fishing_manager.py` — 估价公式重构: 移除 `size_factor` 和 `skill_value`, 改为 `base_price × rarity_mult × weight_bonus × (1 + price_bonus_pct/100)`, `weight_bonus = 1 + clamp((weight - median) / median, -0.1, 0.1)`
- [Add] `src/fishing/fishing_manager.py` — `get_fishing_skill_progress(user) → {level, current_exp, next_level_exp, is_max}` 钓鱼技能进度查询
- [Add] `src/fishing/fishing_manager.py` — `SIZE_CLASS_AVG_WEIGHT` + `calc_break_risk_from_hook(hook_effects, rod_max, line_max)` 断竿/断线风险评估
- [Add] `src/fishing/fishing_manager.py` — `format_weight()` 5 档紧凑格式 (g/kg/t)
- [Add] `src/fishing/fishing_manager.py` — `format_length_compact()` 5 档紧凑格式 (mm/cm/m), `0cm/0.05cm` 兜底 `1mm`
- [Fix] `modules/renderer.py:1061` — 中鱼通知 rarity 优先用 `catch["rarity"]` (升档后) 而非 `fish["rarity"]` (基础)
- [Fix] `modules/renderer.py:1062` — `rarity_cn` 映射表补 `mythic: "神话"`, 修复所有神话鱼显示"常见"bug
- [Fix] `src/fishing/fishing_manager.py:apply_catch` — inventory entry 写入时存 `final_rarity` + `base_rarity` + `boost_tier` 字段
- [Fix] `src/market/__init__.py:calc_sell_price` — 售价 = 估价 (无波动, 无 base 字段依赖), 完全按鱼名 + 库存鱼 final_rarity + 实际 weight 计算

### 钓鱼视觉
- [Refactor] `modules/templates.py:FISHING_SPOTS` — 模板重写: 6 渔具栏 3x2 网格 / 右上角正方形圆角等级方框含 exp 进度条 / 标题栏下方显示钓鱼称号 / 钓鱼中显示进度条 + ticks
- [Refactor] `modules/templates.py` — 水域卡 2 列布局: emoji 在上/名称在下居中, 解锁等级和入场费分两行展示
- [Refactor] `src/commands/fishing.py:run_fishing_show_spots_logic` — 6 渔具解析 (竿/线/轮/漂/钩/饵) + 风险提示 (按鱼钩 size_class 范围) + 钓鱼称号 + 缺装备警告 + 钓鱼状态条
- [Refactor] `src/commands/fishing.py` — 钓鱼中也走渲染卡片 (`run_fishing_show_spots_logic`), 失败时 fallback 文本含 exp + 渔具 + 进度
- [Refactor] `src/commands/fishing.py:run_fishing_start_logic` — 加解锁等级严格检查 (按玩家钓鱼等级)

### 鱼池生态
- [Refactor] `data/config/fishes.json` — 8 水域各 2-3 条特色鱼 (legendary/mythic 限 1 水域 habitat 独占)
  - 村口池塘: 月牙银鱼 + 黄金锦鲤 + 金鳞鲤幼体
  - 林间小溪: 凤尾小鲈 + 龙须溪哥 + 凤尾马口
  - 山区水库: 蛟龙 + 鳡鱼王 + 炎鳞兽幼体
  - 平原河流: 龙鳞青鳉 + 龙鲤成体 + 渊鳡
  - 大型湖泊: 墨麒麟幼体+半成+成体
  - 近海港口: 赤鲟 + 苍鳞鲟王 + 巨骨鲱
  - 远洋深海: 荧光水母鱼 + 龙趸 + 深渊巨妖
  - 深渊海沟: 海皇波塞冬 + 旧日支配者 + 深渊母皇
- [Refactor] `data/config/fishes.json` — 大鲶鱼系按系列限 2 水域
  - 玄鳞鲶系 (4 条) → 水库+河流
  - 雷龙鲶系 (3 条) → 湖泊+水库
  - 金鳇系 (3 条) → 近海+河流
  - 炎鳞系 (2 条) → 深海+近海
  - 蓝龙鲶 (1 条) → 湖泊+河流
- [Refactor] `data/config/fishes.json` — 删除 40 件鱼饵/拟饵的 `base_effects.habitat_filter` (水域加成已废除)
- [Refactor] `data/config/items.json` — 删除 29 件鱼竿的 `habitat_pond/river/reservoir/creek/lake/nearshore/deepsea/ocean` 字段
- [Refactor] `data/config/items.json` — 删除 2 条涉水鞋 (普通胶鞋 + 矶钓鞋) — 子类废弃

### 验证
- [Verified] `tests/test_item_detail.py` 16/16 通过
- [Verified] AstrBot PID 762269 启动成功, 0 errors
- [Verified] 各水域 rarity 概率 (全鱼池): 村口 82.1% / 山区水库 68.8% / 大型湖泊 32.1% / 深渊海沟 26.8%
- [Verified] 各水域 mythic 条件概率: 村口 0.12% → 深渊海沟 1.27% (10.6 倍)
- [Verified] 断线/断竿风险按超载比例分级: 无 ≤ 0 / 低 ≤ 10% / 中 ≤ 20% / 高 ≤ 30% / 极高 > 30%
- [Verified] 中鱼通知标题含鱼名 + 紧凑重量 + 紧凑尺寸

## 2026-09-06 (基础设施 + 通知机制重构 + 15 命令渐进应用)
- [Add] `src/ui/message_sender.py` (520 行) — MessageSender 类, 3 入口: `send_card()` / `send_text()` / `notify()`
- [Add] `src/data/user_view.py` (325 行) — UserView 访问层, 30+ typed accessor + 4 个 view_for_card (profile/fish_dex/fishing_gear/backpack)
- [Add] `src/data/content_registry.py` (535 行) — ContentRegistry 单例, 405 项统一注册 + actions 自动推导
- [Add] `tests/test_message_sender.py` (557 行, 21 测试) / `tests/test_user_view.py` (324 行, 17 测试) / `tests/test_content_registry.py` (223 行, 25 测试)
- [Refactor] `modules/messenger.py` — 委派 sender, 缓存键适配 (session_key 分组)
- [Refactor] `main.py` — `_cache_event` 改 session_key 索引 + 删 1h 过期 + 初始化 `self._sender = MessageSender(self)`
- [Refactor] `main.py llm_view_fish_dex` — 3 处嵌套访问改 UserView (`get_fish_caught / get_biggest_catch / get_fish_title`)
- [Refactor] `main.py` 14 个 LLM tool — 补 `Returns: dict: {status, last_text, _sender}` 段 (Google-style docstring)
- [Refactor] `modules/renderer.py` — 加 `ViewSpec` class + `VIEW_SPECS` dict (14 CardType) + `_render` 入口 `apply_defaults` + `check_required`
- [Refactor] `modules/shop.py:get_sellable_items` — 改用 `ContentRegistry.instance().filter_by_action("sell")` 替代遍历 ITEMS dict
- [Fix] `modules/tick.py` — 取消 1h 过期保护, 玩家发指令去忙/睡 4h+ tick 完成通知仍能送达 (此前 1h 后会跳过)
- [Fix] 缓存按 session_key 分组 — 群 A 钓鱼 + 群 B 闲聊不再覆盖, 鱼通知正确发到原发起会话
- [Fix] `from ..data.content_registry` 路径错 — 改为 `from ..src.data.content_registry` (runtime 相对 import)
- [Refactor] 15 个命令改用 MessageSender.send_card() 替代 try/except 样板:
  - profile / help / sell (5处) / fish (2处) / cancel / residence / complete_job / stock (3处) / shop (2处) / learn / enchant / backpack / entertain / work (3处) / fishing_gear
  - 累计消除 **26 处 try/except 样板**
- [Refactor] ViewSpec 应用: `profile` + `fish_dex` + `backpack` + `fishing_gear` 用 `view_for_xxx_card(user)` 拿齐 data
- [Refactor] UserView 应用: `main.py:llm_view_fish_dex` (3处) + `src/commands/fishing.py:run_fish_dex_logic` (3处) + `src/commands/fishing.py:run_fishing_show_spots_logic`
- [Add] 持久化目录 `/home/alex/data/niumalife_cache/notify_imgs/` — MessageChain 持久化 (B+C 方案)
- [Refactor] `_format_delay` — 5 档模糊化 (数分钟/半小时/数小时/半天/> 24h 不发)
- [Add] `_pending_notify:{user_id}` KV 持久化 — 存活 24h, 玩家进该 session 时由 `_flush_pending_for_session` 兜底
- [Refactor] `src/ui/message_sender.py:send_card` — 加 `render_timeout` 参数 (Optional[float]), `asyncio.wait_for` 套渲染调用, 保留 checkin 的 30s 超时保护
- [Refactor] `checkin` 命令改用 sender.send_card() — 2 处 try/except 消除 (success + already_checked 分支), 累计 16 个命令应用 sender
- [Add] `tests/test_view_specs.py` 加 8 个 per-CardType 测试 (profile/status/checkin/shop/backpack/fishing_gear/sell_overview/help) — 14 测试全过
- [Fix] `modules/renderer.py` FISHING_GEAR ViewSpec 补 6 字段 (capacity_combined_max/diet_zh/gear_slots/effects/inventory_gear/equipped_count) — 测试发现真 bug, 渲染该卡会失败
- [Add] `src/data/user_view.py` 新增 `get_setting()` + `ensure_settings_defaults()` + `_DEFAULT_SETTINGS` — 老玩家 settings 自动补默认 (notification_enabled=False opt-in / sub_group_daily=True / auto_fish_check=True / sell_confirm_threshold=1000), `setdefault` 语义不覆盖显式设置
- [Add] `tests/test_user_view.py` 加 3 个 settings 测试 (ensure_settings_defaults_fills_missing / preserves_existing / get_setting_returns_default_for_missing_key)
- [Verified] **99/99 单元测试全过** (market 12 + llm_tool 7 + view_specs 14 + user_view 20 + content_registry 25 + message_sender 21)
- [Verified] AstrBot 4.27.5 PID 380326 存活, 0 errors, plugin 加载成功
- [Fix] **连接池泄漏 bug** —— `src/commands/profile.py` 漏改 import 路径 (2点 → 3点 `from ...modules` / `from ...data.user_view`), 导致 `profile` 命令每次都 `ImportError`, 异常 handler 漏关 SQLAlchemy session, 触发 `QueuePool limit of size 5 overflow 10 reached` 雪崩, 玩家 `/档案` / `/签到` 全失败 + 所有 `[notify] 读 KV` 30s 超时. 9/6 18:50 修复, 修复后 0 QueuePool 错误.
- [Fix] **`profile.py` 引用不存在的常量 `DEBUFFS`** → 正确是 `DEBUFF_DEFINITIONS`. 修复后 debuff 列表正常显示

## 2026-09-03 (LLM Tools — 牛马机器人工具化, 安全加固)
- [Add] `src/llm_tools/game_tools.py` + `__init__.py` —— 6 个 LLM 可调用的游戏数据工具
  - `get_player_status` / `get_player_skills` / `get_fishing_records` (按重量/时间/稀有度排序) / `get_inventory_summary` (按类别筛选)
  - `preview_sell` (只读预览) + `execute_sell` (真实执行, 玩家明确同意后调用)
- [Add] `main.py` 6 个 `@filter.llm_tool` 装饰方法 + `initialize()` 调 `register_game_tools(self)`
- [Add] `main.py` `_get_sender_context` + `_wrap_with_sender` —— 所有工具返回都带 `_sender` 字段
- [Fix] `main.py llm_execute_sell` —— **9/3 严重 BUG 修复**: market.sell_items 不会改 user.gold, 工具现在手动 `user.gold += total`
- [Fix] `main.py llm_execute_sell` —— 安全检查: 拒绝代其他玩家执行 (`target_user_id != event.get_sender_id()` 时 return error)
- [Fix] `main.py llm_execute_sell` —— 主动用 `event.send(MessageChain)` 给真人发确认消息
- [Add] `tests/test_game_tools.py` —— 14 个单元测试 (14/14 通过), 含 BUG 回归测试
- [Decision] LLM Tools 设计: 智能确认分流 = `preview_sell` (LLM 推测) → LLM 自己组织确认文本 → 玩家答"是" → `execute_sell` (真实执行). 玩家明确命令时直接调 execute_sell.
- [Decision] 工具签名: `async def xxx(self, event: AstrMessageEvent, ...) -> dict`. 必须返回 dict 不能 yield (LLM tool 限制). user_id 从 `_get_sender_context(event)` 取, 不直接 `event.get_sender_id()`.
- [Decision] 身份安全: 写入工具强制 `target_user_id` 参数, 工具内验证等于 `_sender.user_id` 才执行. 9/3 群聊乌龙 (熊发消息但 LLM 把鱼板面卖了) 的根因修复.
- [Pending] WebUI → 丽贝卡 persona 编辑, 加工具使用规则 prompt → `/home/alex/niumalife_rebecca/REBECCA_PROMPT.md` 已更新含身份安全规则

## 2026-09-03 (LLM Tools — 全量功能指令接入)
- [Add] `main.py` 新增 12 个 `do_xxx` 写入工具: do_checkin / do_cancel / do_work / do_learn / do_entertain / do_eat / do_residence / do_equip / do_complete_job / do_cancel_job / do_fishing_start / do_settings
- [Add] `main.py _check_write_permission()` —— 统一身份验证, 所有 do_xxx 工具统一调用
- [Add] `main.py _run_command_for_llm()` —— 通用 LLM tool helper, 把 run_xxx_logic 的 yield 转 event.send 主动发出去
- [Add] `main.py _send_image_to_user()` —— view_xxx 工具发图通用方法 (处理 url_image/file_image 分支)
- [Decision] 写入工具统一签名 `(event, ...业务参数, target_user_id: str = "")` —— 强制 target_user_id == _sender.user_id
- [Decision] LLM tool 不能 yield, 采用"临时替换 event.message_str + 复用 run_xxx_logic + event.send 转 yield"模式, 无需重构业务代码
- [Fixed] 所有 do_xxx 工具的 Args 文档必须带 `(string)`/`(number)` 类型标记, 否则 AstrBot 装饰器拒绝加载 (曾导致整个 plugin 加载失败)

## 2026-09-03 (买食物 + 吃 工作流修复)
- [BugFix] 9/3 session: 玩家说"买点吃的恢复饱食度"时丽贝卡无法获取相关食物信息
- [RootCause] 缺 `do_buy_shop_item` 工具 (商店买物品), `view_shop` 没返回 foods effects, `get_inventory_summary` 没返回食物效果
- [Fix] `main.py` 新增 `do_buy_shop_item(item_name, quantity, target_user_id)` —— 复用 run_shop_logic, 构造 "商店 买 X N" 命令
- [Fix] `main.py view_shop` 重写为结构化返回: 每件商品含 effects + effect_summary (中文效果描述), food 排序在前
- [Fix] `main.py view_shop` 顶部模块级 `_format_food_effects_zh()` helper —— satiety→饱食度, health→健康 等中文化
- [Fix] `src/llm_tools/game_tools.py _tool_get_inventory_summary` 对食物附加 effects 字段 (查 ITEMS)
- [Doc] `niumalife_rebecca/REBECCA_PROMPT.md` 加 "买食物 + 吃 完整工作流" 5 步流程图, 强调必须等玩家确认再扣钱

## 2026-09-03 (do_buy_shop_item 重写, 绕开 run_shop_logic bug)
- [BugFix] 9/3 session: `do_buy_shop_item` 报错 `buy_item() missing 1 required positional argument: 'item_id'`
- [RootCause] `run_shop_logic` (line 265) 调 `buy_item(user, item_id, quantity)` 缺 `plugin` 和 `shop_id` 参数. `buy_item` 真实签名是 `(plugin, user, shop_id, item_id, quantity)`. 这是 `run_shop_logic` 的历史 BUG, 一直未修复.
- [Fix] `main.py llm_do_buy_shop_item` 重写: 绕开 run_shop_logic, 直接调 buy_item (传 5 个参数) + 主动发 @真人 确认消息 + 错误信息中文化
- [Fix] 验证金币先于调用 buy_item, 避免 buy_item 内部扣金币失败时数据不一致
- [Pending] `src/commands/shop.py:265` 也要修, 但这是已有 BUG (群里 /商店 买 也受影响), LLM 工具先独立绕过

## 2026-09-03 (item_id 显式传递, 修复 LLM 模糊匹配失败)
- [BugFix] 9/3 session: LLM 调 do_buy_shop_item(item_name="止痛药") 找不到 item, 因为 view_shop 没返回明确的 item_id 字段
- [Fix] `main.py view_shop` 每件商品加 `item_id` 显式字段 (保留 `id` alias 兼容)
- [Fix] `src/llm_tools/game_tools.py _tool_get_inventory_summary` 背包物品也加 `item_id` 字段
- [Fix] `main.py do_buy_shop_item` 加 `item_id` 参数, 优先用 item_id 精确匹配 ITEMS 字典 key, item_name 仅作 fallback 模糊匹配
- [Doc] REBECCA_PROMPT.md "买 + 吃 工作流" 第 1 步强调 "item_id 必传", 加 "item_id vs item_name 关键区分" 段落

## 2026-09-03 (buy_item UnboundLocalError 修复)
- [BugFix] 9/3 session: 群聊 `/商店 买 止痛药` 和 LLM do_buy_shop_item 都报 `cannot access local variable 'slot' where it is not associated with a value`
- [RootCause] `modules/shop.py:416` buy_item return msg 那行用了 `slot` 局部变量, 但 `slot` 只在 `if slot:` (line 389) 分支里赋值. 无 slot 的物品 (food/medicine) 抛 UnboundLocalError
- [Fix] `modules/shop.py:416` 改用 `item.get("slot")` 安全取值, 避免依赖可能未赋值的 `slot` 变量
- [Impact] 同时修复群聊 `/商店 买` 路径 (之前 buy_item 抛异常被吞 + line 261-268 手算金币 = 用户感觉"成功"但物品没加背包的幽灵 bug)

## 2026-09-03 (药品 + 食物 都能 do_eat)
- [BugFix] 9/3 session: 买止痛药成功, 但 do_eat(food_name="止痛药") 失败 — `_find_inventory_food` 只接受 type in ("fish","food","item")
- [RootCause] buy_item 把物品加背包时**没存 category/type 字段**, 药品和食物区分不出来. run_eat_logic 内部的查找过滤条件 `type in ("fish","food","item")` 也只接受这 3 种
- [Fix] `modules/shop.py:378` buy_item 新增背包项时存 `category / type / effects` 字段
- [Fix] `src/commands/food.py:_find_inventory_food` 和 `_eat_inventory_item` 过滤加 `category in ("food","medicine")` 白名单
- [Verifiy] 止痛药 effects {health:20} 走 food.py:295 else 分支, 调 `_apply_food_effects(attrs, health=20)` 直接生效
- [Doc] REBECCA_PROMPT.md 加 "food vs medicine 关键区分" 段落: 两者都走 do_eat, 药品 effects 直接 apply attributes.health

## 2026-09-03 (旧 inventory 数据缺 category 字段, 历史包袱修复)
- [BugFix] 9/3 session: LLM 买止痛药成功, 但 do_eat 找不到 — 玩家现有 inventory item `{id, name, quantity}` 缺 `category/type/effects` 字段 (旧 buy_item 没存)
- [RootCause] 1. 用户 9/3 之前用群聊 `/商店 买 止痛药` 买的, 那时 buy_item 只存 `{id, name, quantity}`. 2. LLM 买的走 `stackable=True` 堆叠分支, `quantity+=1` 不补字段. 3. _find_inventory_food 之前不反查 ITEMS 字典, 所以找不到
- [Fix] `modules/shop.py:373` 堆叠分支顺手补 category/type/effects 字段
- [Fix] `src/commands/food.py:_find_inventory_food` 和 line 251 _eat_inventory_item 兜底: 反查 ITEMS 字典拿 category/type
- [Fix] 手动 SQL UPDATE 把 748455427 用户的旧止痛药补上 category=medicine / effects={health:20}
- [Impact] 修复后, 旧数据即使没补字段也能 do_eat (兜底逻辑)

## 2026-09-04 凌晨 (商店卡片渲染 BUG 修复: Jinja2 字段名冲突)
- [Bug] LocalRenderer 渲染时报 `TypeError: 'builtin_function_or_method' object is not iterable`
- [RootCause] SHOP 模板用 `cat.items` 迭代, 但 `cat` 是 dict, `dict.items` 是内置方法而非列表
  - Jinja2 在 `{% for x in dict.items %}` 会拿到 method 对象, 报 not iterable
- [Fix] 重命名字段:
  - `cat.items` → `cat.item_list`
  - `group.items` → `group.item_list`
- [Fix] 模板加固:
  - `{% if x %}` → `{% if x and x|length > 0 %}` (避免空 dict 误判)
  - `{% if tier_groups %}` 外加 length 检查
- [Impact] src/commands/shop.py 同步改 item_list 字段
- [Verify] Jinja2 测试两种模式均渲染成功

## 2026-09-04 凌晨 (商店 V3.1 卡片化: 整合页面 + 单分类页面均输出卡片)
- [Impact] modules/templates.py SHOP 模板重写:
  - 旧模板: 固定/随机商品列表 (list-item 横向布局)
  - 新模板: 支持 2 种渲染模式
    - **整合模式** (`categories`): 4 分类各 6 件 2x3 网格
    - **完整模式** (`tier_groups`): 单分类按 tier 分组, 每 tier 2x3 网格
- [Impact] templates.py CSS 新增:
  - `.shop-grid`: CSS Grid 3 列布局
  - `.shop-grid-item`: 物品卡片 (圆角 + 边框)
  - `.grid-emoji/name/price/tier`: 网格内样式
  - 价格用渐变色 (#ff9a44 → #feca57) 突出
- [Impact] modules/renderer.py `render_shop` 重写:
  - 旧签名: (shop_name, fixed_items, random_items, ...)
  - 新签名: (page_title, categories=[], tier_groups=[], ...)
  - 高度自适应: 整合页面 4 分类 ~900px, 单分类按 tier 数
- [Impact] src/commands/shop.py run_shop_logic 全面卡片化:
  - `/商店` 无参数 → 整合页面卡片
  - `/商店 <分类>` → 单分类完整列表卡片
  - `/商店 买` → 保留纯文本 (不需要卡片)
  - `/商店 列表` → 保留纯文本
  - 渲染失败 fallback 到纯文本
- [Verify] 输出格式:
  - 卡片 header: 头像 + 用户名 + "商店" 标题 + 金币
  - 每个分类标题: "🍞 食物" / "💊 药品" / "🎒 装备" / "🎣 渔具"
  - 每个物品: emoji + 名称 + 渐变价格 + T{tier} {稀有度}
  - footer: 购买提示

## 2026-09-04 凌晨 (商店 V3 重构: 取消基础/公司商店分离, 4 分类整合展示)
- [Impact] modules/shop.py 完全重写 (517 → 360 行):
  - 取消 SHOPS 字典 (基础商店/小吃街/药品店等 7 家分类)
  - 取消固定/随机商品池配置
  - 取消 SHOPS 字段 (刷新间隔/random_pool/random_count)
  - 改用 `get_sellable_items()` 统一扫描 items.json 中 price>0 的物品
- [Impact] 新分类系统 (4 大类):
  - **食物** (food): 31 件, 排除无价/非卖品
  - **药品** (medicine): 6 件
  - **装备** (equip): 31 件 (服装/日用/通用装备/电子产品)
  - **渔具** (fishing): 85 件 (鱼竿/线/钩/浮/饵/轮)
- [Impact] /商店 无参数整合页面:
  - 每分类随机 6 种, 2 行 3 列排版
  - 抽样策略: 每个 tier 抽 1 个, 不足随机补齐
  - 显示: 稀有度圆点 + 名称 + 价格
- [Impact] /商店 <分类> 完整列表:
  - 按 tier 分组展示 (T1/T2/T3/T4/T5)
  - 支持中英文分类名 (食物/food, 渔具/fishing 等)
- [Impact] /商店 买 <物品名> [数量] 接口简化:
  - 不再依赖 shop_id, 任何可售卖物品都买
  - 食物药品默认可堆叠 (合并 quantity)
  - 装备/渔具不可堆叠 (多个独立 entry)
- [Impact] main.py view_shop + do_buy_shop_item LLM 工具:
  - view_shop 返回新增 `shop_category` / `tier` / `rarity` / `subcategory` 字段
  - 不再返回 `shops` 列表, 改为 `categories` dict
  - do_buy_shop_item 移除 shop_id 查找, 直接调 buy_item
- [Impact] company_shop 模块未删除 (保留代码, 暂未引用):
  - 公司商店 UI 已废弃, 但 company_favorability 模块仍用
  - get_company_shop_mgr() 函数保留 (其他模块可能引用)
- [Verify] 整合页面测试输出:
  - 食物: 泡面/奶茶/能量饮料/人参/火锅/红茶
  - 装备: 格子衬衫/移动电源/品牌卫衣/华为Mate60/iPhone 16 Pro Max/小米14 Ultra
  - 渔具: 蚯蚓/大蚯蚓/碳素竿/沉水米诺/乌贼块/神话鱼竿

## 2026-09-04 凌晨 (鱼线细分: 5→8 种 + 鱼竿承载力下调, 承载力主源切换为鱼线)
- [Impact] items.json 鱼线从 5 种扩展到 **8 种**, 价格梯度平滑:
  - t1: 棉线(1kg/20) + 麻线(1.5kg/35)
  - t2: 尼龙线(3.5kg/100) + 尼龙编织线(5kg/200)
  - t3: 碳线(12kg/500) + PE 编织线(18kg/800)
  - t4: 氟碳线(35kg/2000) + 隐形 stealth_bonus=0.20
  - t5: 钢丝线(150kg/8000)
- [Impact] items.json 12 鱼竿 `load_capacity_max` 全下调（主承载由鱼线承担）:
  - t1 竹竿 1.5→**0.3kg** / t2 玻璃钢 5→**0.8kg** / t3 玻璃纤维 12→**1.5kg** / 碳素 15→**2.0kg**
  - t3 筏竿 8→**1.2kg** / t4 电轮 20→**2.5kg** / 路亚 25→**2.0kg** / 海竿 25→**3.0kg** / 矶竿 30→**3.0kg**
  - t5 传说 50→**4.0kg** / 深海 80→**4.5kg** / t6 神话 100→**5.0kg**
- [Impact] 综合承载力梯度（竹竿+棉线 1.3kg → 深海+钢丝 154.5kg, 中间 6 档平滑过渡）
- [Impact] 鱼线新增字段:
  - `duration_reduce`: 0-4 (高级线缩短收竿时间)
  - `rare_bonus`: 0-10% (高级线微加稀有率)
  - `stealth_bonus`: 20% (氟碳线独家, 鱼警觉度降低, 待实现)
- [Verify] 承载力门槛与鱼尺寸对应:
  - 1-2kg (micro/small): 棉线/麻线
  - 4-5kg (medium): 尼龙线/编织线
  - 13-20kg (large): 碳线/PE
  - 38kg (shark): 氟碳线
  - 154kg (whale/monster): 钢丝线

## 2026-09-04 凌晨 (钩解锁饵: 鱼竿 max_hook_slots + 同饵自动合并)
- [Impact] items.json 12 个鱼竿 `max_bait_slots` → `max_hook_slots`:
  - 决定鱼竿可装多少**鱼钩**（不是直接 bait 槽）
  - t1 竹竿: 1 钩 / t2 玻璃钢竿: 1 钩 / t3 玻璃纤维/碳素: 2 钩 / t3 筏竿: 1 钩
  - t4 海竿/矶竿: 3 钩 / t4 电轮竿/路亚竿: 2 钩 / t5 传说/深海: 3 钩 / t6 神话: 3 钩
- [Impact] 数据结构升级:
  - 新增 `equipped_items.hook_slots: []` (鱼钩槽列表)
  - 已有 `equipped_items.bait_slots: []` 现在**槽数 = 已装备鱼钩数**
  - 用户装 2 个鱼钩 → 只能装 2 个饵料
- [Impact] modules/item.py equip_item 重大重写:
  - **hook 槽**: 检查鱼竿 max_hook_slots, 追加到 hook_slots 列表
  - **bait 槽**: 检查 hook_slots 数量上限 (未装钩不能装饵)
  - **同饵合并**: 装同种饵料时合并到现有槽, +quantity (不创建新槽)
  - **拟饵**: stackable=False, 装上不消耗 inventory, quantity=null
  - **消耗饵**: 装上时把 inventory 数量合并到 slot.quantity, inventory 扣 1
- [Impact] modules/tick.py 多钩 effects 合并:
  - `hook_effects.target_size_weights` 累加 (多钩 = 扩大尺寸覆盖)
  - 其他字段 (rare_bonus 等) 也累加
- [Impact] modules/tick.py `_consume_one_bait` 改扣 bait_slot.quantity:
  - 不再扣 inventory, 直接扣 slot 内的 quantity
  - quantity 0 时该 slot 视为空 (装备 UI 可清理)
- [Impact] src/commands/fishing.py 新增 `_resolve_hook_slots`:
  - 返回 `[(hook_id, effects), ...]` 列表
  - 优先 hook_slots, fallback 到 hook (旧)
- [Verify] 装备流程:
  - 鱼竿 3 钩槽 → 装钩1+钩2 → 2 饵槽
  - 装蚯蚓 → bait_slots[0].quantity = inventory.quantity
  - 再买 5 个蚯蚓 → /渔具 装 蚯蚓 → 合并: bait_slots[0].quantity += 5
  - 中鱼 → bait_slots[0].quantity -= 1, 拟饵不变

## 2026-09-04 凌晨 (bait 槽多槽化 - 鱼竿 max_bait_slots 决定数量, 最多 3 个)
- [Impact] items.json 12 个鱼竿加 `max_bait_slots` 字段 (鱼竿决定 bait 槽数):
  - t1 竹竿: 1 槽 / t2 玻璃钢竿: 1 槽 / t3 玻璃纤维/碳素: 2 槽 / t3 筏竿: 1 槽
  - t4 海竿/矶竿: 3 槽 / t4 电轮竿/路亚竿: 2 槽 / t5 传说/深海: 3 槽 / t6 神话: 3 槽
- [Impact] items.json 40 个饵料 (28 消耗饵 + 12 拟饵) 加 `slot=bait` 字段
- [Impact] equipped_items 结构升级: `bait` 单 dict → `bait_slots` list 列表
  - 旧数据自动兼容 (有 bait 无 bait_slots 时 fallback)
- [Impact] src/fishing/fishing_manager.py roll_catch 签名改造:
  - 旧 `bait_effects: dict` → 新 `bait_effects_list: list[dict]`
  - 多饵 rare_bonus 累加 (例 3 槽 +10%/+15%/+20% = +45%)
  - 多饵 target_diet 取**并集** (任一饵料匹配即可, 增加命中)
  - 多饵 habitat_filter 取**并集** (扩大候选水域)
  - 多饵 fish_bonus 累加
- [Impact] modules/tick.py 新增 `_consume_one_bait`:
  - 中鱼后扣 1 个消耗饵 (inventory.quantity -= 1)
  - 拟饵 (consumable=False) 不消耗, 永久装备
  - 优先扣第一个 is_consumable=True 的饵
- [Impact] modules/item.py equip_item 改造:
  - bait 槽特殊处理: 追加到 bait_slots list, 检查鱼竿 max_bait_slots 上限
  - 拟饵装上后保留 inventory (不扣, 因 stackable=False)
  - 消耗饵装上扣 1 个
- [Impact] src/commands/fishing.py 新增 `_resolve_bait_slots`:
  - 返回 `[(bait_id, effects), ...]` 列表
  - 优先读 bait_slots (新), fallback 到 bait (旧), 再 fallback 到 inventory 第一个饵
- [Verify] 鱼竿 bait 槽分配:
  - 1 槽 (40%): 竹竿/玻璃钢/筏竿
  - 2 槽 (40%): 玻璃纤维/碳素/电轮/路亚
  - 3 槽 (60%): 海竿/矶竿/传说/深海/神话

## 2026-09-04 凌晨 (鱼饵双系统: 28 消耗饵 + 12 拟饵 + 食性完全下放)
- [Impact] items.json 鱼饵从 28 消耗饵重设为 **28 消耗饵 + 12 拟饵 = 40 种**
- [Impact] **两套鱼饵系统**:
  - **消耗饵 (consumable=true)**: 价格 5-800, rare_bonus 高 (5%-60%), 每次消耗 1 个
    - 子分类 `bait`, 类别 `consumable`
  - **拟饵 (consumable=false)**: 价格 80-3500, rare_bonus 低 (3%-22%), 不消耗
    - 子分类 `lure`, 类别 `equipment`, stackable=false
  - 拟饵价格约同 tier 消耗饵 5-10 倍, 加成约 1/3
- [Impact] **食性完全下放鱼饵**: 所有鱼饵 effects 加 `target_diet` 字段
  - 例: 玉米粒 target_diet=[herbivore] (草食饵)
  - 蚯蚓 target_diet=[omnivore] (杂食饵)
  - 龙涎香 target_diet=[omnivore, herbivore] (传说道饵)
- [Impact] 鱼饵设计原则:
  - **t1**: 蚯蚓/红虫/玉米粒/面团/面包虫/蓝藻 (基础饵, 全 omnivore/herbivore)
  - **t2**: 大蚯蚓/螺蛳/青虫/小鱼块/商品饵 (中级, 按食性分化)
  - **t3**: 活泥鳅/活虾/活小鱼/海虫沙蚕/海星/海虾/螃蟹/蜂蛹 (高级活饵)
  - **t4**: 大虾/大鱿鱼块/活鱼块/深海鱼块/鱿鱼须/发亮鱼块 (顶级海饵)
  - **t5**: 乌贼块/巨型鱼块/龙涎香 (终极饵, 龙涎香 +60% 传说)
- [Impact] 拟饵设计 (12 种路亚):
  - **t1**: 塑料软虫 (¥80)
  - **t2**: 金属亮片 / 橡胶鱼
  - **t3**: 米诺 / 铅头软虫 / 旋转亮片
  - **t4**: 波趴 / 沉水米诺 / VIB颤泳
  - **t5**: 大型金属饵 / 木虾 / 鲣鱼木饵 (顶级)
- [Verify] 价格对比 (同 tier):
  - t1: 塑料软虫 ¥80 vs 蚯蚓 ¥5 (16x)
  - t3: 米诺 ¥500 vs 活泥鳅 ¥80 (6x)
  - t5: 鲣鱼木饵 ¥3500 vs 龙涎香 ¥800 (4x)
- [Verify] rare_bonus 对比 (同 tier):
  - t1: 塑料软虫 +3% vs 蚯蚓 +5%
  - t3: 米诺 +10% vs 活泥鳅 +25%
  - t5: 鲣鱼木饵 +22% vs 龙涎香 +60%
- [TODO] roll_catch 需要改造 (下一轮):
  - 鱼钩 size_weights 过滤 (已实现)
  - 鱼饵 target_diet 过滤 (待实现 - 钩的 target_diet 已删, 移给饵)
  - 鱼饵 habitat_filter 过滤 (已实现)
  - 消耗逻辑: 上钩后从 inventory 扣 quantity

## 2026-09-04 凌晨 (鱼钩重构: 加 monster 级专钩 + 三本钩改名 + 食性下放鱼饵)
- [Impact] items.json 鱼钩从 14 种改为 **15 种** (覆盖 7 级尺寸 + 食性完全下放鱼饵):
  - **5 单尺寸专钩 (覆盖 small/medium/large/shark/whale/monster)**:
    - 袖钩(small100%) / 秋田狐(medium100%) / 鲤钩(large100%) / 鲨鱼钩(shark100%, t4) / 鲸钩(whale100%, t4) / 巨物锚钩(monster100%, t5, 10000金) ⭐
  - **6 双尺寸过渡钩**:
    - 海夕(micro20/small80) / 伊势尼(small20/medium80) / 新关东(medium30/large70) / 拟饵钩(shark60/large40) / 三本钩(whale60/shark40) / 串钩(whale70/shark30)
  - **2 三尺寸特殊钩**:
    - 爆炸钩(whale50/shark30/monster20) - 唯一含 monster 的非专钩
  - **2 万能型**:
    - 伊豆(4尺寸25%) / 小矶(6尺寸16.7%)
- [Impact] 拟饵三本钩 → **三本钩** (简化命名)
- [Impact] **食性完全下放鱼饵**: 所有鱼钩 effects 移除 target_diet 字段
  - 鱼钩只控尺寸, 鱼饵 (鱼饵系统) 控食性
  - roll_catch 中 target_diet 永远为空 → 跳过 diet 过滤 (保留兼容)
- [Verify] size_class 全覆盖 (micro/small/medium/large/shark/whale/monster):
  - micro: 海夕/小矶
  - small: 袖钩/海夕/伊势尼/伊豆/小矶
  - medium: 秋田狐/伊势尼/新关东/伊豆/小矶
  - large: 鲤钩/新关东/拟饵钩/伊豆/小矶
  - shark: 拟饵钩/鲨鱼钩/三本钩/串钩/爆炸钩/伊豆/小矶
  - whale: 鲸钩/三本钩/串钩/爆炸钩/小矶
  - monster: 巨物锚钩/爆炸钩

## 2026-09-04 凌晨 (鱼钩 size_class 权重精简 - 单/双/万能三档)
- [Impact] items.json 鱼钩从 13 种重构为 **14 种** (按覆盖尺寸分档):
  - **3 单尺寸钩 (t1-3)**: 袖钩(small100%) / 秋田狐(medium100%) / 鲤钩(large100%) - 一钩一鱼
  - **9 双尺寸钩 (t1-5)**: 海夕/伊势尼/新关东/千又/铅头钩/拟饵三本钩/爆炸钩/串钩/铁板钩 - 覆盖邻近 2 尺寸
  - **2 万能钩 (t3-4)**: 伊豆(4尺寸) / 小矶(6尺寸) - 唯一覆盖 3+ 尺寸的钩
- [Impact] 修正逻辑: 大部分鱼钩只覆盖 1-2 种 size, 万能型才覆盖 3-6 种
- [Verify] 鱼钩覆盖尺寸分布:
  - 1 尺寸: 3 种 (袖钩/秋田狐/鲤钩)
  - 2 尺寸: 9 种 (覆盖邻近 2 档, 例 small+medium)
  - 4 尺寸: 1 种 (伊豆 - 万能型)
  - 6 尺寸: 1 种 (小矶 - 万能型)

## 2026-09-04 凌晨 (默认鱼钩 → 袖钩 + 新增铁板钩)
- [Impact] items.json: **删 "默认鱼钩"** (t1, small40/medium40/large20)
- [Impact] items.json: **加 "铁板钩"** (t5, shark40/whale50/monster10, +12%rare, 7000 金)
  - 路亚顶级装备, 专攻鲨鱼级与巨物, 替代原"默认鱼钩"位置
- [Impact] src/commands/checkin.py: 新玩家注册时**赠送默认渔具**
  - `_STARTER_FISHING_GEAR = {hook: 袖钩, fishing_rod: 竹竿, line: 棉线}`
  - `_grant_starter_fishing_gear(store, user_id)` 在 create_user 后自动注入背包 + 装备
  - 旧用户 (已注册) 不受影响, 仅新注册用户自动送
- [Verify] 鱼钩总览 (13 种): 袖钩/海夕/秋田狐/伊势尼/新关东/千又/伊豆/小矶/铅头钩/拟饵三本钩/爆炸钩/串钩/铁板钩
- [Verify] 新玩家流程: /签到 → 自动赠送袖钩+竹竿+棉线 → 装备就绪 → 直接 /钓鱼 即可

## 2026-09-04 凌晨 (鱼钩重设计: size_class 权重抽样 - 取代硬过滤)
- [Impact] items.json 鱼钩从 20 种简化为 **13 种** (按用户分类 + size_class 加权):
  - **小鱼钩 (t1)**: 袖钩(micro30/small70) / 海夕(micro20/small50/medium30)
  - **小鱼偏中 (t2)**: 秋田狐(small70/medium30)
  - **中大鱼钩 (t2-3)**: 伊势尼(small10/medium60/large30, +3%rare) / 新关东(medium40/large50/shark10, +5%) / 千又(medium30/large60/shark10, +5%)
  - **万能型 (t3)**: 伊豆(6尺寸) / 小矶(small+medium+large+shark)
  - **路亚 (t3-4)**: 铅头钩(medium20/large50/shark30, 食肉) / 拟饵三本钩(large40/shark50/whale10, 食肉, +5%size)
  - **守大物/远投 (t5)**: 爆炸钩(large20/shark50/whale20/monster10, +10%rare) / 串钩(shark30/whale50/monster20, +15%rare)
  - **初始鱼钩 (t1)**: 默认鱼钩(small40/medium40/large20)
- [Impact] 鱼钩字段从 target_sizes (硬过滤) → target_size_weights (加权):
  - 取代"非此即彼过滤", 改为"加权抽样"
  - 例: 袖钩不只钓小型鱼, 30%概率钓 micro (微型鱼)
- [Impact] roll_catch 接入 `_pick_fish_by_size_weights`:
  - 过滤: 候选鱼 size_class 在 size_weights keys 中, 且 diet 匹配
  - 加权: random.choices 按 size_weights 抽一条
  - 无鱼钩或 size_weights 空 → 走原 _weight_fish_choice (兼容)
- [Impact] `_fish_size` 新 helper: 读鱼 size_class 字段, 兜底用 weight_range 现算
- [Impact] /渔具 显示段改为"鱼钩尺寸权重: 微型30% 小型70%"
- [Verify] 池塘候选 10 条鱼 (micro 3 / small 3 / medium 4):
  - 袖钩 200次抽样: micro=55, small=145 (符合 30/70) ✓
  - 海夕: medium=66, micro=45, small=89 (符合 30/20/50) ✓
  - 秋田狐: small=132, medium=68 (符合 70/30) ✓

## 2026-09-04 凌晨 (鱼 size_class 字段写入 - 便于之后分类运算)
- [Impact] fishes.json 65 条鱼加 `size_class` 字段 (与 _fish_in_buckets 同步)
  - 分布: micro 3 / small 13 / medium 30 / large 10 / shark 7 / whale 2
  - 字段值: "micro"/"small"/"medium"/"large"/"shark"/"whale"/"monster"
- [Impact] `_fish_in_buckets` 优先读 fish["size_class"], 兜底用 weight_range 现算
  - 性能: 命中字段跳过现算 (1 次 dict.get vs 6 次 if 比较)
  - 兼容: 未迁移鱼 (旧数据/动态生成) 自动兜底
- [Verify] 背包鱼数据 (id/name/type/weight/size_label/length_cm/time) **不受影响**:
  - 用户背包存的是 "已钓到" 的实例, 不带 size_class 字段
  - size_class 仅在鱼**配置** fishes.json 中, 与背包数据完全独立
  - market 卖鱼走 FISHES_DATA[name].weight_range 也独立
- [Impact] 用户背包鱼 (inventory item) 无 size_class 字段 → 不影响任何现有业务 (卖鱼/吃鱼/展示/记录)

## 2026-09-04 凌晨 (鱼 7级尺寸 + 3种食性 + 20 种鱼钩重设计)
- [Impact] fishes.json 65 条鱼加 `diet` 字段 (carnivore/omnivore/herbivore)
  - 食性分布: carnivore 39 / omnivore 18 / herbivore 8
- [Impact] 鱼尺寸分级从 5 桶改为 7 桶:
  - micro(≤0.2kg) / small(0.2-1kg) / medium(1-5kg) / large(5-20kg) / shark(20-100kg) / whale(100-500kg) / monster(>500kg)
- [Impact] items.json 鱼钩从 5 种重写为 **20 种** (覆盖 7级尺寸 + 3种食性):
  - **7 尺寸专用钩**: 微型/小型/中型/大型/鲨鱼/鲸/巨物 (tier 1-5)
  - **3 食肉钩**: 食肉中型/大型/鲨鱼 (carnivore only)
  - **3 食草钩**: 食草中型/大型/鲸 (herbivore only)
  - **2 杂食钩**: 杂食中型/大型 (omnivore only)
  - **3 组合双钩**: 通吃/深海双/终极双
  - **2 特殊钩**: 万能(全尺寸但 -5% rare) / 黄金(中+大 +15% rare)
- [Impact] _fish_in_buckets 重写: 接受 target_sizes(7级) + target_diet(3种), 鱼按 w_max 命中尺寸后必须 diet 匹配
- [Impact] roll_catch 改用 hook_effects.get("target_sizes") + get("target_diet")
- [Impact] /渔具 显示段改为"鱼钩尺寸" + "鱼钩食性", 支持空 (无限制)
- [保留] 鱼竿/鱼线 load_capacity_max 累加 combined_max + 超载断线机制不变
- [Verify] 验证表格 (14 种典型鱼 × 14 种典型钩):
  - 小虾(0.01-0.05, omnivore): 微型钩/万能钩 命中
  - 草鱼(0.5-2.0, herbivore): 中型/食草中型/通吃/黄金/万能 命中
  - 章鱼(0.5-10, carnivore): 中型/大型/食肉中型/通吃/深海双/黄金/万能 命中
  - 龙趸(10-100, carnivore): 大型/鲨鱼/终极双/黄金/万能 命中

## 2026-09-04 凌晨 (渔具承载力重构: 鱼钩 target_buckets + 断线机制回归 - 用户新设计)
- [Impact] items.json 5 个鱼钩字段重写 (weight_range → target_buckets):
  - 小钩: target_buckets=["small"] 仅小鱼 (w_max<=1kg)
  - 中钩: ["small", "medium"] 小鱼+中鱼
  - 大钩: ["medium", "large"] 中鱼+大鱼
  - 三本钩: ["large", "shark"] 大鱼+鲨鱼级
  - 钛合金钩: ["shark", "monster"] 鲨鱼级+巨物
  - 重叠设计: 大钩能钓中钩能钓的鱼 (大钩 target 包含下级桶)
- [Impact] roll_catch 改用 _fish_in_buckets 判定 (按鱼 weight_range 分桶交集):
  - bucket 范围: small(<1kg) / medium(0.5-5kg) / large(2-20kg) / shark(10-100kg) / monster(>50kg)
  - 每条鱼自动归入 1-2 个桶 (基于 w_max 主桶 + 重叠覆盖)
- [Impact] 断线机制回归 (用户改主意保留):
  - 中鱼后如果 weight > combined_max → 按超载%概率断线
  - 断线概率: ≤10%→30%, 10-20%→60%, 20-30%→90%, >30%→100%
  - 断线返回 {_line_break: True, ...} 给 tick.py 发通知
  - 断线**不算鱼**: 不写 inventory, 无经验, 无金币
  - 但给玩家发"巨物逃了"通知, 保留钓上巨物的期待感
- [Feat] tick.py 新增 `_notify_line_break` 方法: 扔通知队列发"噗通! XX 扯断线...超载 X% (承载力 Ykg)"
- [Impact] /渔具 显示段改【🎯 承载与断线】: 杆承重/线承重/承载上限/鱼钩圈定/断线提示
- [Impact] 取消前置 weight_range 过滤 (承载力不再"拦"鱼, 改为"超载断线"后置)
- [Verify] _fish_in_buckets 测试 (66 条鱼分桶正确):
  - 小鲫鱼(0.1,0.4): only 小钩/中钩
  - 鲤鱼(0.3,1.5): 中钩/大钩
  - 草鱼(0.5,2.5): 中钩/大钩/三本钩
  - 鲨鱼小(5,20): 大钩/三本钩/钛合金钩
  - 翻车鱼(50,200): 三本钩/钛合金钩
- [弃用] 鱼钩 weight_range 字段 (被 target_buckets 替代)
- [保留] 鱼竿/鱼线 load_capacity_max (承载力公式不变)

## 2026-09-03 深夜 (渔具承载力系统 - 用户设计: 鱼竿/鱼线累加 + 鱼钩绝对范围)
- [Impact] items.json 22 件装备字段重写:
  - 12 鱼竿加 `load_capacity_max` (kg): 竹竿 1.5 → 神话鱼竿 100.0
  - 5 鱼线加 `load_capacity_max` (kg), 删 `break_strength`: 棉线 0.5 → 钢丝线 100.0
  - 5 鱼钩改 `weight_range` [min, max] kg, 删 `min_size_bonus`: 小钩 [0.1, 1.0] → 钛合金钩 [5, 200]
- [Impact] roll_catch 接入承载力过滤 (9/3晚 用户设计):
  - 鱼竿 max + 鱼线 max = 累加 combined_max
  - 鱼钩 weight_range 给绝对硬约束 [min, max]
  - 实际可钓: max(0.1, hook_min) ~ min(combined_max, hook_max)
  - 完全超出承载的鱼被过滤掉, 部分 overlap clamp 后作为候选
  - size_bonus 抽到的 weight 兜底不超过 gear_max (防止超载)
- [Impact] 鱼钩 min_size_bonus 字段移除 (语义被 weight_range 替代)
- [Feat] `/渔具` 新增【 🎯 承载范围 】段: 杆承重 / 线承重 / 合计 / 鱼钩限制 / 实际可钓
- [Impact] break_strength 完全废弃 (用户 9/3晚 决定不保留)
- [Impact] 断线机制废除 - 承载力改为"前置过滤", 超载的鱼根本不进入候选
- [Verify] 默认 (空 effects) → 竹竿1.5 + 棉线0.5 = 2kg 上限, 草鱼 (0.5-2.5) clamp 到 (0.5, 2.0), 鲤鱼 (0.3-1.5) 完全在范围内
- [Verify] 小钩 (0.1, 1.0) + 深海 → 深海没鱼在范围内, 期望 0 条 ✓
- [Verify] 场景对照: 竹竿+棉线+无钩=2kg max / +小钩=1kg max / +钛合金钩+钢丝线=101.5kg max

## 2026-09-03 晚 (渔具第 6 槽: 鱼轮 reel - 钓鱼经验加成)
- [Feat] items.json 5 个鱼轮加 `exp_bonus` 字段: 塑料轮 0% / 纺车轮 5% / 水滴轮 10% / 鼓轮 20% / 电动轮 35%
- [Feat] SLOTS/SLOT_EMOJI/FISHING_GEAR_SLOTS 加 `reel` 槽 (鱼轮 🧵)
- [Impact] roll_catch 新参数 `reel_effects`: reel.rare_bonus 叠加到 `extra_rare`
- [Impact] apply_catch 新参数 `reel_effects`: reel.exp_bonus 应用于经验公式 `exp_gain *= (1 + reel_exp_bonus)`
- [Impl] `run_fishing_start_logic` 解析 reel 槽 + 把 reel_id 写入 action_detail + duration_reduce 累加
- [Impl] `tick.py` 把 reel_effects 传给 roll_catch 和 apply_catch
- [Impl] `/渔具` 显示 6 槽 + reel 描述 (经验%/时间/tick/稀有%/自动收竿)
- [Impl] `_calc_gear_effects` 聚合 6 槽 effects
- [Verify] 经验公式 (小鲫鱼 common t1 大): 无=25 / 塑料轮=25 / 纺车轮=26 / 水滴轮=27 / 鼓轮=30 / 电动轮=33
- [Verify] roll_catch 老签名仍兼容 (reel_effects 默认 {})
- [弃用] fishing_waders (涉水鞋) 子类未接入 (用户 9/3 决定废弃)

## 2026-09-03 (渔具双轨制: 5 槽独立 + 全部接入 roll_catch)
- [Feat] **渔具 5 槽位独立系统** (用户 9/3 决定: 不复用通用 5 装备槽)
  - SLOTS 加 5 槽: `fishing_rod` 🎣 / `line` 🪢 / `hook` 🪝 / `float` 🪶 / `bait` 🪱
  - FISHING_GEAR_SLOTS 提供中文名 → key 映射
- [Feat] `/渔具` 命令 (`src/commands/fishing_gear.py`)
  - `/渔具` → 显示 5 槽装备状态 + 套装效果 + 背包可装备
  - `/渔具 装 <名字/序号>` → 装备
  - `/渔具 卸 <栏位>` → 卸下 (中文/英文名都接受)
- [Feat] items.json 补 40 个 slot 字段 (12 鱼竿 + 5 浮漂 + 28 鱼饵)
- [Impact] **roll_catch 接入全部 5 件 effects**
  - 鱼竿: fishing_bonus → 基础中鱼率
  - 鱼线: min_size_bonus → 提升上鱼最大重量
  - 鱼钩: rare_bonus → 限制上鱼种类 + 提升某些种类概率 (min_size_bonus)
  - 浮漂: fishing_bonus → 中鱼率 + sensitivity → 提高尺寸 (每级 +3%)
  - 鱼饵: habitat_filter → 调整上鱼种类池 + fish_bonus → 特定鱼加权 + rare_bonus → 稀有度
- [Impl] `_weight_fish_choice` 加 `fish_bonus` 参数: 鱼饵 fish_bonus 命中的鱼额外乘 (1+加成*20)
- [Impl] `run_fishing_start_logic` 把 line_id/hook_id/float_id 写入 action_detail
- [Impl] `tick.py` 把 line/hook/float effects 传给 roll_catch
- [Feat] 2 个 LLM tool: `view_fishing_gear` + `do_fishing_gear`
- [Tool Count] 32 → 34
- [ImportFix] `src/commands/__init__.py` 加 run_fishing_gear_logic 导出 (避免 ImportError)
- [Unchanged] fishing_reel / fishing_waders 子类暂未接入 (用户未提到, 不强行扩大范围)
- [Verify] roll_catch 老签名 (rod, bait) 兼容; 新签名 (rod, bait, line, hook, float) 跑通

## 2026-09-03 (钓鱼等级 Lv.1 卡死 + 等级徽章左上角错位)
- [BugFix] 9/3 session: 钓了上百条鱼还在 Lv.1
- [RootCause] `src/fishing/fishing_manager.py:apply_catch` 完全没写 `skill_exp["钓鱼"]`. `modules/tick.py:750-755` 调 `catch.get("exp_reward")` 但 catch 字典没这字段 → 永远 exp=0
- [Fix] `apply_catch` 加经验逻辑: `exp = 10 + (tier-1)*5 + rarity_bonus + size_bonus`, 然后按 rarity 倍率 (`common:1.0, rare:1.2, epic:1.5, legendary:2.0`)
- [Fix] `tick.py` 改用 `apply_catch` 写入的 `_last_levelup` 字段, 删除死代码 `catch.get("exp_reward")` 路径
- [Fix] `render_fishing_catch` 加 `exp_gain` 参数 (传 `levelup_info["exp_gain"]`)
- [Fix] `user["skills"]["钓鱼"] = level` 同步 (兼容旧 UI 读取)
- [UI] `templates.py FISHING_CARD` 等级徽章从 `left` 改 `right` (右上角)
- [Exp] 常见小鱼 +10, 中鱼 +15, 罕见大鱼 +30, 史诗 +97, 传说 +210
- [Feat] LLM do_eat 加 `quantity` 参数 (默认 1, 上限 10). 玩家说"一次吃完" → LLM 不用循环 3 次调 do_eat
- [Refactor] **方案 B** (业务层加批量路径): `src/commands/food.py run_eat_logic` 加 `batch_quantity` 分支
  - **群聊/LLM 统一语义**: selector 是数字 → 吃 N 份 (堆叠累扣, 不堆叠按找到顺序吃). 避免歧义
  - selector 是 None → 吃 1 份 (单次)
  - selector 是 "大" → 同名最大那条 (单次)
  - selector 是其他字符串 → 走 fallback (无)
  - 批量路径: 一次性扣 N 份背包 (按堆叠数顺序扣) + effects 累加 (food `{satiety: 30} × 3 = 90`)
  - 不足时只吃背包里有的 + 提示"⚠️ 想吃 N 个但背包只有 Y 个"
- [BreakingChange] 删除原 "selector 数字 → 第 N 个" 逻辑 (会破坏"第 N 个"的鱼选择习惯). 改为统一批量.
  - 影响: `/吃 鱼名 2` 现在是"吃 2 份"而非"第 2 条". 鱼不堆叠时如果想"按 weight 排的第 2 条", 暂时不支持 (后续可加 `/吃 鱼名 大`/`小`/数字+权重选择)
- [Doc] REBECCA_PROMPT.md do_eat 工具说明 + "批量吃" 段落
- [Help] food.py docstring 更新帮助文本

## 2026-09-03 (UI/筛选)
- [UI] modules/templates.py + modules/renderer.py — 钓鱼通知卡片：左上角 Lv.X 等级徽章、名字下方显示钓鱼称号、尺寸数值化（按 size_label 索引映射 15-120cm 随机区间）
- [UI] 全局鱼尺寸数值化：length_cm 写入 fishing_manager.apply_catch + tick.last_catch；所有用户可见位置（鱼塘图鉴/个人中心/卖鱼/吃鱼/背包）从 size_label 文本切换为 length_str，老数据按 size_label 兜底
- [Feature] 背包 / 卖鱼增加筛选：尺寸(小/大/巨) + 稀有度(常见/不凡/稀有/史诗/传奇/传说) + 类别(鱼/食物/物品)。例 `/背包 鱼 大` `/背包 鱼 稀有` `/卖 鱼 巨` `/卖 食物 史诗`。复用 _helpers.py 共享解析 + 应用逻辑，token 歧义时稀有度优先。
- [Feature] 卖鱼保留售出：`/卖 鱼 留大 [N]` `/卖 鱼 留小 [N]` `/卖 鱼 大 留大 1`。按 weight 排序留下 N 条最大/最小不卖，其余卖。SELL_RESULT 卡片新增"🪝 保留"区显示被留下的鱼。保留参数仅对鱼生效。

Tag: `[Add]` 新功能 | `[Fix]` Bug 修复 | `[Refactor]` 重构 | `[Bug]` 待修 | `[Decision]` 架构决策

---

## Unreleased (开发中)

### [Refactor] 2026-09-05
- [Fix] `main.py:927` —— 删死代码 `_fm_module = sys.modules.get(...) if False else None`, 加注释说明 `FISHES` 必须显式 import 才能引用
- [Fix] `main.py:1068-1070` —— 删冗余 `from .modules.constants import STOCKS as CONST_STOCKS` 双源, `__import__` + `hasattr` 链改 `hasattr(get_user_stocks, "__call__")`, `available_stocks` 降级单源
- [Refactor] `modules/messenger.py:_send_platform_message` —— 不再走 StarTools.send_message (platform_id 解析有 bug), 改走 main.py `_notify_queue` + 缓存 event 方案, 与 tick.py `_notify_catch / _notify_empty` 走同一条路. 彻底消除 ARCHITECTURE.md L4 警告的"3 套发送路径并存". 移除顶部 `import asyncio` / `from astrbot.api.star import StarTools` 死 import
- [Add] `tests/test_llm_tool_schemas.py` —— 7 个 schema 校验 (31 个 LLM 工具 docstring 自动化). **新增 BUG 发现**: 14 个工具缺 `Returns:` 段 (get_fishing_records / get_inventory_summary / do_cancel / do_learn / do_entertain / do_eat / do_buy_shop_item / do_residence / do_equip / do_fishing_gear / do_complete_job / do_cancel_job / do_fishing_start / do_settings), 全部补齐
- [Add] `modules/renderer.py` —— 落地 ARCHITECTURE.md P0 #2: `ViewSpec` class + 全局 `VIEW_SPECS` dict (14 个 CardType 契约声明) + `get_view_spec()`. `_render()` 入口自动 `apply_defaults` + `check_required` (缺关键字段打 warning 不抛, 走 fallback). 默认 values 兜底后, 25 个命令调用方少写 50% try/except 补默认值
- [Add] `tests/test_view_specs.py` —— 6 个 AST 静态分析测试 (无需 AstrBot runtime), 验证: ViewSpec 数量 ≥ 13 / apply_defaults 不覆盖 / required 字段都在 defaults 里 / defaults ≥ 3 字段防太空 spec
- [Add] `src/data/user_view.py` —— 落地 ARCHITECTURE.md P1 #3: typed accessor 层. 30+ 公共函数消除 `user["fishing"]["fish_caught"]` 嵌套散落. 提供 getter (get_gold/get_status/get_fishing/...) + mutator (set_status/add_gold/add_fish/equip_item/...) + 模板视图 (view_for_profile_card / view_for_fish_dex_card / view_for_fishing_gear_card / view_for_backpack_card). **不改存储格式**: 老数据完全兼容, 缺字段自动补默认
- [Add] `tests/test_user_view.py` —— 17 个单元测试覆盖所有 getter / mutator / 模板视图. 老数据 + 空 user + 完整 user 三种情况都验证
- [Add] `src/data/content_registry.py` —— 内容注册中心 (ContentRegistry + ContentDef dataclass). 统一加载 6 类配置数据 (164 物品 / 91 鱼 / 99 课程 / 14 工作 / 7 住所 / 30 娱乐 = 405 项内容). 11 种 actions (sell/buy/eat/use/equip/use_in_fishing/learn/work/reside/entertain/enchant) 替代散落 if/elif. **自动推导**: JSON 没 actions 字段时根据 category/slot/price 自动给出合理默认, 老 JSON 完全不用改. 查询 API: find_by_id / find_by_name / supports_action / filter_by_action / get_sellable_items
- [Add] `tests/test_content_registry.py` —— 25 个测试覆盖: 6 类内容加载 / actions 自动推导 / 查询 API / frozen dataclass / 阶段 2 老数据兼容验证
- [Add] `src/ui/message_sender.py` —— **MessageSender 统一发送器 (ARCHITECTURE.md P0 #1 落地)**. 3 个核心入口: `send_card(event, card_type, data, fallback_text)` async generator, 渲染成功发图失败 fallback 文本异常统一捕获; `send_text(event, text, at_user=False)` 自动 @nickname; `notify(user_id, msg_type, text, image_url)` tick 后台推送. 25 个命令可改用 sender 替代散落 try/except + yield image_result/plain_result 样板
- [Refactor] `main.py:_cache_event` —— **缓存按 session_key 分组 (9/6 改进)**, 旧 `_recent_event[user_id]` 改 `_recent_events[session_key]`. session_key = "platform_id|session_type|session_id". 解决群 A 钓鱼/群 B 闲聊时通知发错窗口的 BUG. 同时触发 `sender.flush_pending_for_session(event)` 异步补发该 session 的 pending 通知
- [Refactor] `main.py:_notification_consumer` —— 移除 1h 过期保护 (玩家可能忙几小时, 通知必须送达). 按 session_key 查找缓存 event. 失败 / 无缓存 event 由 `MessageSender.notify()` 持久化兜底
- [Add] `tests/test_message_sender.py` —— 21 个测试覆盖: send_card 3 路径 (成功/空/异常) / send_text at_user / notify 立即发送+持久化 / 本地图片持久化 / URL 持久化 / 24h 过期清理 / 上限截断 / flush_pending_for_session 匹配/不匹配/过期/延迟提示/图片失效 5 场景. 不依赖 AstrBot runtime (用 stub plugin + stub MessageChain)
- [Doc] `ARCHITECTURE.md` —— 更新通知子系统模块图 (9/6 重构版), 标记 P0 #1/#2 已完成, P1 #3/#5 已完成
- [Bug] 取消 1h 过期保护 —— 玩家发指令去忙/睡 4h+, tick 完成通知仍能送达 (此前 1h 后会跳过)
- [Refactor] `modules/messenger.py:_send_platform_message` —— 缓存键兼容新旧 (`_recent_events` / `_recent_event`), 用 `_extract_session_key()` 推断 session_key 后入队, consumer 按 session_key 路由

### 应用阶段 1: 3 个高频命令 + 4 基础设施落地

- [Refactor] `src/commands/profile.py:run_profile_logic` —— 改用 `MessageSender.send_card()`, 配 `view_for_profile_card(user)` 一次拿齐 data。消除 1 处 try/except 样板。
- [Refactor] `src/commands/help.py:run_help_logic` —— 改用 `MessageSender.send_card()`, fallback_text 提取为 `_HELP_FALLBACK` 常量。消除 1 处 try/except。
- [Refactor] `src/commands/sell.py:run_sell_logic + _run_sell_with_filter` —— 改用 `MessageSender.send_card()`, 消除 5 处 try/except + renderer._render 样板 (SELL_OVERVIEW / SELL_RESULT 各 2 处 + filter 分支 1 处)。`_run_sell_with_filter` 签名 `renderer` → `sender`。
- [Refactor] `src/commands/fishing.py:run_fishing_logic` —— 主入口改用 sender; `run_fishing_show_spots_logic` 改用 sender.send_card() + CardType.FISHING_SPOTS; `run_fish_dex_logic` 改用 sender + `view_for_fish_dex_card(user, FISHES)`。消除 2 处 try/except。
- [Refactor] `main.py` —— `@filter.command("卖") / @filter.command("钓鱼") / @filter.command("鱼塘")` + LLM tool `do_fishing_start` 全部传 `self._sender` 替代 `self._renderer`。
- [Refactor] `modules/shop.py:get_sellable_items` —— 改用 `ContentRegistry.instance().filter_by_action("sell", content_type="item")` 替代遍历 ITEMS dict。**回归测试**: 155 件 sellable 物品分类与旧逻辑完全一致 (food:31 / props:8 / equip:25 / fishing:85 / daily:6)。**修 ImportError**: `from ..data.content_registry` → `from ..src.data.content_registry` (runtime sys.path 不识别 `data/` 顶层)。
- [Refactor] `main.py:llm_view_fish_dex` —— 改用 `UserView.get_fish_caught/get_biggest_catch/get_fish_title(user)` 替代 `user.get("fishing", {}).get("fish_caught", {})` 嵌套访问。消除 3 处嵌套。
- [Refactor] `src/commands/fishing.py:run_fish_dex_logic` —— 改用 `view_for_fish_dex_card(user, FISHES)` + `view_for_fish_dex_card` 拿齐 data (nickname / fish_caught / all_fish / completion_pct / biggest_catch / fish_title / fish_count)。

### 总览
- **单元测试**: 88/88 全过 (market 12 / llm_tool 7 / view_specs 6 / user_view 17 / content_registry 25 / message_sender 21)
- **运行时**: AstrBot 4.27.5 PID 359628 存活, 0 errors, plugin 加载成功
- **架构债务**: MessageSender / ContentRegistry / UserView / ViewSpec 4 个新基础设施**全部已应用**到核心高频命令 (profile/help/sell/fish)。剩余 19 个命令的渐进应用 + 36 处 UserView 嵌套访问属于**未来 session 的优化项**



### [Refactor] 2026-09-03
- [Add] `ARCHITECTURE.md` — 模块图 + 数据流 + 集中化注册说明
- [Add] `WORKFLOW.md` — 加内容/命令/bug 标准流程
- [Add] `tests/test_market.py` — market fallback 单元测试
- [Add] `scripts/check_health.py` — plugin/PID/数据完整性自检
- [Refactor] `src/market/__init__.py` — 加载 foods/items.json + `_auto_register_missing()` 自动注册
- [Refactor] `src/data/user_repository.py` — `get_user` 加老 plugin_id scope fallback + 自动迁移
- [Add] `src/commands/sell.py` — 通用交易命令（5 种模式 + 安全默认展示）
- [Add] `modules/templates.py` `CardType.SELL_OVERVIEW` 模板

### [Bug] 2026-09-03（已修复）
- [Fixed] `src/market/__init__.py` — `can_sell` 只查 market.json 导致背包 65 条鱼中 52 条卖不出
- [Fixed] `main.py:477` — logger 写死 "v0.1.7" 而非动态读 metadata
- [Fixed] `modules/tick.py:_notify_catch` — `chain.url_image()` 拿到本地路径报"not a valid url"，改 `file_image`/`url_image` 分支
- [Fixed] `main.py` — `_keyword_handlers` dict 漏注册 `"sell_cmd": self.sell_cmd`，导致群聊发"卖"无响应
- [Fixed] `modules/keyword_routes.py` — 加 `KeywordRoute(keyword="卖", action="sell_cmd")` 群聊纯文路由
- [Documented] `WORKFLOW.md` — 加"加关键词触发"标准流程（3 处必改：routes/handlers/changelog）
- [Fixed] `main.py` — `@register` 版本号与 `metadata.yaml` 不一致

---

## v0.1.8 (2026-05-02)

### 重构

- **Tick 结算机制重构**：属性消耗改为整点结算
  - `WorkTickProcessor` / `SleepTickProcessor` 整点触发属性结算
  - 工作/学习/睡眠状态转换时即时结算剩余时间
  - 空闲状态每小时结算一次

### 新增

- `action_detail` 数据结构：记录工作/学习时的用户状态快照
  - `action_detail.job_id` / `action_detail.course_id` - 关联的工作/课程ID
  - `action_detail.start_time` / `action_detail.total_hours` - 开始时间和总时长
  - `action_detail.start_stats` - 开始时的用户属性快照
  - `action_detail.last_hourly_settle` - 上次整点结算时间

### 变更

- `_accept_job` 创建 `action_detail` 并保存用户数据快照
- `_show_working_status` 实时计算进度并显示当前属性
- 结算时使用快照属性计算消耗，与显示值一致

---

## v0.1.7 (2026-04-28)

### 新增

- **技能系统 v3 - 三阶体系重构**：
  - 56个技能分 T1（基础）/ T2（专业）/ T3（专精）三阶
  - 三档经验曲线：fast（速成）/ standard（标准）/ mastery（精修）
  - 前置条件系统：课程设定了严格的技能前置要求，避免"解锁即弃"
  - 课程级进阶：同技能进阶课程逐步提升前置要求（如编程进阶要求计算机基础 Lv6）

- **教育机构系统**：
  - 7所机构：匠心学堂、技能职校、IT学院、商学院、艺体学院、文理学院、专精堂
  - 机构分层：T1基础层 / T1+T2专业层 / T2+T3专精层
  - 同技能可在多处学习（不同机构课程名不同、价格/效率不同）

- **学习系统重构**：
  - `/学习` → 随机推荐3-4所相关机构 + 可学课程
  - `/学习 查询` → 查看所有机构
  - `/学习 查询#名称` → 查询机构详情或技能全路径
  - `/学习 课程名` → 直接开始学习（固定2小时，直接扣费）
  - 课程自带时长属性，无需玩家选择学习时长

### 重构

- `courses.json` 重写：99门课程统一结构（institution/tier/prerequisites/hours等）
- `modules/skills.py` 重写：引入三档经验曲线和前置检查函数
- `modules/institutions.py` 新建：机构推荐、课程查询、关键词搜索
- `interactive.py` 学习指令完全重写：机构推荐模式 + 查询模式 + 直接选课
- `modules/tick.py` 学习Tick适配新课程格式

### 修复

- **P0**: `daily_report_hour/minute` 为 None 时导致 `f"{None:02d}"` TypeError 崩溃
- **P1**: `tick.py` 课程查找失败时静默跳过，无日志
- **P1**: `courses.json` 旧课程（如 `coding_basic`）缺失 `exp_per_hour` 等字段
- **P2**: `interactive.py` 双 COURSES 导入（constants 和 institutions），来源不清晰

### 文档

- 更新 README.md 架构图，添加 institutions.json / skills.json / institutions.py 说明
- 移除 `_meta` 残留字段（skills.json / institutions.json）

---

## v0.1.6 (2026-04-27)

### 修复

- **P0**: `main.py` 导入缺失 `TICKS_PER_HOUR`，启动后1分钟 NameError 崩溃
- **P1-2**: `migrate_user_data` 的 checkin 迁移会覆盖已有签到数据（streak/active_buffs）
- **P1-3**: cron 触发器使用 UTC 而非 CST，导致结算/报告时间错误
- **P1-3**: 股票涨跌幅在日报中硬编码为0
- **P1-3**: 报告时间戳硬编码为23:00，未读取配置
- **P1-3**: `daily_report_hour/minute` 配置从未被使用

### 重构

- **P2-6**: `STOCKS` 多处重复加载，统一为 `modules/constants.py` 单一数据源
- **P2-7**: `buff`/`debuff`/`skills` 等导入分散在函数内部，统一移到模块顶部
- **P2-8**: `TickType` 类替换为纯常量（`TICK_TYPE_WORK` 等），简化代码
- **P2-9**: 清理遗留文件 `main.py.bak` 和 `src/commands/legacy/` 死代码

---

## v0.1.5 (2026-04-25)

### 新增

- **日报系统 v2 - 完整日报 + 订阅系统**：
  - 新增 `lifetime_stats` 累计数据（永久）
  - 新增 `daily_stats` 每日数据（保留30天）
  - Tick 系统自动记录工作/学习/娱乐/股票统计
  - 新增 `/设置` 指令（订阅管理、个性化设置）
  - 群组 KV 配置系统（`group_config:{id}`）
  - 群组日报：按群订阅，汇总金币/打工/股市排行榜
  - 个人日报：私聊推送完整的个人数据报告
  - 群管理可开启/关闭本群日报功能

### 变更

- 重构 `_do_daily_settlement` 为完整的日报生成+发送引擎
- 日报发送时间默认 23:00（可自定义）

---

## v0.1.4 (2026-04-25)

### 新增

- **股票系统 v2 - 趋势与基本面机制**：
  - 每只股票有长期趋势：20-120小时方向性移动（±10%-50%幅度）
  - 每小时价格变动 = 基础随机幅度 + 趋势贡献 + 随机事件
  - 交易时段 8:00-20:00，休市价格冻结
  - 8:00 开盘重置开盘价，日内记录高低
  - 涨跌停限制（按股票波动率）
  - 界面显示今日涨跌幅，红涨绿跌（A股习惯）

---

## v0.1.3 (2026-04-25)

### 新增

- **P1-1 股票交易系统完整实现**：
  - `/股市` 查看实时行情（代码/名称/价格）
  - `/股市 买 代码 数量` 买入股票（支持补仓，平均成本计算）
  - `/股市 卖 代码 数量` 卖出股票（显示盈亏）
  - `/股市 持股` 查看持仓详情（成本/当前价/盈亏）
  - 支持 5 只股票：牛马科技(NIU001)、搬砖集团(BAN002)、外卖快送(WAI003)、程序员培训(COD004)、海豹银行(SEA005)

---

## v0.1.2 (2026-04-25)

### 新增

- **压力系统 v2**：引入身体疲劳/精神压力双轨机制（0-100%）
  - 体力型工作 → 身体疲劳（搬砖/清洁工/外卖/快递/工地小工）
  - 脑力/技能型工作 → 精神压力（文员/数据录入/客服/会计/程序员/销售/项目经理/技术总监/顾问）
  - 压力分段惩罚：>50% 开始效率衰减，90-100% 强制力竭
  - 空闲衰减 2%/小时，娱乐可针对性缓解压力
- **Debuff 系统**：低属性持续 10 分钟未恢复时触发 debuff
  - 虚弱/疲劳/抑郁/饥饿/疾病，对应收入或恢复效率惩罚
  - Buff 可抵消 debuff
- **强制住院机制**：健康 ≤ 0 时强制入院，每小时消耗 30 金币恢复

### 变更

- 被动恢复调整：属性博弈为核心的策略系统替代原有无脑恢复

---

## v0.1.1 (2026-04-25)

### 修复

- **P0-1** 清理重复命令注册：归档 `basic.py` `checkin.py` `work.py` `learn.py` `entertain.py` `life.py` 至 `src/commands/legacy/`，现仅 `interactive.py` 生效
- **P0-4** 修复 `modules/tick.py` 中状态字符串 `"FREE"` 死代码，统一使用 `UserStatus.FREE.value`

### 变更

- 版本号统一为 V0.1.1
- `metadata.yaml` / `main.py @register` / `README.md` 版本信息同步
- 更新 README 架构图，注明 `legacy/` 目录

---

## v0.0.11 (2026-04-??)

- 重构为模块化命令 + DAO 数据访问
- 引入 KV 存储替代部分 JSON 文件操作
- 新增 Tick 系统（分钟级结算）
- 新增 HTML 卡片渲染

---

## v0.0.1 (2026-03-??)

- 初始版本
- 基础功能：签到、打工、学习、娱乐、饮食、住所、股市
