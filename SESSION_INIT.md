# SESSION_INIT.md

> **新对话第一份要读的文件**。比 session_search 快。
> 包含：当前 plugin 状态、上次 session 在做什么、后续待办、验证命令。

---

## 当前 plugin 状态（9/6 晚）

**plugin**: `astrbot_plugin_niumalife` (牛马人生)
**路径**: `/home/alex/data/plugins/astrbot_plugin_niumalife/`
**AstrBot**: PID 348896 (bash) + 348912 (python), 9/6 17:37 启动, ASTRBOT_RELOAD=1 模式
**重启命令**: `pgrep -f "astrbot run" | xargs kill && sleep 3 && cd /home/alex && ASTRBOT_RELOAD=1 nohup /home/alex/.local/bin/astrbot run >> /home/alex/astrbot.log 2>&1 &`

---

## 最近工作 (上次 session)

**主题**: MessageSender + 持久化通知系统 + ContentRegistry

**已落地**:
- `src/ui/message_sender.py` — MessageSender 统一发送器 (ARCHITECTURE P0 #1)
- `main.py:_cache_event` — 缓存按 session_key 分组 (9/6 改进), 解决多群通知发错窗口
- `main.py:_notification_consumer` — 移除 1h 过期, 按 session_key 路由
- `modules/messenger.py` — 缓存键兼容新旧, 用 _extract_session_key 推断
- 持久化 KV 兜底: 缓存失效时通知写入 `_pending_notify:user_id`, 玩家下次进对应会话补发
- 24h 软上限 + 5 档延迟提示 (数分钟/半小时/数小时/半天) + 持久化图片目录 `/home/alex/data/niumalife_cache/notify_imgs/`
- `src/data/content_registry.py` — 内容注册中心 (ContentRegistry + ContentDef)
- 自动推导 actions: JSON 没 actions 字段时根据 category/slot/price 自动给出, 老 JSON 完全不动
- 6 个测试文件, **88/88 单元测试全过**

---

## 新对话开局 5 步（< 30 秒）

```bash
# 1. 确认 AstrBot 健康
python /home/alex/data/plugins/astrbot_plugin_niumalife/scripts/check_health.py

# 2. 跑单元测试确认无回归
python /home/alex/data/plugins/astrbot_plugin_niumalife/tests/test_market.py

# 3. 查历史改动 (CHANGELOG.md)
cat /home/alex/data/plugins/astrbot_plugin_niumalife/CHANGELOG.md | head -30

# 4. 看架构 + 工作流
cat /home/alex/data/plugins/astrbot_plugin_niumalife/ARCHITECTURE.md | head -60
cat /home/alex/data/plugins/astrbot_plugin_niumalife/WORKFLOW.md | head -60

# 5. (可选) 找旧 session 详情
session_search query="niumalife 卖 fish" session_id=20260901_120919_478a32dc
```

---

## 当前健康检查已知 warnings

1. **2 个 AstrBot 进程** (4703 bash + 4756 python) —— 不影响功能, 想清理可以 `kill 4703`
2. **老 scope 51 个用户 KV 未迁移** —— fallback 没触发? 让用户发 `/卖` 会触发 fallback
3. **主用户 748455427 当前 scope 无数据** —— 同上, 需要发 `/卖` 触发 fallback

---

## 待办（用户已知未完成）

- [ ] 用户发 `/卖` 验证 fallback 实际触发（看日志 [fallback] FOUND legacy data）
- [ ] 验证 SELL_OVERVIEW 卡片正确显示 3 条鱼 + 估值
- [ ] 清理 AstrBot 重复进程
- [ ] 把 fallback 调试日志（[fallback] warning）改为仅 debug level
- [ ] 业务逻辑从 commands/ 抽到 domain/ （长期）
- [ ] CI/cron 自动跑测试 + check_health

---

## 调试常用查询

```bash
# 用户背包数据
sqlite3 /home/alex/data/data_v4.db "SELECT value FROM preferences WHERE scope='plugin' AND scope_id='海獭 🦦/niumalife' AND key='user:748455427'"

# 老 scope 数据 (fallback 找这里)
sqlite3 /home/alex/data/data_v4.db "SELECT value FROM preferences WHERE scope='plugin' AND scope_id='海獭 🦦/astrbot_plugin_niumalife' AND key='user:748455427'"

# 当前 plugin 加载状态
grep "Loading plugin astrbot_plugin_niumalife" /home/alex/astrbot.log | tail -3

# 强制 reload plugin
rm -rf /home/alex/data/plugins/astrbot_plugin_niumalife/{src,modules}/**/__pycache__
touch /home/alex/data/plugins/astrbot_plugin_niumalife/main.py

# 清渲染缓存 (改卡片后)
rm -f /home/alex/data/niumalife_cache/render_cache.json
```

---

## 切忌

- ❌ 改代码前**先 grep ARCHITECTURE.md / WORKFLOW.md / CHANGELOG.md** 看现状
- ❌ 调试时**不要先猜问题在哪** —— 先 SQL 查 data_v4.db 看实际数据
- ❌ 改完代码**直接发 QQ 消息验证** —— 先跑单元测试
- ❌ 怀疑 DAO/Repository 层封装 —— 用户已强调"架构不是应该正常封装了DAO吗"，这层一般没问题
- ❌ 假设 plugin_id scope 算法会变 —— v4 是 `{author}/{name.lower()}`

---

## 数据 schema 关键约定

- 鱼: `data/config/fishes.json` (含 base_price, weight_range, rarity)
- 食物: `data/config/foods.json` (含 price, restore_*)  
- 物品: `data/config/items.json` (含 price, category, effects)
- market 覆盖: `data/config/market.json` (仅给特殊定价/波动率)
- KV 存储: sqlite `preferences` 表, scope='plugin', scope_id=plugin_id

**加新鱼/食物/装备**只改对应的 source json, market.json 留给手动覆盖。