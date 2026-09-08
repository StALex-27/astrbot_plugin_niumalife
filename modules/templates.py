"""
HTML卡片模板模块
牛马人生项目

使用Jinja2模板语法 + Grid布局实现美观卡片
参考 astrbot_plugin_atrifeed 的 clip 渲染方式
"""

# ============================================================
# 完整HTML模板（固定380px宽度）
# ============================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 380px; background: transparent; height: auto !important; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(145deg, #1e1e3f 0%, #2d2d5a 100%); height: auto !important; }
.card { width: 380px; background: linear-gradient(145deg, #1e1e3f 0%, #2d2d5a 50%, #1a1a35 100%); border-radius: 16px; overflow: hidden; color: #fff; position: relative; }
.shop-card { width: 880px; box-sizing: border-box; }
.card-top { height: 3px; background: linear-gradient(90deg, #4facfe, #00f2fe); }
.header { display: grid; grid-template-columns: 48px 1fr auto; gap: 10px; padding: 10px; background: rgba(0,0,0,0.25); }
.avatar { width: 48px; height: 48px; border-radius: 10px; border: 2px solid rgba(79,195,247,0.5); object-fit: cover; }
.header-info { display: flex; flex-direction: column; justify-content: center; }
.username { font-size: 14px; font-weight: 700; color: #fff; }
.user-id { font-size: 9px; color: rgba(255,255,255,0.5); margin-top: 2px; }
.gold-box { background: rgba(254,202,87,0.15); border: 1px solid rgba(254,202,87,0.3); border-radius: 8px; padding: 5px 10px; text-align: center; min-width: 70px; }
.gold-label { font-size: 8px; color: rgba(254,202,87,0.8); text-transform: uppercase; }
.gold-value { font-size: 16px; font-weight: 800; color: #feca57; }
.main { padding: 10px; }
.section { background: rgba(255,255,255,0.03); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
.section-title { font-size: 10px; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
.section-title::before { content: ''; width: 3px; height: 10px; background: linear-gradient(180deg, #4facfe, #00f2fe); border-radius: 2px; }
.section-sub-title { font-size: 11px; color: rgba(255,255,255,0.6); margin: 10px 0 6px 0; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.row:last-child { border-bottom: none; }
.row-label { font-size: 11px; color: rgba(255,255,255,0.6); }
.row-value { font-size: 12px; font-weight: 600; color: #fff; }
.row-value.highlight { color: #4fc3f7; }
.row-value.gold { color: #feca57; }
.row-value.warning { color: #ffa502; }
.row-value.success { color: #2ed573; }
.list-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.list-item:last-child { border-bottom: none; }
.list-item-left { display: flex; align-items: center; gap: 8px; }
.list-item-emoji { font-size: 16px; }
.list-item-name { font-size: 12px; font-weight: 600; color: #fff; }
.list-item-desc { font-size: 10px; color: rgba(255,255,255,0.5); }
.list-item-right { text-align: right; }
.list-item-value { font-size: 11px; font-weight: 600; color: #feca57; }
.shop-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.shop-grid-item { background: rgba(255,255,255,0.04); border-radius: 10px; padding: 8px 10px 6px; border: 1px solid rgba(255,255,255,0.06); display: grid; grid-template-columns: 48px 1fr; grid-template-rows: auto auto auto auto; gap: 3px 8px; align-items: start; }
.shop-grid-item:hover { background: rgba(255,255,255,0.08); }
.grid-icon-box { grid-row: 1 / 5; grid-column: 1 / 2; width: 48px; height: 48px; background: linear-gradient(145deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.04) 100%); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 26px; line-height: 1; border: 1px solid rgba(255,255,255,0.12); box-shadow: inset 0 1px 0 rgba(255,255,255,0.15), 0 2px 4px rgba(0,0,0,0.3); position: relative; }
.lock-badge { position: absolute; bottom: -4px; right: -4px; font-size: 12px; background: rgba(0,0,0,0.6); border-radius: 6px; padding: 1px 3px; line-height: 1; }
.grid-name-row { grid-column: 2 / 3; grid-row: 1 / 2; display: flex; align-items: center; gap: 5px; min-width: 0; overflow: hidden; }
.grid-name { font-size: 13px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; }
.grid-tag { font-size: 9px; color: rgba(255,255,255,0.5); background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 4px; flex-shrink: 0; }
.grid-tier-row { grid-column: 2 / 3; grid-row: 2 / 3; display: flex; align-items: center; gap: 5px; min-width: 0; overflow: hidden; }
.grid-tier-tag { font-size: 9px; color: rgba(79,195,247,0.9); background: rgba(79,195,247,0.12); padding: 1px 4px; border-radius: 3px; flex-shrink: 0; }
.grid-effects { font-size: 10px; color: #74b9ff; line-height: 1.3; word-break: break-all; overflow-wrap: anywhere; flex: 1; min-width: 0; }
.grid-price-big { grid-column: 2 / 3; grid-row: 3 / 4; justify-self: end; font-size: 16px; font-weight: 700; background: linear-gradient(90deg, #ff9a44, #feca57); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1.1; }
.grid-desc { grid-column: 2 / 3; grid-row: 4 / 5; font-size: 10px; color: rgba(255,255,255,0.5); line-height: 1.3; word-break: break-all; overflow-wrap: anywhere; }
.list-item-sub { font-size: 9px; color: rgba(255,255,255,0.4); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
.grid-item { background: rgba(255,255,255,0.03); border-radius: 8px; padding: 10px; text-align: center; }
.grid-item-title { font-size: 9px; color: rgba(255,255,255,0.4); text-transform: uppercase; margin-bottom: 4px; }
.grid-item-value { font-size: 18px; font-weight: 800; color: #fff; }
.grid-item-value.gold { color: #feca57; }
.grid-item-value.highlight { color: #4fc3f7; }
.attrs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.attr-item { background: rgba(255,255,255,0.03); border-radius: 8px; padding: 8px; }
.attr-item.full { grid-column: span 2; }
.attr-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
.attr-name { font-size: 10px; color: rgba(255,255,255,0.6); }
.attr-value { font-size: 11px; font-weight: 700; }
.attr-bar { height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden; }
.attr-fill { height: 100%; border-radius: 2px; }
.attr-health .attr-fill { background: linear-gradient(90deg, #ff6b6b, #ee5a5a); }
.attr-strength .attr-fill { background: linear-gradient(90deg, #ffa502, #ff7f00); }
.attr-energy .attr-fill { background: linear-gradient(90deg, #7bed9f, #2ed573); }
.attr-mood .attr-fill { background: linear-gradient(90deg, #ff6b81, #ff4757); }
.attr-satiety .attr-fill { background: linear-gradient(90deg, #feca57, #ff9f43); }
.buff-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.buff-tag { display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; background: rgba(79,195,247,0.15); border: 1px solid rgba(79,195,247,0.3); border-radius: 20px; font-size: 10px; color: #4fc3f7; }
.skill-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.skill-tag { display: inline-flex; align-items: center; padding: 3px 8px; background: rgba(255,255,255,0.05); border-radius: 6px; font-size: 10px; color: rgba(255,255,255,0.8); }
.skill-tag.active { background: rgba(255,215,0,0.15); border: 1px solid rgba(255,215,0,0.3); color: #ffd700; }
.warning-box { background: rgba(255,165,2,0.1); border: 1px solid rgba(255,165,2,0.3); border-radius: 8px; padding: 8px; text-align: center; color: #ffa502; font-size: 11px; }
.success-box { background: rgba(46,213,115,0.1); border: 1px solid rgba(46,213,115,0.3); border-radius: 8px; padding: 8px; text-align: center; color: #2ed573; font-size: 11px; }
.footer { padding: 8px 10px; background: rgba(0,0,0,0.2); text-align: center; }
.footer-text { font-size: 9px; color: rgba(255,255,255,0.3); }
.center { text-align: center; }
.big-emoji { font-size: 48px; margin: 10px 0; }
.help-section { margin-bottom: 8px; }
.help-title { font-size: 9px; font-weight: 600; color: #4fc3f7; text-transform: uppercase; margin-bottom: 4px; }
.help-items { display: flex; flex-wrap: wrap; gap: 2px 8px; }
.help-item { font-size: 10px; color: rgba(255,255,255,0.7); width: calc(50% - 4px); }
.help-cmd { color: #fff; font-weight: 500; }
.error-card { background: linear-gradient(145deg, #2d1f1f, #3d1f1f); }
.rank-list { }
.rank-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.rank-item:last-child { border-bottom: none; }
.rank-num { width: 20px; font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.4); text-align: center; }
.rank-num.top1 { color: #ffd700; }
.rank-num.top2 { color: #c0c0c0; }
.rank-num.top3 { color: #cd7f32; }
.rank-name { flex: 1; font-size: 11px; color: #fff; }
.rank-value { font-size: 11px; font-weight: 600; color: #feca57; }
</style>
</head>
<body>
{{ content }}
</body>
</html>"""


# ============================================================
# 消息类型枚举
# ============================================================

class CardType:
    PROFILE = "profile"
    STATUS = "status"
    CHECKIN = "checkin"
    CHECKIN_STATS = "checkin_stats"
    BUFF_LIST = "buff_list"
    JOB_LIST = "job_list"
    JOB_START = "job_start"
    JOB_POOL = "job_pool"
    JOB_COMPLETE = "job_complete"
    COURSE_LIST = "course_list"
    COURSE_START = "course_start"
    FOOD_LIST = "food_list"
    FISHING_GEAR = "fishing_gear"
    FISHING_SPOTS = "fishing_spots"
    EAT = "eat"
    RESIDENCE = "residence"
    HOUSING_LIST = "housing_list"
    DAILY_REPORT = "daily_report"
    MY_STATS = "my_stats"
    ENTERTAINMENT_LIST = "entertainment_list"
    HELP = "help"
    ERROR = "error"
    SUCCESS = "success"
    GENERIC = "generic"
    STOCK_MARKET = "stock_market"
    STOCK_HOLDINGS = "stock_holdings"
    BACKPACK = "backpack"
    SHOP = "shop"
    FISHING_CARD = "fishing_card"
    FISH_Market = "fish_market"
    FISH_DEX = "fish_dex"
    SELL_RESULT = "sell_result"
    SELL_OVERVIEW = "sell_overview"
    ENCHANT = "enchant"
    ITEM_DETAIL = "item_detail"


# ============================================================
# Jinja2 模板内容
# ============================================================

CONTENT_TEMPLATES = {

    CardType.PROFILE: """
    <div class="card">
        <div class="card-top"></div>
        <div class="header">
            <img class="avatar" src="{{ avatar_url }}" alt="avatar">
            <div class="header-info">
                <div class="username">{{ nickname }}</div>
                <div class="user-id">Lv.{{ user_level }} · {{ status }}</div>
            </div>
            <div class="gold-box">
                <div class="gold-label">金币</div>
                <div class="gold-value">{{ gold }}</div>
            </div>
        </div>
        <div class="main">
            {% if warnings_html %}
            <div class="warning-box">
                {{ warnings_html | safe }}
            </div>
            {% endif %}

            {% if action_label %}
            <div class="success-box">
                🎯 {{ action_label }}
                {% if action_progress >= 0 %}
                <div class="attr-bar" style="margin-top:6px;">
                    <div class="attr-fill" style="width:{{ action_progress }}%; background:linear-gradient(90deg,#4facfe,#00f2fe);"></div>
                </div>
                {% endif %}
            </div>
            {% endif %}

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <!-- 左列 -->
                <div>
                    <div class="section">
                        <div class="section-title">🏠 基本信息</div>
                        <div class="row">
                            <div class="row-label">住所</div>
                            <div class="row-value">{{ residence_emoji }} {{ residence }}</div>
                        </div>
                        {% if rent_per_day > 0 %}
                        <div class="row">
                            <div class="row-label">日租</div>
                            <div class="row-value warning">{{ rent_per_day }}</div>
                        </div>
                        {% endif %}
                        <div class="row">
                            <div class="row-label">累计赚</div>
                            <div class="row-value gold">{{ total_gold_earned }}</div>
                        </div>
                        <div class="row">
                            <div class="row-label">历史最高</div>
                            <div class="row-value">{{ peak_gold }}</div>
                        </div>
                    </div>

                    {% if fish_count > 0 %}
                    <div class="section">
                        <div class="section-title">🎣 钓鱼</div>
                        {% if fish_title %}
                        <div style="text-align:center;margin-bottom:6px;">
                            <span style="display:inline-block;padding:2px 8px;background:rgba(254,202,87,0.15);border:1px solid rgba(254,202,87,0.4);border-radius:20px;font-size:10px;color:#feca57;">🏅 {{ fish_title }}</span>
                        </div>
                        {% endif %}
                        <div class="row">
                            <div class="row-label">累计</div>
                            <div class="row-value">{{ fish_count }} 次</div>
                        </div>
                        <div class="row">
                            <div class="row-label">卖鱼</div>
                            <div class="row-value gold">{{ fish_value }}</div>
                        </div>
                        <div class="row">
                            <div class="row-label">种类</div>
                            <div class="row-value">{{ fish_species }}</div>
                        </div>
                        {% if biggest_fish %}
                        <div class="row">
                            <div class="row-label">最大</div>
                            <div class="row-value gold" style="font-size:11px;">{{ biggest_fish }} {{ biggest_fish_weight_str }} · {{ biggest_fish_length_str }}</div>
                        </div>
                        {% endif %}
                    </div>
                    {% endif %}

                    {% if skills %}
                    <div class="section">
                        <div class="section-title">📚 技能 ({{ skills|length }}{% if skills_more > 0 %}+{{ skills_more }}{% endif %})</div>
                        {% for skill in skills %}
                        <div class="row">
                            <div class="row-label">
                                <span style="color:{% if skill.tier == '高级' %}#ffd700{% elif skill.tier == '中级' %}#4fc3f7{% else %}rgba(255,255,255,0.7){% endif %};">{{ skill.name }}</span>
                            </div>
                            <div class="row-value highlight" style="font-size:11px;">Lv.{{ skill.level }}</div>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                </div>

                <!-- 右列 -->
                <div>
                    <div class="section">
                        <div class="section-title">❤️ 属性</div>
                        <div class="attr-item attr-health" style="margin-bottom:4px;padding:6px;">
                            <div class="attr-header"><span class="attr-name">❤️ 健康</span><span class="attr-value">{{ health }}</span></div>
                            <div class="attr-bar"><div class="attr-fill" style="width:{{ health }}%"></div></div>
                        </div>
                        <div class="attr-item attr-strength" style="margin-bottom:4px;padding:6px;">
                            <div class="attr-header"><span class="attr-name">💪 体力</span><span class="attr-value">{{ strength }}</span></div>
                            <div class="attr-bar"><div class="attr-fill" style="width:{{ strength }}%"></div></div>
                        </div>
                        <div class="attr-item attr-energy" style="margin-bottom:4px;padding:6px;">
                            <div class="attr-header"><span class="attr-name">⚡ 精力</span><span class="attr-value">{{ energy }}</span></div>
                            <div class="attr-bar"><div class="attr-fill" style="width:{{ energy }}%"></div></div>
                        </div>
                        <div class="attr-item attr-mood" style="margin-bottom:4px;padding:6px;">
                            <div class="attr-header"><span class="attr-name">😊 心情</span><span class="attr-value">{{ mood }}</span></div>
                            <div class="attr-bar"><div class="attr-fill" style="width:{{ mood }}%"></div></div>
                        </div>
                        <div class="attr-item attr-satiety" style="padding:6px;">
                            <div class="attr-header"><span class="attr-name">🍖 饱食</span><span class="attr-value">{{ satiety }}</span></div>
                            <div class="attr-bar"><div class="attr-fill" style="width:{{ satiety }}%"></div></div>
                        </div>
                    </div>

                    <div class="section">
                        <div class="section-title">📊 今日 + 签到</div>
                        <div class="row">
                            <div class="row-label">打工</div>
                            <div class="row-value gold">+{{ today_gold_work }}</div>
                        </div>
                        <div class="row">
                            <div class="row-label">消费</div>
                            <div class="row-value warning">-{{ today_gold_spent }}</div>
                        </div>
                        <div class="row">
                            <div class="row-label">连胜</div>
                            <div class="row-value highlight">{{ streak }}天</div>
                        </div>
                        <div class="row">
                            <div class="row-label">总签到</div>
                            <div class="row-value">{{ checkin_days_total }}天</div>
                        </div>
                        <div class="row">
                            <div class="row-label">欧气</div>
                            <div class="row-value">{{ luck_emoji }} {{ luck_name }}</div>
                        </div>
                        <div class="row">
                            <div class="row-label">经验</div>
                            <div class="row-value highlight">{{ total_exp }} EXP</div>
                        </div>
                    </div>

                    {% if buff_count > 0 %}
                    <div class="section">
                        <div class="section-title">✨ Buff ({{ buff_count }})</div>
                        <div class="buff-tags" style="display:flex;flex-wrap:wrap;gap:4px;">{{ buff_tags | safe }}</div>
                    </div>
                    {% endif %}
                </div>
            </div>
        </div>
        <div class="footer"><div class="footer-text">牛马人生 v3.0 · /鱼塘 /背包 /装备 /设置</div></div>
    </div>
    """,


    CardType.STATUS: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">状态监控</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">金币</div>
            <div class="gold-value">{{ gold }}</div>
        </div>
    </div>
    <div class="main">
        <div class="grid-2">
            <div class="grid-item"><div class="grid-item-title">当前状态</div><div class="grid-item-value highlight">{{ status }}</div></div>
            <div class="grid-item"><div class="grid-item-title">居住</div><div class="grid-item-value">{{ residence }}</div></div>
        </div>
        
        {% if progress %}
        <div class="section">
            <div class="section-title">当前进度</div>
            <div class="row"><span class="row-label">{{ progress.action }}</span><span class="row-value">{{ progress.current }}/{{ progress.total }} 小时</span></div>
        </div>
        {% endif %}
        
        <div class="section">
            <div class="section-title">属性状态</div>
            <div class="attrs-grid">
                <div class="attr-item attr-health">
                    <div class="attr-header"><span class="attr-name">❤️</span><span class="attr-value">{{ health }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ health }}%"></div></div>
                </div>
                <div class="attr-item attr-strength">
                    <div class="attr-header"><span class="attr-name">💪</span><span class="attr-value">{{ strength }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ strength }}%"></div></div>
                </div>
                <div class="attr-item attr-energy">
                    <div class="attr-header"><span class="attr-name">⚡</span><span class="attr-value">{{ energy }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ energy }}%"></div></div>
                </div>
                <div class="attr-item attr-mood">
                    <div class="attr-header"><span class="attr-name">😊</span><span class="attr-value">{{ mood }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ mood }}%"></div></div>
                </div>
                <div class="attr-item attr-satiety full">
                    <div class="attr-header"><span class="attr-name">🍖</span><span class="attr-value">{{ satiety }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ satiety }}%"></div></div>
                </div>
            </div>
        </div>
        
        {% if buff_tags %}
        <div class="section">
            <div class="section-title">生效 Buff</div>
            <div class="buff-tags">{{ buff_tags }}</div>
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">牛马人生 v3.0</div></div>
</div>
""",


    CardType.CHECKIN: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">每日签到</div>
        </div>
    </div>
    <div class="main center">
        {% if is_new_user %}
        <div class="success-box" style="margin-bottom:10px">🎉 首次注册成功！</div>
        {% endif %}
        
        <div class="big-emoji">{{ luck_emoji }}</div>
        <div style="font-size:20px;font-weight:800;margin-bottom:2px">{{ luck_name }}</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.85);margin:8px 16px 12px;line-height:1.6;white-space:pre-wrap;text-align:center">{{ luck_desc }}</div>
        
        <div class="grid-2" style="margin-bottom:12px">
            <div class="grid-item"><div class="grid-item-title">本次获得</div><div class="grid-item-value gold">+{{ gold }}</div></div>
            <div class="grid-item"><div class="grid-item-title">连续签到</div><div class="grid-item-value highlight">{{ streak }} 天</div></div>
        </div>
        
        {% if streak_bonus %}
        <div class="success-box" style="margin-bottom:10px">🔥 连续签到奖励 +{{ streak_bonus }} 金币</div>
        {% endif %}
        
        {% if drop %}
        <div class="section"><div class="section-title">🎁 幸运掉落</div>{{ drop }}</div>
        {% endif %}
        
        {% if already %}
        <div style="color:rgba(255,255,255,0.5);margin-top:10px">今日已签到，明天再来~</div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">明天再来签到吧~ 🌙</div></div>
</div>
""",


    CardType.CHECKIN_STATS: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">签到统计</div>
        </div>
    </div>
    <div class="main">
        <div class="grid-2">
            <div class="grid-item"><div class="grid-item-title">总签到</div><div class="grid-item-value">{{ total_days }} 天</div></div>
            <div class="grid-item"><div class="grid-item-title">累计金币</div><div class="grid-item-value gold">{{ total_gold }}</div></div>
            <div class="grid-item"><div class="grid-item-title">幸运掉落</div><div class="grid-item-value">{{ lucky_drops }} 次</div></div>
            <div class="grid-item"><div class="grid-item-title">最高连续</div><div class="grid-item-value highlight">{{ max_streak }} 天</div></div>
        </div>
        
        <div class="section">
            <div class="section-title">欧气统计</div>
            <div class="row"><span class="row-label">🤑 超级欧皇</span><span class="row-value">{{ super_lucky }} 次</span></div>
            <div class="row"><span class="row-label">😄 欧皇</span><span class="row-value">{{ lucky }} 次</span></div>
            <div class="row"><span class="row-label">😐 普通人</span><span class="row-value">{{ normal }} 次</span></div>
            <div class="row"><span class="row-label">😣 非酋</span><span class="row-value">{{ unlucky }} 次</span></div>
            <div class="row"><span class="row-label">💀 超级非酋</span><span class="row-value">{{ super_unlucky }} 次</span></div>
        </div>
    </div>
    <div class="footer"><div class="footer-text">继续坚持签到吧~ 💪</div></div>
</div>
""",


    CardType.BUFF_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">Buff 列表</div>
        </div>
    </div>
    <div class="main">
        {% if buffs %}
        <div class="section">
            {% for buff in buffs %}
            <div class="row">
                <span class="row-label">{{ buff.emoji }} {{ buff.name }}</span>
                <span class="row-value">{{ buff.desc }}</span>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="center" style="padding:30px;color:rgba(255,255,255,0.5)">
            暂无生效的 Buff<br>通过签到或活动获取吧~
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">Buff来源：签到掉落 | 购买 | 活动</div></div>
</div>
""",


    CardType.JOB_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">工作列表</div>
        </div>
    </div>
    <div class="main">
        {% if physical_jobs %}
        <div class="section">
            <div class="section-title">💪 体力型工作</div>
            {% for job in physical_jobs %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ job.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ job.name }}</div>
                        <div class="list-item-sub">{{ job.skill }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ job.gold }}金/时</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if mental_jobs %}
        <div class="section">
            <div class="section-title">🧠 脑力型工作</div>
            {% for job in mental_jobs %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ job.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ job.name }}</div>
                        <div class="list-item-sub">{{ job.skill }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ job.gold }}金/时</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /打工 <工作名> <小时数></div></div>
</div>
""",


    CardType.JOB_START: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">开始工作</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">收入</div>
            <div class="gold-value">+{{ expected_gold }}</div>
        </div>
    </div>
    <div class="main">
        <div class="center" style="padding:10px 0">
            <div style="font-size:32px">{{ job_emoji }}</div>
            <div style="font-size:16px;font-weight:700;margin-top:4px">{{ job_name }}</div>
        </div>
        
        <div class="section">
            <div class="section-title">工作信息</div>
            <div class="row"><span class="row-label">⏰ 时长</span><span class="row-value">{{ hours }} 小时</span></div>
            <div class="row"><span class="row-label">💰 预计收入</span><span class="row-value gold">+{{ expected_gold }} 金币</span></div>
            <div class="row"><span class="row-label">📚 预计经验</span><span class="row-value">+{{ expected_exp }} EXP</span></div>
        </div>
        
        <div class="section">
            <div class="section-title">消耗预估</div>
            <div class="row"><span class="row-label">💪 体力</span><span class="row-value warning">-{{ consume_strength }}</span></div>
            <div class="row"><span class="row-label">⚡ 精力</span><span class="row-value warning">-{{ consume_energy }}</span></div>
            <div class="row"><span class="row-label">🍖 饱食</span><span class="row-value warning">-{{ consume_satiety }}</span></div>
        </div>
        
        {% if active_buffs %}
        <div class="success-box" style="margin-bottom:10px">✨ {{ active_buffs }}</div>
        {% endif %}
    </div>
</div>
""",


    CardType.JOB_POOL: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">委托池</div>
        </div>
    </div>
    <div class="main">
        {% if pools %}
        <div class="section">
            <div class="section-title">📋 公共委托</div>
            {% for job in pools %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ job.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ job.title }}</div>
                        <div class="list-item-sub">{{ job.company_emoji }} {{ job.company_name }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value gold">+{{ job.base_reward }}</div>
                    <div class="list-item-sub">{{ job.duration_hours }}h {{ job.diff_icon }}{{ job.difficulty }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if recommended %}
        <div class="section">
            <div class="section-title">🏢 公司推荐</div>
            {% for company in recommended %}
            <div style="margin-bottom:10px">
                <div style="font-size:12px;font-weight:600;margin-bottom:4px">{{ company.emoji }} {{ company.name }} <span style="opacity:0.6">Lv.{{ company.level }} {{ company.level_name }}</span></div>
                {% for job in company.jobs %}
                <div class="list-item">
                    <div class="list-item-left">
                        <span class="list-item-emoji">{{ job.emoji }}</span>
                        <div>
                            <div class="list-item-name">{{ job.title }}</div>
                            <div class="list-item-sub">{{ job.diff_icon }}{{ job.difficulty }}</div>
                        </div>
                    </div>
                    <div class="list-item-right">
                        <div class="list-item-value gold">+{{ job.base_reward }}</div>
                        <div class="list-item-sub">{{ job.duration_hours }}h</div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if not pools and not recommended %}
        <div class="center" style="padding:20px;color:rgba(255,255,255,0.5)">暂无委托，请稍后再来~</div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">/打工 &lt;编号/名称&gt; 接受委托</div></div>
</div>
""",


    CardType.JOB_COMPLETE: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">委托完成</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">获得</div>
            <div class="gold-value">+{{ total_gold }}</div>
        </div>
    </div>
    <div class="main">
        <div class="center" style="padding:8px 0">
            <div style="font-size:40px">{{ grade_emoji }}</div>
            <div style="font-size:20px;font-weight:800;margin-top:4px">{{ grade_name }}</div>
            <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-top:4px">综合分 {{ total_score }}</div>
        </div>

        <div class="grid-2" style="margin-bottom:10px">
            <div class="grid-item"><div class="grid-item-title">金币</div><div class="grid-item-value gold">+{{ gold }}</div></div>
            <div class="grid-item"><div class="grid-item-title">好感度</div><div class="grid-item-value">{{ favor_change|+ }}</div></div>
        </div>

        {% if exp_str %}
        <div class="row" style="margin-bottom:8px"><span class="row-label">📈 经验</span><span class="row-value">{{ exp_str }}</span></div>
        {% endif %}

        <div class="section">
            <div class="section-title">📊 六维评价</div>
            <div class="row"><span class="row-label">⚡ 效率</span><span class="row-value">{{ efficiency }}</span></div>
            <div class="row"><span class="row-label">⭐ 质量</span><span class="row-value">{{ quality }}</span></div>
            <div class="row"><span class="row-label">💪 压力</span><span class="row-value">{{ stress_bonus|+ }}</span></div>
            <div class="row"><span class="row-label">😊 心情</span><span class="row-value">{{ mood_bonus|+ }}</span></div>
            <div class="row"><span class="row-label">🎯 技能</span><span class="row-value">{{ skill_bonus|+ }}</span></div>
            <div class="row"><span class="row-label">✨ Buff</span><span class="row-value">{{ buff_bonus|+ }}</span></div>
        </div>
    </div>
    <div class="footer"><div class="footer-text">辛苦了~ 💪</div></div>
</div>
""",


    CardType.COURSE_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">课程列表</div>
        </div>
    </div>
    <div class="main">
        {% if courses %}
        <div class="section">
            {% for course in courses %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">📚</span>
                    <div>
                        <div class="list-item-name">{{ course.name }}</div>
                        <div class="list-item-sub">{{ course.type }} | {{ course.skill }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ course.cost }}金/时</div>
                    <div class="list-item-sub">+{{ course.exp }}EXP</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /学习 <课程名> <小时数></div></div>
</div>
""",


    CardType.FOOD_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">食物列表</div>
        </div>
    </div>
    <div class="main">
        {% if foods %}
        <div class="section">
            {% for food in foods %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ food.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ food.name }}</div>
                        <div class="list-item-sub">{{ food.effects }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ food.price }}金</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /吃 <食物名></div></div>
</div>
""",


    CardType.EAT: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">购买食物</div>
        </div>
    </div>
    <div class="main center">
        <div style="font-size:40px;margin:10px 0">{{ food_emoji }}</div>
        <div style="font-size:16px;font-weight:700">{{ food_name }}</div>
        
        <div class="section" style="margin-top:12px">
            <div class="section-title">效果</div>
            <div class="row"><span class="row-label">💪 体力</span><span class="row-value success">+{{ restore_strength }}</span></div>
            <div class="row"><span class="row-label">⚡ 精力</span><span class="row-value success">+{{ restore_energy }}</span></div>
            <div class="row"><span class="row-label">😊 心情</span><span class="row-value success">+{{ restore_mood }}</span></div>
            <div class="row"><span class="row-label">❤️ 健康</span><span class="row-value success">+{{ restore_health }}</span></div>
            <div class="row"><span class="row-label">🍖 饱食</span><span class="row-value success">+{{ restore_satiety }}</span></div>
        </div>
        
        <div class="success-box">购买成功！</div>
    </div>
</div>
""",


    CardType.RESIDENCE: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">我的住所</div>
        </div>
    </div>
    <div class="main">
        <div class="center" style="padding:10px 0">
            <div style="font-size:32px">{{ res_emoji }}</div>
            <div style="font-size:16px;font-weight:700;margin-top:4px">{{ res_name }}</div>
            <div style="font-size:10px;color:rgba(255,255,255,0.5)">{{ res_type }}</div>
        </div>
        
        <div class="section">
            <div class="section-title">住所信息</div>
            <div class="row"><span class="row-label">类型</span><span class="row-value">{{ res_type }}</span></div>
            <div class="row"><span class="row-label">{{ cost_label }}</span><span class="row-value">{{ cost_value }}</span></div>
        </div>
        
        <div class="section">
            <div class="section-title">被动恢复</div>
            <div class="row"><span class="row-label">💪 体力/小时</span><span class="row-value success">+{{ passive_strength }}</span></div>
            <div class="row"><span class="row-label">⚡ 精力/小时</span><span class="row-value success">+{{ passive_energy }}</span></div>
        </div>
    </div>
    <div class="footer"><div class="footer-text">使用 /房产列表 查看更多</div></div>
</div>
""",


    CardType.HOUSING_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">房产列表</div>
        </div>
    </div>
    <div class="main">
        {% if rentals %}
        <div class="section">
            <div class="section-title">🏠 可租房产</div>
            {% for house in rentals %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ house.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ house.name }}</div>
                        <div class="list-item-sub">{{ house.desc }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ house.rent }}金/天</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
        
        {% if purchases %}
        <div class="section">
            <div class="section-title">🏡 可购房产</div>
            {% for house in purchases %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ house.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ house.name }}</div>
                        <div class="list-item-sub">{{ house.desc }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ house.price }}金</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /租房 <名称> 或 /买房 <名称></div></div>
</div>
""",

    CardType.ENTERTAINMENT_LIST: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">娱乐列表</div>
        </div>
    </div>
    <div class="main">
        {% if entertainments %}
        <div class="section">
            {% for ent in entertainments %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ ent.emoji }}</span>
                    <div>
                        <div class="list-item-name">{{ ent.name }}</div>
                        <div class="list-item-sub">{{ ent.type }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">{{ ent.cost }}金/时</div>
                    <div class="list-item-sub">😊+{{ ent.gain_mood }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /娱乐 <名称> <小时></div></div>
</div>
""",

    CardType.DAILY_REPORT: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">{{ report_date }}</div>
        </div>
    </div>
    <div class="main">
        <div class="section">
            <div class="section-title">💰 金币排行</div>
            <div class="rank-list">
                {% for item in gold_ranking %}
                <div class="rank-item">
                    <span class="rank-num {% if loop.index <= 3 %}top{{ loop.index }}{% endif %}">{{ loop.index }}</span>
                    <span class="rank-name">{{ item.name }}</span>
                    <span class="rank-value">{{ item.value }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
        
        {% if work_ranking %}
        <div class="section">
            <div class="section-title">💼 工作排行</div>
            <div class="rank-list">
                {% for item in work_ranking %}
                <div class="rank-item">
                    <span class="rank-num {% if loop.index <= 3 %}top{{ loop.index }}{% endif %}">{{ loop.index }}</span>
                    <span class="rank-name">{{ item.name }}</span>
                    <span class="rank-value">{{ item.value }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">每日 {{ settlement_time }} 自动结算</div></div>
</div>
""",


    CardType.MY_STATS: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">我的统计</div>
        </div>
    </div>
    <div class="main">
        <div class="grid-2">
            <div class="grid-item"><div class="grid-item-title">今日收入</div><div class="grid-item-value gold">+{{ today_income }}</div></div>
            <div class="grid-item"><div class="grid-item-title">今日支出</div><div class="grid-item-value warning">-{{ today_expense }}</div></div>
            <div class="grid-item"><div class="grid-item-title">工作时长</div><div class="grid-item-value">{{ work_hours }} 小时</div></div>
            <div class="grid-item"><div class="grid-item-title">学习时长</div><div class="grid-item-value">{{ learn_hours }} 小时</div></div>
        </div>
    </div>
    <div class="footer"><div class="footer-text">{{ report_date }}</div></div>
</div>
""",


    CardType.HELP: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">指令帮助</div>
        </div>
    </div>
    <div class="main">
        <div class="help-section">
            <div class="help-title">📌 基础指令</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/我要当牛马</span></div>
                <div class="help-item"><span class="help-cmd">/档案</span></div>
                <div class="help-item"><span class="help-cmd">/状态</span></div>
                <div class="help-item"><span class="help-cmd">/帮助</span></div>
            </div>
        </div>
        <div class="help-section">
            <div class="help-title">🎯 签到系统</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/签到</span></div>
                <div class="help-item"><span class="help-cmd">/签到统计</span></div>
                <div class="help-item"><span class="help-cmd">/我的buff</span></div>
            </div>
        </div>
        <div class="help-section">
            <div class="help-title">💼 工作指令</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/工作列表</span></div>
                <div class="help-item"><span class="help-cmd">/打工</span></div>
                <div class="help-item"><span class="help-cmd">/取消工作</span></div>
            </div>
        </div>
        <div class="help-section">
            <div class="help-title">📚 学习指令</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/课程列表</span></div>
                <div class="help-item"><span class="help-cmd">/学习</span></div>
                <div class="help-item"><span class="help-cmd">/取消学习</span></div>
            </div>
        </div>
        <div class="help-section">
            <div class="help-title">🍜 生活指令</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/食物列表</span></div>
                <div class="help-item"><span class="help-cmd">/吃</span></div>
                <div class="help-item"><span class="help-cmd">/睡觉</span></div>
            </div>
        </div>
        <div class="help-section">
            <div class="help-title">🏠 居住指令</div>
            <div class="help-items">
                <div class="help-item"><span class="help-cmd">/住所</span></div>
                <div class="help-item"><span class="help-cmd">/房产列表</span></div>
                <div class="help-item"><span class="help-cmd">/租房/买房</span></div>
            </div>
        </div>
    </div>
    <div class="footer"><div class="footer-text">牛马人生 v3.0</div></div>
</div>
""",


    CardType.ERROR: """
<div class="card error-card">
    <div style="padding:30px;text-align:center">
        <div style="font-size:48px;margin-bottom:10px">❌</div>
        <div style="font-size:14px;font-weight:600;color:#ff6b6b">{{ error_title }}</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-top:6px">{{ error_message }}</div>
    </div>
</div>
""",


    CardType.SUCCESS: """
<div class="card">
    <div style="padding:30px;text-align:center">
        <div style="font-size:48px;margin-bottom:10px;color:#2ed573">✅</div>
        <div style="font-size:14px;font-weight:600;color:#2ed573">{{ success_message }}</div>
    </div>
</div>
""",


    CardType.GENERIC: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">消息</div>
        </div>
    </div>
    <div class="main">{{ content }}</div>
</div>
""",


    CardType.STOCK_MARKET: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">{{ status }}</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">金币</div>
            <div class="gold-value">{{ gold }}</div>
        </div>
    </div>
    <div class="main">
        <div class="section">
            <div class="section-title">📈 股票行情</div>
            {% for stock in stocks %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">📊</span>
                    <div>
                        <div class="list-item-name">{{ stock.name }}</div>
                        <div class="list-item-sub">{{ stock.code }}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">¥{{ stock.price }}</div>
                    <div class="list-item-sub {% if stock.change_val > 0 %}success{% elif stock.change_val < 0 %}warning{% endif %}">{{ stock.change_str }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <div class="footer"><div class="footer-text">使用 /股市 买/卖 代码 数量</div></div>
</div>
""",


    CardType.STOCK_HOLDINGS: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">我的持股</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">总盈亏</div>
            <div class="gold-value {% if total_profit >= 0 %}gold{% else %}warning{% endif %}">{{ total_profit_str }}</div>
        </div>
    </div>
    <div class="main">
        {% if holdings %}
        <div class="section">
            {% for holding in holdings %}
            <div class="list-item" style="flex-wrap:wrap">
                <div class="list-item-left" style="width:100%">
                    <span class="list-item-emoji">📈</span>
                    <div style="flex:1">
                        <div class="list-item-name">{{ holding.code }} {{ holding.name }}</div>
                        <div class="list-item-sub">{{ holding.amount }}股 | 成本¥{{ holding.cost_price }} | 现价¥{{ holding.current_price }}</div>
                    </div>
                </div>
                <div class="list-item-right" style="width:100%;margin-top:4px">
                    <div class="list-item-value {% if holding.profit >= 0 %}gold{% else %}warning{% endif %}">{{ holding.profit_str }}</div>
                    <div class="list-item-sub {% if holding.today_change >= 0 %}success{% else %}warning{% endif %}">今日 {{ holding.today_change_str }} | 总 {{ holding.profit_pct_str }}</div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="center" style="padding:30px;color:rgba(255,255,255,0.5)">
            暂无持股<br>使用 /股市 买 <代码> <数量> 购入
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /股市 卖 <代码> <数量></div></div>
</div>
""",


    CardType.BACKPACK: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">背包 · {{ item_count }} 件{% if filter_label %} · {{ filter_label }}{% endif %}{% if is_fishing %} · 🎣 <span style="color:#feca57;">钓鱼中 @ {{ fishing_spot }}</span>{% endif %}</div>
        </div>
    </div>
    <div class="main">
        {% if items %}
        {# 9/7: 6 列布局 + 整数重量 #}
        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:6px;padding:6px;">
            {% for item in items %}
            <div style="position:relative;background:rgba(255,255,255,0.05);border:2px solid {{ item.rarity_color }};border-radius:8px;padding:6px;text-align:center;min-height:60px;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                <div style="font-size:22px;line-height:1;">{{ item.emoji }}</div>
                <div style="font-size:8px;color:{{ item.rarity_color }};font-weight:{% if item.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};margin-top:2px;line-height:1.1;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ item.name }}</div>
                {% if item.is_fish %}
                    <div style="font-size:7px;color:{{ item.rarity_color }};line-height:1;margin-top:1px;">{{ item.weight_str }}</div>
                {% elif item.quantity > 1 %}
                    <div style="position:absolute;top:1px;right:1px;background:{{ item.rarity_color }};color:#fff;font-size:8px;padding:1px 3px;border-radius:4px;">x{{ item.quantity }}</div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="center" style="padding:30px;color:rgba(255,255,255,0.5)">
            🎒 背包是空的！<br>通过签到或购买获取物品
        </div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">使用 /吃 物品名 食用 | /装备 装备名</div></div>
</div>
""",

    CardType.FISHING_GEAR: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">🎣 我的渔具{% if is_fishing %} · <span style="color:#feca57;">钓鱼中 @ {{ fishing_spot }}</span>{% endif %}</div>
        </div>
    </div>
    <div class="main">
        {# 9/7: 装备状态分两列布局 #}
        <div class="section">
            <div class="section-title">⚙️ 装备状态</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            {% for slot in gear_slots %}
            <div class="list-item" style="background:rgba(255,255,255,0.04);border-radius:8px;padding:8px;">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ slot.emoji }}</span>
                    <div style="min-width:0;">
                        <div class="list-item-name" style="font-size:11px;">{{ slot.name }}{% if slot.item_id %}: <span style="color:rgba(255,255,255,0.9);font-size:10px;">{{ slot.item_id }}</span>{% endif %}</div>
                        {% if slot.effect %}<div class="list-item-sub" style="font-size:9px;">⚡ {{ slot.effect }}</div>{% endif %}
                        {% if slot.desc %}<div class="list-item-sub" style="color:rgba(255,255,255,0.55);font-style:italic;font-size:9px;">📖 {{ slot.desc }}</div>{% endif %}
                    </div>
                </div>
            </div>
            {% endfor %}
            </div>
        </div>
        <div class="section">
            <div class="section-title">🎯 套装效果</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                <div class="row"><div class="row-label">🎣 中鱼率</div><div class="row-value success">+{{ effects.fishing_bonus_pct_int }}%</div></div>
                <div class="row"><div class="row-label">⭐ 稀有</div><div class="row-value success">+{{ effects.rare_bonus_pct_int }}%</div></div>
                <div class="row"><div class="row-label">⚖️ 竿承重</div><div class="row-value">{{ capacity_fishing_rod_int }}kg</div></div>
                <div class="row"><div class="row-label">🧵 线承重</div><div class="row-value">{{ capacity_fishing_line_int }}kg</div></div>
                <div class="row" style="grid-column:1 / -1;"><div class="row-label">🪱 鱼钩食性</div><div class="row-value">{{ diet_zh }}</div></div>
            </div>
        </div>
        <div class="section">
            <div class="section-title">🎒 背包渔具 ({{ inventory_gear_count }})</div>
            {# 9/7: 背包渔具两列布局 #}
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            {% for inv in inventory_gear %}
            <div class="list-item" style="background:rgba(255,255,255,0.04);border-radius:8px;padding:6px 8px;">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ inv.emoji }}</span>
                    <div style="min-width:0;">
                        <div class="list-item-name" style="font-size:11px;">{{ inv.name }}</div>
                        <div class="list-item-sub" style="font-size:9px;">{{ inv.slot_zh }}{% if inv.desc %} · {{ inv.desc }}{% endif %}</div>
                    </div>
                </div>
                <div class="list-item-right">
                    <div class="list-item-value">#{{ inv.idx }}</div>
                </div>
            </div>
            {% endfor %}
            </div>
        </div>
    </div>
    <div class="footer">
        <div class="footer-text">📦 /渔具 装 <名字/序号>  卸 <栏位></div>
    </div>
</div>
""",

    CardType.FISHING_SPOTS: """
<div class="card">
    <div class="card-top"></div>
    <!-- 9/8: 右上角钓鱼等级方框 (正方形圆角) + 底部 exp 进度条 -->
    <div style="position:absolute;top:14px;right:14px;z-index:10;display:inline-flex;flex-direction:column;align-items:center;gap:4px;padding:8px 10px;background:linear-gradient(135deg,rgba(79,195,247,0.35),rgba(0,242,254,0.35));border:2px solid rgba(79,195,247,0.8);border-radius:14px;box-shadow:0 4px 14px rgba(79,195,247,0.5);min-width:64px;">
        <span style="font-size:24px;color:#4fc3f7;font-weight:900;line-height:1;text-shadow:0 0 8px rgba(79,195,247,0.6);">Lv.{{ skill_level }}</span>
        {% if skill_progress is defined and skill_progress %}
            {% if skill_progress.is_max %}
            <span style="font-size:8px;color:rgba(255,255,255,0.7);font-weight:700;letter-spacing:0.5px;">✨ 满级</span>
            {% else %}
            {% set exp_pct = ((skill_progress.current_exp / skill_progress.next_level_exp) * 100) if skill_progress.next_level_exp > 0 else 0 %}
            <div style="height:4px;width:52px;background:rgba(0,0,0,0.45);border-radius:2px;overflow:hidden;">
                <div style="height:100%;width:{{ exp_pct }}%;background:linear-gradient(90deg,#4fc3f7,#00f2fe);box-shadow:0 0 6px rgba(79,195,247,0.7);"></div>
            </div>
            {% endif %}
        {% endif %}
    </div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <!-- 9/8: 钓鱼称号 (在 username 下方) -->
            {% if fish_title %}
            <div style="font-size:10px;color:#feca57;font-weight:700;margin-top:1px;letter-spacing:0.5px;">{{ fish_title }}</div>
            {% endif %}
            <!-- 9/8: user-id 行 - 地点已移到下方进度条内, 此处仅显示状态 -->
            <div class="user-id">
                {% if is_fishing %}🎣 钓鱼中
                {% else %}🎣 选择水域
                {% endif %}
            </div>
        </div>
    </div>
    <div class="main">
        <!-- 9/8: 钓鱼状态条 (如果正在钓鱼) -->
        {% if is_fishing and fishing_status %}
        <div class="section" style="background:linear-gradient(135deg,rgba(79,195,247,0.15),rgba(0,242,254,0.15));border:1px solid rgba(79,195,247,0.4);border-radius:8px;padding:10px 14px;margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="font-size:13px;font-weight:700;color:#4fc3f7;">🎣 正在 {{ fishing_status.spot_name }} 钓鱼中</span>
                <span style="font-size:11px;color:rgba(255,255,255,0.6);">{{ fishing_status.ticks_done }}/{{ fishing_status.max_ticks }} ticks</span>
            </div>
            <div style="height:6px;background:rgba(0,0,0,0.3);border-radius:3px;overflow:hidden;">
                <div style="height:100%;width:{{ fishing_status.progress_pct }}%;background:linear-gradient(90deg,#4fc3f7,#00f2fe);box-shadow:0 0 8px rgba(79,195,247,0.6);"></div>
            </div>
        </div>
        {% endif %}
        <!-- 9/8: 6 渔具栏 (3列x2行) -->
        <div class="section">
            <div class="section-title">🔧 渔 具 栏</div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;">
                {% for gear in gear_slots %}
                <div style="padding:6px 8px;background:{% if gear.missing and gear.required %}rgba(255,107,107,0.15){% else %}rgba(255,255,255,0.05){% endif %};border:1px solid {% if gear.missing and gear.required %}#ff6b6b{% elif gear.required %}rgba(79,195,247,0.4){% else %}rgba(255,255,255,0.1){% endif %};border-radius:6px;">
                    <div style="font-size:10px;color:{% if gear.missing and gear.required %}#ff6b6b{% else %}rgba(255,255,255,0.6){% endif %};font-weight:600;">{{ gear.label }}{% if gear.required %}<span style="color:#ff6b6b;">*</span>{% endif %}</div>
                    <div style="font-size:12px;color:{% if gear.missing and gear.required %}#ff6b6b{% else %}#fff{% endif %};font-weight:700;margin-top:2px;">{{ gear.name }}</div>
                    <div style="font-size:9px;color:rgba(255,255,255,0.5);margin-top:1px;">{{ gear.risk }}</div>
                </div>
                {% endfor %}
            </div>
        </div>
        <!-- 9/8: 风险提示 + 缺失警告 (按鱼钩 size_class 超载%) -->
        {% if missing_required %}
        <div class="section" style="background:rgba(255,107,107,0.1);border:1px solid #ff6b6b;border-radius:6px;padding:8px 12px;margin-bottom:8px;">
            <div style="font-size:11px;font-weight:700;color:#ff6b6b;">⚠️ 缺少必备渔具: {{ missing_required | join('、') }}</div>
        </div>
        {% elif break_risk != '无' %}
        <div class="section" style="background:{% if break_risk == '极高' %}rgba(255,71,87,0.15){% elif break_risk == '高' %}rgba(255,107,107,0.12){% elif break_risk == '中' %}rgba(254,202,87,0.12){% else %}rgba(46,213,115,0.1){% endif %};border:1px solid {% if break_risk == '极高' %}#ff4757{% elif break_risk == '高' %}#ff6b6b{% elif break_risk == '中' %}#feca57{% else %}#2ed573{% endif %};border-radius:6px;padding:8px 12px;margin-bottom:8px;">
            <div style="font-size:11px;font-weight:700;color:{% if break_risk == '极高' %}#ff4757{% elif break_risk == '高' %}#ff6b6b{% elif break_risk == '中' %}#feca57{% else %}#2ed573{% endif %};">
                {% if break_risk == '极高' %}🔥 极高风险 (鱼钩目标 {{ hook_max_kg | intf }}kg 超装备 {{ [rod_max, line_max] | min }}kg 30%+, 必断!)
                {% elif break_risk == '高' %}⚠️ 高风险 (鱼钩目标 {{ hook_max_kg | intf }}kg 超装备 20-30%)
                {% elif break_risk == '中' %}⚡ 中风险 (鱼钩目标 {{ hook_max_kg | intf }}kg 超装备 10-20%)
                {% else %}✅ 低风险 (鱼钩目标 {{ hook_max_kg | intf }}kg 超装备 0-10%)
                {% endif %}
            </div>
        </div>
        {% endif %}
        <!-- 9/8: 两列水域列表 (emoji 上/名称下 + 解锁信息分行) -->
        <div class="section">
            <div class="section-title">🌊 可用水域</div>
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">
                {% for spot in spots %}
                <div style="padding:8px 10px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:6px;{% if spot.locked %}opacity:0.5;{% endif %}">
                    <!-- emoji 在上, 名称在下 居中横向展示 -->
                    <div style="display:flex;flex-direction:column;align-items:center;gap:2px;margin-bottom:6px;">
                        <span style="font-size:24px;line-height:1;">{{ spot.emoji }}</span>
                        <span style="font-size:12px;font-weight:700;color:#fff;text-align:center;">{{ spot.name }}{% if spot.locked %} 🔒{% endif %}</span>
                    </div>
                    <div style="font-size:9px;color:rgba(255,255,255,0.5);line-height:1.3;height:26px;overflow:hidden;">{{ spot.desc }}</div>
                    <!-- 解锁信息分行 -->
                    <div style="display:flex;flex-direction:column;gap:2px;margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:9px;color:rgba(255,255,255,0.5);">🎣 中鱼率</span>
                            <span style="font-size:12px;color:#4fc3f7;font-weight:900;">{{ spot.base_rate }}%</span>
                        </div>
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-size:9px;color:rgba(255,255,255,0.5);">🔓 解锁</span>
                            <span style="font-size:10px;color:{% if spot.locked %}#ff6b6b{% else %}#2ed573{% endif %};font-weight:700;">Lv.{{ spot.unlock_level }}{% if spot.fee > 0 %} · {{ spot.fee }}金{% else %}{% endif %}</span>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    <div class="footer">
        <div class="footer-text">
            {% if is_fishing %}📝 /钓鱼 取消 收竿{% else %}📝 /钓鱼 <水域名> 开始钓鱼 · /渔具 装/卸{% endif %}
        </div>
    </div>
</div>
""",

    CardType.FISHING_CARD: """
<div class="card">
    <div class="card-top"></div>
    <!-- 右上角钓鱼等级徽章 -->
    {% if skill_level is defined %}
    <div style="position:absolute;top:14px;right:14px;z-index:10;display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:linear-gradient(135deg,rgba(79,195,247,0.25),rgba(0,242,254,0.25));border:1px solid rgba(79,195,247,0.5);border-radius:20px;box-shadow:0 2px 8px rgba(79,195,247,0.3);">
        <span style="font-size:9px;color:rgba(255,255,255,0.7);font-weight:600;letter-spacing:0.5px;">FISH</span>
        <span style="font-size:13px;color:#4fc3f7;font-weight:900;">Lv.{{ skill_level }}</span>
    </div>
    {% endif %}
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <!-- 名字下方显示钓鱼称号 -->
            {% if fish_title %}
            <div style="font-size:10px;color:#feca57;font-weight:700;margin-top:2px;letter-spacing:0.5px;">🏅 {{ fish_title }}</div>
            {% else %}
            <div class="user-id">🎣 叮！上钩了！</div>
            {% endif %}
        </div>
    </div>
    <div class="main">
        <!-- 鱼展示区 + 估值 -->
        <div class="section center" style="padding:24px 16px 18px;background:linear-gradient(135deg,{{ rarity_bg }},rgba(0,0,0,0.15));">
            <!-- 鱼 emoji 大图 -->
            <div style="font-size:96px;line-height:1;margin-bottom:6px;filter:drop-shadow(0 4px 8px rgba(0,0,0,0.3));">{{ fish_emoji }}</div>
            <!-- 鱼名 -->
            <div style="font-size:20px;font-weight:{% if rarity in ('epic','legendary','mythic') %}900{% else %}800{% endif %};color:{{ rarity_color }};margin-bottom:14px;letter-spacing:1px;">{{ fish_name }}</div>
            <!-- 估值(显眼) -->
            <div style="display:inline-block;padding:8px 20px;background:linear-gradient(135deg,#feca57,#ff9f43);border-radius:24px;box-shadow:0 4px 12px rgba(254,202,87,0.4);">
                <span style="font-size:11px;color:rgba(0,0,0,0.6);font-weight:600;">💰 估值</span>
                <span style="font-size:22px;color:#1a1a2e;font-weight:900;margin-left:6px;">{{ estimated_price | intf }}</span>
                <span style="font-size:11px;color:rgba(0,0,0,0.6);font-weight:600;margin-left:2px;">金币</span>
            </div>
            <!-- 稀有度标签 (9/6: 按 rarity_color 染色) -->
            <div style="margin-top:10px;">
                <span style="display:inline-block;padding:3px 12px;background:{{ rarity_color }}22;border:1px solid {{ rarity_color }};border-radius:20px;font-size:10px;color:{{ rarity_color }};font-weight:{% if rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">{{ rarity_cn }}</span>
            </div>
        </div>
        <!-- 鱼数据(随机大小) -->
        <div class="grid-2" style="margin-top:10px;">
            <div class="grid-item">
                <div class="grid-item-title">⚖️ 重量</div>
                <div class="grid-item-value" style="font-size:{{ weight_size }}px;color:#4fc3f7;font-weight:800;">{{ weight_str }} </div>
            </div>
            <div class="grid-item">
                <div class="grid-item-title">📏 尺寸</div>
                <div class="grid-item-value" style="font-size:{{ size_size }}px;color:#feca57;font-weight:800;">{{ length_str_compact }}</div>
            </div>
        </div>
        <div class="grid-2">
            <div class="grid-item">
                <div class="grid-item-title">📍 钓鱼点</div>
                <div class="grid-item-value" style="font-size:{{ spot_size }}px;">{{ spot }}</div>
            </div>
            <div class="grid-item">
                <div class="grid-item-title">📊 经验</div>
                <div class="grid-item-value" style="font-size:{{ exp_size }}px;color:#2ed573;font-weight:800;">+{{ exp_gain }}</div>
            </div>
        </div>
        {% if title_unlocked %}
        <div class="success-box">
            🏅 解锁称号：{{ title_unlocked }}
        </div>
        {% endif %}
        {% if satiety_restore > 0 or mood_restore > 0 %}
        <div class="section">
            <div class="section-title">🍽️ 食用效果</div>
            {% if satiety_restore > 0 %}
            <div class="row">
                <div class="row-label">🍖 饱食度</div>
                <div class="row-value success">+{{ satiety_restore }}</div>
            </div>
            {% endif %}
            {% if mood_restore > 0 %}
            <div class="row">
                <div class="row-label">😊 心情</div>
                <div class="row-value success">+{{ mood_restore }}</div>
            </div>
            {% endif %}
        </div>
        {% endif %}
    </div>
    <div class="footer">
        <div class="footer-text">📦 已自动存入鱼塘 · 使用 /鱼塘 查看 · /卖鱼 出售</div>
    </div>
</div>
""",

    CardType.SHOP: """
<div class="card shop-card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">{{ page_title or '商店' }}</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">金币</div>
            <div class="gold-value">{{ gold }}</div>
        </div>
    </div>
    <div class="main">
        {% if categories and categories|length > 0 %}
        {# 9/4: 整合商店页面 - 3 列横卡 #}
        {% for cat in categories %}
        <div class="section">
            <div class="section-sub-title">{{ cat.emoji }} {{ cat.name }} <span style="color:rgba(255,255,255,0.3);font-size:10px;">({{ cat.item_list|length }})</span></div>
            {% if cat.item_list and cat.item_list|length > 0 %}
            <div class="shop-grid">
                {% for item in cat.item_list %}
                <div class="shop-grid-item" style="{% if item.rarity_color %}border:1px solid {{ item.rarity_color }};{% endif %}">
                    <div class="grid-icon-box">{{ item.emoji or '📦' }}{% if item.locked %}<div class="lock-badge">🔒</div>{% endif %}</div>
                    <div class="grid-name-row">
                        <span class="grid-name" style="color:{{ item.rarity_color }};font-weight:{% if item.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">{{ item.name }}</span>
                        <span class="grid-tag">{{ item.type or '物品' }}</span>
                    </div>
                    <div class="grid-tier-row">
                        <span class="grid-tier-tag" style="{% if item.rarity_color %}border-color:{{ item.rarity_color }};color:{{ item.rarity_color }};{% endif %}">T{{ item.tier }}</span>
                        <span class="grid-effects">{{ item.effects_text or '—' }}</span>
                    </div>
                    <div class="grid-price-big">¥{{ item.price | intf }}</div>
                    {% if item.description %}<div class="grid-desc">{{ item.description }}</div>{% endif %}
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="center" style="padding:8px;color:rgba(255,255,255,0.5);font-size:11px;">暂无</div>
            {% endif %}
        </div>
        {% endfor %}
        {% else %}
        {# 单分类完整列表 - 9/7: 按 subcategory 分栏 + rarity 降序 #}
        {% if section_title %}
        <div class="section-title">{{ section_title }}</div>
        {% endif %}
        {% if subcat_groups and subcat_groups|length > 0 %}
        {% for group in subcat_groups %}
        <div class="section">
            <div class="section-sub-title">{{ group.subcategory_name }} <span style="color:rgba(255,255,255,0.3);font-size:10px;">({{ group.item_list|length }})</span></div>
            {% if group.item_list and group.item_list|length > 0 %}
            <div class="shop-grid">
                {% for item in group.item_list %}
                <div class="shop-grid-item" style="{% if item.rarity_color %}border:1px solid {{ item.rarity_color }};{% endif %}">
                    <div class="grid-icon-box">{{ item.emoji or '📦' }}{% if item.locked %}<div class="lock-badge">🔒</div>{% endif %}</div>
                    <div class="grid-name-row">
                        <span class="grid-name" style="color:{{ item.rarity_color }};font-weight:{% if item.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">{{ item.name }}</span>
                        <span class="grid-tag">{{ item.type or '物品' }}</span>
                    </div>
                    <div class="grid-tier-row">
                        <span class="grid-tier-tag" style="{% if item.rarity_color %}border-color:{{ item.rarity_color }};color:{{ item.rarity_color }};{% endif %}">T{{ item.tier }}</span>
                        <span class="grid-effects">{{ item.effects_text or '—' }}</span>
                    </div>
                    <div class="grid-price-big">¥{{ item.price | intf }}</div>
                    {% if item.description %}<div class="grid-desc">{{ item.description }}</div>{% endif %}
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% endif %}
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">📋 /商店 买 &lt;物品名&gt; [数量] · /商店 &lt;分类&gt; 查看完整</div></div>
</div>
""",

    CardType.COURSE_START: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">开始学习</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">经验</div>
            <div class="gold-value">+{{ gain_exp }}</div>
        </div>
    </div>
    <div class="main">
        <div class="center" style="padding:10px 0">
            <div style="font-size:32px">{{ course_emoji }}</div>
            <div style="font-size:16px;font-weight:700;margin-top:4px">{{ course_name }}</div>
        </div>
        
        <div class="section">
            <div class="section-title">学习信息</div>
            <div class="row"><span class="row-label">⏰ 时长</span><span class="row-value">{{ hours }} 小时</span></div>
            <div class="row"><span class="row-label">📚 预计经验</span><span class="row-value gold">+{{ gain_exp }} EXP</span></div>
        </div>
        
        <div class="section">
            <div class="section-title">消耗预估</div>
            <div class="row"><span class="row-label">💪 体力</span><span class="row-value warning">-{{ consume_strength }}</span></div>
            <div class="row"><span class="row-label">⚡ 精力</span><span class="row-value warning">-{{ consume_energy }}</span></div>
            <div class="row"><span class="row-label">😊 心情</span><span class="row-value warning">-{{ consume_mood }}</span></div>
        </div>
    </div>
</div>
""",

    CardType.FISH_DEX: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">🎣 鱼塘图鉴</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">收集</div>
            <div class="gold-value">{{ caught_count }}/{{ total_count }}</div>
        </div>
    </div>
    <div class="main">
        {% if title %}
        <div class="success-box">
            🏅 当前称号：{{ title }}
        </div>
        {% endif %}
        {% if biggest.fish %}
        <div class="section">
            <div class="section-title">🏆 个人记录</div>
            <div class="row">
                <div class="row-label">最大单条</div>
                <div class="row-value gold">{{ biggest.fish }} {{ biggest_weight_str }} · {{ biggest_length }}</div>
            </div>
        </div>
        {% endif %}
        <div class="section">
            <div class="section-title">🐟 鱼类图鉴</div>
            {% for fish in fish_items %}
            <div class="list-item">
                <div class="list-item-left">
                    <span class="list-item-emoji">{{ fish.emoji }}</span>
                    <div>
                        <div class="list-item-name">
                            {% if fish.locked %}<span style="color:rgba(255,255,255,0.3)">??? 未知鱼类</span>
                            {% else %}{{ fish.name }}{% endif %}
                            {% if fish.rarity == 'legendary' %}<span style="color:#ff6b6b;font-size:10px;"> [传奇]</span>
                            {% elif fish.rarity == 'epic' %}<span style="color:#c586c0;font-size:10px;"> [史诗]</span>
                            {% elif fish.rarity == 'rare' %}<span style="color:#4fc3f7;font-size:10px;"> [稀有]</span>
                            {% elif fish.rarity == 'uncommon' %}<span style="color:#7bed9f;font-size:10px;"> [不凡]</span>
                            {% endif %}
                        </div>
                        <div class="list-item-sub">
                            {% if fish.locked %}未捕获{% else %}已捕获 × {{ fish.caught }}{% endif %}
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    <div class="footer">
        <div class="footer-text">📝 /钓鱼 村口池塘 开始钓鱼 · /卖鱼 出售</div>
    </div>
</div>
""",

    CardType.SELL_RESULT: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">💰 交易完成{% if filter_label %} · {{ filter_label }}{% endif %}</div>
        </div>
    </div>
    <div class="main">
        <div class="section center" style="padding:20px 16px;background:linear-gradient(135deg,rgba(46,204,113,0.2),rgba(46,204,113,0.05));">
            <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;">本次收入</div>
            <div style="display:inline-block;padding:10px 24px;background:linear-gradient(135deg,#2ed573,#26de81);border-radius:24px;box-shadow:0 4px 12px rgba(46,213,115,0.4);">
                <span style="font-size:32px;color:#fff;font-weight:900;">+{{ total_gold }}</span>
                <span style="font-size:13px;color:rgba(255,255,255,0.9);font-weight:600;margin-left:4px;">金币</span>
            </div>
            <div style="margin-top:8px;font-size:12px;color:rgba(255,255,255,0.7);">共 {{ total_count }} 件物品</div>
        </div>
        <div class="section">
            <div class="section-title">📦 售出明细</div>
            {% for item in sold_records %}
            <div class="row">
                <div class="row-label">
                    {% if item.weight is defined and item.weight %}{% if item.length_str %}{{ item.length_str }} {% endif %}{% endif %}<span style="color:{{ item.rarity_color }};font-weight:{% if item.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">{% if item.rarity %}<span style="opacity:0.7;">[{{ item.rarity_cn }}] </span>{% endif %}{{ item.name }}</span>{% if item.quantity is defined %} ×{{ item.quantity }}{% endif %}
                </div>
                <div class="row-value gold">+{{ item.gold }}</div>
            </div>
            {% endfor %}
        </div>
        {% if kept_records and kept_records|length > 0 %}
        <div class="section" style="background:rgba(79,195,247,0.05);border:1px dashed rgba(79,195,247,0.3);">
            <div class="section-title">🪝 保留 ({{ kept_records|length }})</div>
            {% for k in kept_records %}
            <div class="row">
                <div class="row-label">🐟 <span style="color:{{ k.rarity_color }};font-weight:{% if k.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">{{ k.name }}</span> {{ k.weight_str }} <span style="color:rgba(255,255,255,0.4);font-size:10px;">({{ k.size_label }})</span></div>
                <div class="row-value" style="color:#4fc3f7;font-size:11px;">留下</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    <div class="footer">
        <div class="footer-text">💼 资金已入账 · 使用 /背包 查看 · /卖 继续出售</div>
    </div>
</div>
""",

    CardType.ENCHANT: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">✨ 附魔结果</div>
        </div>
    </div>
    <div class="main">
        <div class="section center" style="padding:16px;background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(155,89,182,0.10));">
            <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;">物品稀有度</div>
            <div style="margin-bottom:8px;">
                <span style="font-size:14px;color:rgba(255,255,255,0.7);text-decoration:line-through;">{{ old_rarity_cn }} {{ item_name }} ×{{ old_mult }}</span>
            </div>
            <div style="font-size:24px;color:#fff;font-weight:900;display:inline-block;padding:6px 18px;background:linear-gradient(135deg,{{ new_rarity_color }},{{ new_rarity_color_dark }});border-radius:18px;box-shadow:0 3px 10px rgba(255,255,255,0.2);">
                {{ new_rarity_cn }} {{ item_name }} ×{{ new_mult }}
            </div>
        </div>

        <div class="section">
            <div class="section-title">📊 词条一览 <span style="font-size:11px;color:rgba(255,255,255,0.5);font-weight:normal;">({{ entry_count }} 个)</span></div>
            {% if entries %}
            {% for e in entries %}
            <div class="row" style="align-items:center;">
                <div class="row-label">
                    <span style="display:inline-block;width:18px;text-align:center;">{{ e.icon }}</span>
                    <span style="font-size:12px;">{{ e.name }}</span>
                </div>
                <div class="row-value">
                    {% if e.type == 'pct' %}
                    <span style="color:#7CFC00;">+{{ e.value }}%</span>
                    {% else %}
                    <span style="color:#FFD700;">+{{ e.value }}</span>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
            {% else %}
            <div style="padding:8px 12px;color:rgba(255,255,255,0.4);font-size:12px;text-align:center;">无词条（普通物品）</div>
            {% endif %}
        </div>

        {% if base_attrs %}
        <div class="section">
            <div class="section-title">🔧 基础属性</div>
            {% for a in base_attrs %}
            <div class="row">
                <div class="row-label">{{ a.name }}</div>
                <div class="row-value">
                    {% if a.diff %}
                    <span style="color:rgba(255,255,255,0.5);text-decoration:line-through;font-size:11px;">{{ a.old }}</span>
                    <span style="color:#7CFC00;margin-left:6px;">{{ a.new }}</span>
                    {% else %}
                    <span>{{ a.new }}</span>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="section" style="background:rgba(255,255,255,0.03);">
            <div class="section-title">📜 消耗</div>
            <div style="padding:6px 12px;font-size:12px;color:rgba(255,255,255,0.7);">
                {{ scroll_color }}{{ scroll_name }} ×1（剩余 {{ scroll_remaining }}）
            </div>
        </div>

        <div class="section" style="background:rgba(255,255,255,0.03);">
            <div class="section-title">💡 附魔提示</div>
            <div style="padding:6px 12px;font-size:11px;color:rgba(255,255,255,0.6);font-family:monospace;line-height:1.7;">
                /附魔 物品 附魔券&nbsp;&nbsp;&nbsp;- 指定附魔券<br>
                /附魔 物品&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- 用背包第一张附魔券<br>
                /使用 附魔券 物品&nbsp;&nbsp;&nbsp;- 反向顺序
            </div>
        </div>
    </div>
    <div class="footer">
        <div class="footer-text">✨ 稀有度改变后词条会重新抽取 · 高稀有度 = 更多词条</div>
    </div>
</div>
""",
CardType.ITEM_DETAIL: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">{{ header_subtitle }}</div>
        </div>
    </div>
    <div class="main">
        <div class="section center" style="padding:18px 16px;background:linear-gradient(135deg,{{ rarity_color }}33,{{ rarity_color }}11);border-left:4px solid {{ rarity_color }};">
            <div style="font-size:48px;line-height:1;margin-bottom:8px;">{{ emoji }}</div>
            <div style="font-size:18px;color:{{ rarity_color }};font-weight:900;margin-bottom:4px;">
                {{ rarity_cn }}{{ name }}
            </div>
            {% if quantity > 1 %}
            <div style="display:inline-block;background:{{ rarity_color }};color:#fff;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">
                持有 ×{{ quantity }}
            </div>
            {% endif %}
            {% if item_type_cn %}
            <div style="margin-top:6px;font-size:11px;color:rgba(255,255,255,0.55);">
                📂 {{ item_type_cn }}{% if subcategory %} · {{ subcategory }}{% endif %}
            </div>
            {% endif %}
        </div>

        {% if show_price or show_sell_price %}
        <div class="section">
            <div class="section-title">💰 交易信息</div>
            {% if show_price %}
            <div class="row">
                <div class="row-label">🏷️ 商店售价</div>
                <div class="row-value" style="color:#ffd700;font-weight:700;">{{ buy_price }} 金币</div>
            </div>
            {% endif %}
            {% if show_sell_price %}
            <div class="row">
                <div class="row-label">💵 出售价格</div>
                <div class="row-value" style="color:#ffd700;font-weight:700;">{{ sell_price }} 金币/件</div>
            </div>
            {% endif %}
            {% if is_fish and base_price %}
            <div class="row">
                <div class="row-label">📊 基础价</div>
                <div class="row-value">{{ base_price }} 金币</div>
            </div>
            {% endif %}
            {% if is_fish and weight %}
            <div class="row">
                <div class="row-label">⚖️ 体重</div>
                <div class="row-value">{{ weight_str }}</div>
            </div>
            {% endif %}
            {% if unlock_requirement %}
            <div class="row">
                <div class="row-label">🔓 解锁</div>
                <div class="row-value" style="font-size:11px;color:rgba(255,255,255,0.7);">{{ unlock_requirement }}</div>
            </div>
            {% endif %}
        </div>
        {% endif %}

        {% if stats_rows %}
        <div class="section">
            <div class="section-title">📊 属性</div>
            {% for row in stats_rows %}
            <div class="row">
                <div class="row-label">{{ row.label }}</div>
                <div class="row-value">{{ row.value }}</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if enchant_entries %}
        <div class="section">
            <div class="section-title">✨ 词条</div>
            {% for entry in enchant_entries %}
            <div style="padding:6px 10px;background:rgba(255,255,255,0.05);border-radius:6px;margin-bottom:4px;">
                <div style="font-size:11px;color:{{ entry.color|default('#ffa726') }};font-weight:700;">{{ entry.name }}</div>
                <div style="font-size:11px;color:rgba(255,255,255,0.75);margin-top:2px;">{{ entry.desc }}</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if desc %}
        <div class="section">
            <div class="section-title">📖 说明</div>
            <div style="font-size:12px;color:rgba(255,255,255,0.85);line-height:1.6;padding:6px 8px;font-style:italic;">
                {{ desc }}
            </div>
        </div>
        {% endif %}

        {% if source_hint %}
        <div class="section">
            <div class="section-title">📍 获取方式</div>
            <div style="font-size:11px;color:rgba(255,255,255,0.7);line-height:1.6;padding:6px 8px;">
                {{ source_hint }}
            </div>
        </div>
        {% endif %}
    </div>
    <div class="footer">
        <div class="footer-text">{{ footer_hint }}</div>
    </div>
</div>
""",    CardType.SELL_OVERVIEW: """
<div class="card">
    <div class="card-top"></div>
    <div class="header">
        <img class="avatar" src="{{ avatar_url }}" alt="avatar">
        <div class="header-info">
            <div class="username">{{ nickname }}</div>
            <div class="user-id">💼 可售资产清单</div>
        </div>
    </div>
    <div class="main">
        <div class="section center" style="padding:16px 16px;background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(255,165,0,0.05));">
            <div style="font-size:11px;color:rgba(255,255,255,0.6);margin-bottom:4px;text-transform:uppercase;letter-spacing:1px;">预估可变现</div>
            <div style="display:inline-block;padding:8px 20px;background:linear-gradient(135deg,#ffd700,#ff8c00);border-radius:20px;box-shadow:0 3px 10px rgba(255,215,0,0.3);">
                <span style="font-size:28px;color:#fff;font-weight:900;">{{ total_estimated }}</span>
                <span style="font-size:13px;color:rgba(255,255,255,0.95);font-weight:600;margin-left:4px;">金币</span>
            </div>
            <div style="margin-top:6px;font-size:11px;color:rgba(255,255,255,0.6);">⚠️ 股票市值不计入 (价格实时变化)</div>
        </div>

        {% if inventory_items %}
        <div class="section">
            <div class="section-title">📦 背包可售 <span style="font-size:11px;color:rgba(255,255,255,0.5);font-weight:normal;">({{ inventory_items|length }} 种 / {{ inventory_count }} 件 / {{ inventory_gold }}G)</span></div>
            {% for it in inventory_items %}
            <div class="row">
                <div class="row-label">
                    {% if it.type == 'fish' %}🐟{% elif it.type == 'food' %}🍖{% else %}🎒{% endif %}
                    <span style="color:{{ it.rarity_color }};font-weight:{% if it.rarity in ('epic','legendary','mythic') %}bold{% else %}normal{% endif %};">
                        {% if it.rarity_cn %}<span style="opacity:0.7;">[{{ it.rarity_cn }}] </span>{% endif %}{{ it.name }}
                    </span>
                    ×{{ it.count }}{% if it.weight %} ({{ it.weight_str }}){% endif %}
                </div>
                <div class="row-value gold">{{ it.total_gold }}G</div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="section">
            <div class="section-title">📦 背包可售</div>
            <div style="padding:8px 12px;color:rgba(255,255,255,0.4);font-size:12px;text-align:center;">空</div>
        </div>
        {% endif %}

        {% if stocks %}
        <div class="section">
            <div class="section-title">📈 股票持仓 <span style="font-size:11px;color:rgba(255,255,255,0.5);font-weight:normal;">({{ stocks|length }} 支 / 成本 {{ stock_cost }}G)</span></div>
            {% for s in stocks %}
            <div class="row">
                <div class="row-label">📊 {{ s.name }} ({{ s.code }}) ×{{ s.quantity }}</div>
                <div class="row-value">成本 {{ s.cost_total }}G</div>
            </div>
            {% endfor %}
            <div style="padding:6px 12px;color:rgba(255,255,255,0.5);font-size:11px;">💡 实时市值请用 /股市 持股</div>
        </div>
        {% else %}
        <div class="section">
            <div class="section-title">📈 股票持仓</div>
            <div style="padding:8px 12px;color:rgba(255,255,255,0.4);font-size:12px;text-align:center;">空</div>
        </div>
        {% endif %}

        {% if assets %}
        <div class="section">
            <div class="section-title">🏛️ 其他资产 <span style="font-size:11px;color:rgba(255,255,255,0.5);font-weight:normal;">({{ assets|length }} 项 / {{ asset_total }}G)</span></div>
            {% for a in assets %}
            <div class="row">
                <div class="row-label">{{ a.detail }} {{ a.name }}</div>
                <div class="row-value gold">{{ a.sell_price }}G</div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="section">
            <div class="section-title">🏛️ 其他资产</div>
            <div style="padding:8px 12px;color:rgba(255,255,255,0.4);font-size:12px;text-align:center;">无</div>
        </div>
        {% endif %}

        <div class="section" style="background:rgba(255,255,255,0.03);">
            <div class="section-title">💡 出售命令</div>
            <div style="padding:6px 12px;font-size:11px;color:rgba(255,255,255,0.7);font-family:monospace;line-height:1.7;">
                /卖 草鱼&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- 卖指定名字<br>
                /卖 草鱼 3&nbsp;&nbsp;&nbsp;- 卖 3 条<br>
                /卖 草鱼 大&nbsp;&nbsp;- 卖最大那条<br>
                /卖 全部&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- ⚠️ 显式确认卖所有
            </div>
        </div>
    </div>
    <div class="footer">
        <div class="footer-text">💼 出售前请确认 · 背包/股票/资产 · 安全第一</div>
    </div>
</div>
""",
}


def get_card_template(card_type: str) -> str:
    """获取完整HTML模板"""
    content = CONTENT_TEMPLATES.get(card_type, CONTENT_TEMPLATES.get(CardType.GENERIC, ""))
    return HTML_TEMPLATE.replace("{{ content }}", content)


def build_avatar_url(qq_id: str) -> str:
    """构建QQ头像URL"""
    return f"https://q.qlogo.cn/headimg_dl?dst_uin={qq_id}&spec=100&img_type=png"
 
 
