# 架构 (Architecture)

> 牛马人生 (astrbot_plugin_niumalife) — AstrBot 插件。
> 最后更新：2026-09-05（反映现状 + 改造路线）

## 一句话

**LLM/QQ → main.py 命令路由 → src/commands 业务逻辑 → src/data 仓储 → modules/renderer 统一卡片渲染 → aiocqhttp 自动 file:// 发送**。

**通知路径**：tick 后台 → MessageSender.notify() (内存优先 + KV 持久化兜底) → _notify_queue → _notification_consumer → 缓存 event.send() → aiocqhttp。详见 `src/ui/message_sender.py`。

---

## 实际模块图（含 2026-09-05 现状标注）

```
┌──────────────────────────────────────────────────────────────────┐
│ 入口层                                                           │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ QQ/QQbot ──► AstrMessageEvent                                │ │
│ └──────────┬───────────────────────────────────────────────────┘ │
└────────────┼────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ L1  入口层  main.py                                              │
│ • 59 个 @filter.command / @filter.llm_tool 装饰器               │
│ • 持 self._store / self._renderer / self._parser                │
│ • 启动 _notification_consumer 后台 task                          │
│ ⚠ [问题] 装饰器注册 vs _build_keyword_handlers vs keyword_routes│
│   三处同步, 容易漏注册 → SESSION_INIT.md 已规定但靠人工         │
└────┬─────────────────┬─────────────────┬─────────────────────────┘
     │                 │                 │
     ▼                 ▼                 ▼
┌─────────┐    ┌─────────────┐    ┌──────────────┐
│commands/│    │ modules/    │    │ modules/     │
│ *.py    │    │ tick.py     │    │ company_*.py │
│ 25 个   │    │ (整点属性)  │    │ (公司/股市)   │
│handler  │    │             │    │              │
└────┬────┘    └──────┬──────┘    └──────────────┘
     │                │
     │           ┌────▼─────────────────┐
     │           │ _notify_catch /      │
     │           │ _notify_empty /      │
     │           │ _notify_line_break   │
     │           │ ↓                    │
     │           │ renderer._render()   │
     │           │ ↓                    │
     │           │ _notify_queue →      │
     │           │ _notification_       │
     │           │ consumer →           │
     │           │ event.send()         │
     │           └──────────────────────┘
     │
     ├─────────────────────────┐
     ▼                         ▼
┌──────────────────┐    ┌────────────────────┐
│ src/data/        │    │ src/market/        │
│ user_repository  │    │ (自动注册 + 价格)   │
│ (DAO)            │    │                    │
│                  │    │                    │
│ ⚠ [问题] 嵌套深  │    │                    │
│ user["fishing"]  │    │                    │
│   ["fish_caught"]│    │                    │
│ 散落各文件       │    │                    │
└────────┬─────────┘    └────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ L4  数据存储                          │
│ AstrBot KV (SQLite) data_v4.db       │
│ scope = 海獭 🦦/niumalife            │
│ scope_id 自动 fallback (v3→v4 迁移) │
└──────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════
                    渲染子系统（问题重灾区）
═══════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────┐
│ modules/renderer.py                                               │
│                                                                  │
│  src/commands/*.py 调用方式:                                     │
│   try:                                                           │
│     url = await renderer.render_xxx(...)                         │
│   except: pass                                                   │
│   if url: yield event.image_result(url)                          │
│   else: yield event.plain_result(text)   ← fallback 文本         │
│                                                                  │
│  ⚠ [问题 1] 每个命令自己 try/except → 真实异常被吞              │
│  ⚠ [问题 2] render_xxx 签名漂移 → 调用方参数不匹配 TypeError    │
│     例: render_fishing_catch 缺 exp_gain → 钓鱼通知无卡片        │
│         render_backpack 缺 filter_label → 背包 fallback         │
│  ⚠ [问题 3] 模板字段缺失 → 各 render_xxx 手动补 30+ 字段        │
│                                                                  │
│  _render(card_type, data, height, width, full_page)             │
│    ↓                                                            │
│  _LocalRenderer.render()  ← 9/5 新增, 优先路径                │
│    • Jinja2 Environment(undefined=_SilentUndefined)              │
│    • jinja2.meta.find_undeclared_variables 自动补默认            │
│    • Playwright 本地 Chromium 截图                              │
│    • viewport width/height/full_page 三参数                     │
│    ↓ 失败 fallback                                              │
│  html_renderer.render_custom_template()  ← AstrBot 网络 T2I    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
         │                                      │
         ▼                                      ▼
┌────────────────────────┐         ┌──────────────────────────┐
│ modules/templates.py   │         │ modules/renderer.py      │
│ CardType 枚举 + HTML   │         │ _LocalRenderer           │
│ 16 个模板              │         │ • Playwright sync API    │
│                        │         │ • Chromium path 探测     │
│ ⚠ [问题 4] 模板用      │         │ • 高度估算 + JS          │
│ categories/tier_groups │         │   document.body.height   │
│ /fixed_items 三种模式  │         │   → full_page 截图       │
│ 但 render_xxx 没全支持 │         │                          │
└────────────────────────┘         └──────────────────────────┘
                                              │
                                              ▼
                                  ┌──────────────────────────┐
                                  │ _local_path_to_url()     │
                                  │ 返回绝对路径             │
                                  │ ↓                        │
                                  │ aiocqhttp 自动转 file://│
                                  │ ↓                        │
                                  │ QQ 客户端显示图片        │
                                  └──────────────────────────┘


═══════════════════════════════════════════════════════════════════
              通知子系统 (9/6 重构: 缓存按 session_key + 持久化)
═══════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────┐
│ src/ui/message_sender.py — MessageSender (统一发送器)           │
│                                                                  │
│  3 个核心入口:                                                   │
│    send_card(event, card_type, data, fallback_text)              │
│      → async generator, 业务方 async for r in sender.send_card()│
│      → 渲染成功 → yield image_result, 失败 → yield plain_result │
│    send_text(event, text, at_user=False)                         │
│      → at_user=True 自动加 @nickname 前缀                        │
│    notify(user_id, msg_type, text, image_url)                    │
│      → tick 后台推送, 走 _notify_queue + 持久化 KV              │
│                                                                  │
│  tick 完成 / 低属性警告场景:                                     │
│    tick → messenger.notify_xxx() →                              │
│    messenger._send_platform_message() (旧路径, 已并入 sender) →  │
│    plugin._notify_queue.put((uid, chain, session_key))           │
│                                                                  │
│  consumer:                                                       │
│    main._notification_consumer 循环消费 queue                    │
│    按 session_key 查 _recent_events[sk] → event.send(chain)      │
│                                                                  │
│  ⚠ 缓存按 session_key (9/6):                                    │
│    旧: _recent_event[user_id] (用户跨群串通知)                    │
│    新: _recent_events[session_key] (群 A 钓鱼/群 B 闲聊分开缓存) │
│    session_key = "platform_id|session_type|session_id"           │
│                                                                  │
│  ⚠ 持久化 (9/6):                                                │
│    缓存 event 在 → 立即 send                                      │
│    缓存 event 不在 / send 失败 → 写 KV "_pending_notify:user_id" │
│    玩家下次进 session_key 对应会话 → _cache_event 触发           │
│    sender.flush_pending_for_session() 补发, 加 ⚠️ 延迟提示       │
│    24h 软上限: 超时清理 + 不补发                                  │
│    图片: 渲染时复制到 NOTIFY_IMG_DIR 持久化, 避免 /tmp 清理失效  │
│                                                                  │
│  ⚠ 已废除:                                                      │
│    - 1h 过期保护 (玩家可能忙几小时, 通知必须送达)                 │
│    - StarTools.send_message (platform_id 解析 bug)               │
│    - MessageSession.from_str (字符串格式错)                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 数据流（以 `/钓鱼` 为例）

```
用户: /钓鱼
  ↓
main.py: fishing_cmd handler
  ↓
src/commands/fishing.py: run_fishing_logic
  ↓
src/fishing/fishing_manager.py: start_fishing()
  user = self.plugin._store.get_user(user_id)
  detail = {"spot": "湖泊", "start_tick": now, ...}
  user["status"] = "钓鱼中"
  await self.plugin._store.update_user(user_id, user)
  ↓
  [整点 tick]
modules/tick.py: _do_fishing_tick()
  ↓
fishing_manager.roll_catch()
  catch = {"fish": {...}, "weight": 0.42, "size_label": "大", "estimated_price": 28}
  ↓
  _notify_catch(user_id, user, catch, new_title, levelup_info)
  ↓
  renderer.render_fishing_catch(user, catch, new_title, exp_gain=42)
  ↓  [修复后]
  url = "/tmp/tmp_xxx.png"
  ↓
  self._notify_queue.put_nowait({
    "user_id": user_id,
    "msg": MessageChain.at("@user").message(" 🐟 上钩了！").file_image(url)
  })
  ↓
main.py:_notification_consumer
  event = self._recent_event.get(user_id)
  await event.send(msg_chain)
  ↓
aiocqhttp: 自动 file:// URL
  ↓
QQ 客户端: 显示卡片图片
```

---

## 现状诊断（9/5）

| 层级 | 设计 | 实际 | 差距 |
|---|---|---|---|
| **L1 入口** | main.py 装饰器 + thin wrapper | ✓ | 但 keyword_routes 3 处同步靠人工 |
| **L2 数据** | 唯一 Repository | ⚠ | 嵌套字段散落 (`user["fishing"]["fish_caught"]`) |
| **L3 业务** | 纯函数 + 渲染调用 | ✗ | 25 个文件重复 try/except + 散落 fallback |
| **L4 渲染** | 单一 _render 入口 | ✓ | 但签名漂移 (exp_gain/filter_label/tier_groups) + 模板字段缺失靠补 |
| **L4 消息分发** | 单一 message_sender | ✗ | 3 套发送路径并存 (image_result/star_tools/event.send) |
| **L5 模板** | CardType + HTML | ✓ | 但 categories/tier_groups/fixed_items 3 模式没全支持 |

---

## 改造路线（按优先级）

### P0（已完成 9/5 + 9/6）

**1. 统一消息分发器** ✅ 9/5 + 9/6 完成
- `src/ui/message_sender.py` — MessageSender
- `send_card()` / `send_text()` / `notify()` 三个入口
- 25 个命令可改用 `await sender.send_card(...)` 替代散落 try/except
- 9/6 改进: 缓存按 session_key 分组 + 持久化 KV 补发机制

**2. 统一渲染数据契约** ✅ 9/5 完成
- `modules/renderer.py` 加 `ViewSpec(card_type, required_fields, defaults)`
- `_render` 在调用前 `data.update(spec.defaults)` 兜底
- 14 个 CardType 已声明契约
- 测试 `tests/test_view_specs.py` 守护

### P1（中等改动，半天）

**3. 数据访问统一** ✅ 9/5 + 9/6 完成
- `src/data/user_view.py` — typed accessor 层 (30+ 公共函数)
- 消除 `user["fishing"]["fish_caught"]` 嵌套散落
- 老数据完全兼容, 缺字段自动补默认
- 测试 `tests/test_user_view.py` 守护

**4. 渲染函数签名冻结** (下一轮)
- 写 `docs/RENDER_API.md` 冻结所有 render_xxx 签名
- 加 `tests/test_render_signatures.py` 自动检查调用方参数

**5. 内容注册中心** ✅ 9/6 完成 (新加)
- `src/data/content_registry.py` — ContentRegistry + ContentDef
- 统一 6 类配置数据 (164 物品 / 91 鱼 / 99 课程 / 14 工作 / 7 住所 / 30 娱乐)
- 11 种 actions 替代散落 if/elif
- 自动推导: JSON 没 actions 字段时根据 category/slot/price 自动给出合理默认
- 测试 `tests/test_content_registry.py` 守护

### P2（大重构，1-2 天）

**5. 命令注册中心**
- 单文件声明 `{command_name: handler_path, views, render_fn}`
- 启动时自动注册 `@filter.command` + keyword_routes
- 干掉"3 处同步"问题

**6. 通知系统重构**
- `_notification_consumer` 加自动 fallback：如果 1h 缓存失效，从 `tick` 数据构造离线通知
- `modules/messenger.py` 改用 `event.send` 而非 StarTools

---

## 关键约定（保持不变）

| 场景 | 怎么做 |
|---|---|
| 加新鱼 | `data/config/fishes.json` + `market.json` 可选 |
| 加新命令 | `src/commands/<name>.py` + main.py 注册 + keyword_routes.py |
| 加新卡片 | `modules/templates.py` 加 CardType + HTML + `modules/renderer.py` 加 `render_xxx` + **注册到 ViewSpec** |
| 修 bug | `CHANGELOG.md` + `tests/test_<bug>.py` 复现 |
| 数据 schema | `docs/DECISIONS.md` 写 ADR |
