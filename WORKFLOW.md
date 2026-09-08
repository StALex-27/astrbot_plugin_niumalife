# 工作流 (Workflow)

> 标准流程：**先看数据 → 写测试 → 改代码 → 测试通过 → 更新 CHANGELOG**。

## 铁律

1. **不要"猜问题在哪"**。每个 bug 调试前先 SQL 查数据，看清楚实际值
2. **不要重复发消息验证**。改完代码先 `pytest` 跑离线测试，**通过后才发命令**
3. **每次改动必须更新 CHANGELOG.md**（一行就够）
4. **加新内容只改 source json**。market.json 仅用于覆盖

---

## 加新内容（鱼/食物/装备/房产/股票）

```
1. 改 data/config/<类别>.json     ← 单一来源
   例: data/config/fishes.json 加一个对象 {name, base_price, weight_range, ...}
2. 跑 tests/test_market.py         ← 验证自动注册生效
3. /卖 或 /背包                    ← UI 验证 (人工)
```

**注意**：
- `base_price`/`price` 必须 > 0，否则自动注册跳过
- market.json 想给某物品特殊定价 → 在对应 category 加同名 entry 覆盖

---

## 加新命令

```bash
# 1. src/commands/<name>.py
#    9/6+: 优先用 sender.send_card() / sender.send_text() 替代 try/except + yield
#    9/5+: data 准备用 UserView.view_for_xxx_card(user) (避免 user["fishing"]["xx"] 嵌套)
#    9/6+: 需要查物品/鱼配置时用 ContentRegistry.instance().find_by_id(...)
async def run_<name>_logic(event, store, parser, sender):
    user = await store.get_user(event.get_sender_id())
    async for r in sender.send_card(
        event, CardType.XXX,
        UserView.view_for_xxx_card(user),  # ← 9/5 推荐
        fallback_text="加载失败, 请重试",
    ):
        yield r

# 2. src/commands/__init__.py
# 3. main.py  (按 WORKFLOW 流程, 5 处同步注册)
# 4. tests/test_<name>.py  (至少 1 个边界用例)
# 5. CHANGELOG.md 加 [Add]
# 6. 关键词路由注册
```

> **9/5+ 推荐**: 25 个命令改用 `sender.send_card()` 后, 每个命令文件少 5-10 行 try/except 样板。

## 加新物品/鱼/食物/装备/课程/工作/住所/娱乐/股票

```bash
1. 改 data/config/<类别>.json     # source of truth
2. ContentRegistry 自动加载       # 9/6+ 无需手动注册
3. 跑 tests/test_content_registry.py  # 验证 actions 自动推导正确
4. 跑 tests/test_market.py        # 验证 sellable 自动包含
5. /商店 / /卖 / /背包             # UI 验证
```

**注册原理 (ContentRegistry)**:
- 启动时一次加载所有 source json → 构造 `ContentDef` (frozen dataclass)
- 自动推导 `actions`: 根据 `category`/`slot`/`price`/`subcategory`
  - food → `eat` / medicine → `use` / enchant → `enchant`
  - 有 slot → `equip` / fishing slot → `use_in_fishing`
  - price > 0 → `buy + sell`
- 想覆盖推导结果? 在 JSON 加 `"actions": ["eat", "buy", "sell"]` 显式声明

**好处**:
- 加新物品时不用改 market/shop/fishing/eat 多处
- 业务层 `reg.supports_action(item_id, "eat")` 替代散落 `if category == "food"`

## 加新通知场景 (tick 完成 / 低属性警告)

```python
# 在 tick.py 或业务模块:
from src.ui.message_sender import MessageSender  # 通过 plugin._sender 拿

async def some_tick():
    # 旧:
    # await self.plugin._messenger.notify_work_complete(user_id, ...)
    # 新 (推荐):
    await self.plugin._sender.notify(
        user_id, "work_complete",
        text=f"📋 {job_name} 已完成!",
        image_url=card_url,  # 自动持久化到 NOTIFY_IMG_DIR
    )
```

**自动处理**:
- 缓存 event 在 → 立即 send
- 缓存 event 不在 / send 失败 → 持久化 KV, 玩家进对应会话时补发
- 24h 软上限 + ⚠️ 延迟提示 (数分钟/半小时/数小时/半天)

---

## 加关键词触发（群聊纯文支持）

**所有 `@filter.command` 命令都必须同时注册关键词路由，否则群聊发"卖"等纯文无响应**。

群聊消息处理流：

```
群聊纯文 → AstrBot filter: is_at_or_wake_command=False → command filter 拒绝
        → 走 on_keyword_msg (niumalife)
        → KeywordRouter.match_command_route(message)
        → _keyword_handlers[action] 查找 handler
        → 执行
```

**3 处必改**：

1. **`modules/keyword_routes.py`** — `_KEYWORD_ROUTES` tuple 加：
   ```python
   KeywordRoute(keyword="卖", action="sell_cmd"),
   ```

2. **`main.py`** — `_keyword_handlers` dict 加：
   ```python
   return {
       ...
       "sell_cmd": self.sell_cmd,  # ← 别忘了
   }
   ```

3. **CHANGELOG.md** — 加 `[Add] keyword route: 卖 -> sell_cmd`

**验证方法**：
- 私聊发"卖" → `@filter.command` 触发（command filter）
- 群聊发"卖" → `on_keyword_msg` + KeywordRouter 触发
- **两个都要测**，少一处就是 bug

**反例**（9/3 卖命令事件）：只改了 keyword_routes.py + `@filter.command`，忘了 `_keyword_handlers` dict → 群聊静默失败，私聊正常。

---

## 加新卡片类型

```
1. modules/templates.py
   class CardType(str, Enum):
       ...
       XXX = "xxx"

2. modules/templates.py (模板 dict)
   CARD_TEMPLATES = {
       ...
       CardType.XXX: """
   <div class="card">...</div>
   """,
   }

3. modules/renderer.py
   async def render_xxx(self, data: dict) -> dict:
       # 处理模板需要的字段
       return {...}

4. 调用处:
   url = await self._render(CardType.XXX, data, height=预估高度, full_page=True)
```

**关键**：所有 `_render` 调用**必须** `full_page=True`（两步法）。4 个小卡片（ERROR/SUCCESS/HELP/GENERIC）保留 viewport 截屏。

---

## 修 Bug

```
1. 现象描述（用户报告或自测）
2. 先查数据: SQL data_v4.db → 看实际值
3. 写测试: tests/test_<bug>.py 复现
4. 跑测试 → 确认失败 (red)
5. 改代码 → 修 bug
6. 跑测试 → 确认通过 (green)
7. CHANGELOG.md 加 [Fix] 一行
```

**调试模板**：
```
[现象]   用户发 /卖 返回空
[数据]   inventory 有 3 条鱼: 小虾/白条/小鲫鱼
[假设]   market.json 没收录这 3 条 → can_sell() 返回 False
[验证]   python -c "import json; m=json.loads(open('market.json').read()); print('小虾' in m['fish'])"
[修复]   market.py 加 fallback (5 行)
[测试]   tests/test_market.py:def test_can_sell_fallback_fish()
```

---

## 加新功能（如成就系统/季节系统）

```
1. docs/DECISIONS.md 加 ADR
   ## ADR-XXX: 成就系统
   - 状态: Proposed / Accepted / Deprecated
   - 背景: 玩家需要 xxx
   - 决策: 用 x 数据结构
   - 后果: 需要 y 修改
2. ARCHITECTURE.md 更新模块图
3. src/domain/<feature>.py        ← 纯业务 (不依赖 AstrBot event)
4. tests/test_<feature>.py        ← 离线测试
5. src/commands/<feature>.py      ← thin wrapper
6. CHANGELOG.md 加 [Decision] 行
```

---

## 调试常用查询

```bash
# 当前 AstrBot PID
pgrep -fa "astrbot run" | grep -v grep

# plugin 是否加载成功
grep "Loading plugin astrbot_plugin_niumalife" /home/alex/astrbot.log | tail -3

# 最近 reload
grep "Detected file changes for plugin\|Removed handler" /home/alex/astrbot.log | tail -10

# 用户背包 (user_id 替换实际值)
sqlite3 /home/alex/data/data_v4.db \
  "SELECT value FROM preferences WHERE scope='plugin' AND scope_id='海獭 🦦/niumalife' AND key='user:748455427'"
# → Python 解析: json.loads()['val']['inventory']

# 当前生效 scope_id 的所有 keys
sqlite3 /home/alex/data/data_v4.db \
  "SELECT key FROM preferences WHERE scope='plugin' AND scope_id='海獭 🦦/niumalife'"

# 清缓存 (修卡片/模板后)
rm -f /home/alex/data/niumalife_cache/render_cache.json

# 强制 reload plugin
touch /home/alex/data/plugins/astrbot_plugin_niumalife/main.py

# plugin 掉线后恢复
pgrep -f "astrbot run" | xargs kill
sleep 3
cd /home/alex && ASTRBOT_RELOAD=1 nohup /home/alex/.local/bin/astrbot run >> /home/alex/astrbot.log 2>&1 &
```

---

## 健康检查

`scripts/check_health.py`（每分钟 cron 或手动跑）：
- AstrBot 进程存活 + PID 唯一
- plugin 加载成功（无 ImportError）
- 所有用户 inventory 字段存在
- 缓存目录可写
- 输出异常才通知，避免噪音