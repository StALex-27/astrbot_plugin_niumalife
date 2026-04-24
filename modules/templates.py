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
html, body { width: 380px; background: transparent; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(145deg, #1e1e3f 0%, #2d2d5a 100%); }
.card { width: 380px; min-height: 100%; background: linear-gradient(145deg, #1e1e3f 0%, #2d2d5a 50%, #1a1a35 100%); border-radius: 16px; overflow: hidden; color: #fff; }
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
    COURSE_LIST = "course_list"
    FOOD_LIST = "food_list"
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
            <div class="user-id">ID: {{ user_id_short }}</div>
        </div>
        <div class="gold-box">
            <div class="gold-label">金币</div>
            <div class="gold-value">{{ gold }}</div>
        </div>
    </div>
    <div class="main">
        <div class="grid-2">
            <div class="grid-item"><div class="grid-item-title">住所</div><div class="grid-item-value">{{ residence }}</div></div>
            <div class="grid-item"><div class="grid-item-title">状态</div><div class="grid-item-value highlight">{{ status }}</div></div>
        </div>
        
        <div class="section">
            <div class="section-title">签到信息</div>
            <div class="grid-2">
                <div class="grid-item"><div class="grid-item-title">连续</div><div class="grid-item-value">{{ streak }} 天</div></div>
                <div class="grid-item"><div class="grid-item-title">总计</div><div class="grid-item-value">{{ total_days }} 天</div></div>
                <div class="grid-item"><div class="grid-item-title">欧气</div><div class="grid-item-value">{{ luck_emoji }} {{ luck_name }}</div></div>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">属性状态</div>
            <div class="attrs-grid">
                <div class="attr-item attr-health">
                    <div class="attr-header"><span class="attr-name">❤️ 健康</span><span class="attr-value">{{ health }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ health }}%"></div></div>
                </div>
                <div class="attr-item attr-strength">
                    <div class="attr-header"><span class="attr-name">💪 体力</span><span class="attr-value">{{ strength }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ strength }}%"></div></div>
                </div>
                <div class="attr-item attr-energy">
                    <div class="attr-header"><span class="attr-name">⚡ 精力</span><span class="attr-value">{{ energy }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ energy }}%"></div></div>
                </div>
                <div class="attr-item attr-mood">
                    <div class="attr-header"><span class="attr-name">😊 心情</span><span class="attr-value">{{ mood }}</span></div>
                    <div class="attr-bar"><div class="attr-fill" style="width:{{ mood }}%"></div></div>
                </div>
                <div class="attr-item attr-satiety full">
                    <div class="attr-header"><span class="attr-name">🍖 饱食度</span><span class="attr-value">{{ satiety }}</span></div>
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
        
        <div class="section">
            <div class="section-title">我的技能</div>
            <div class="skill-tags">{{ skills_html }}</div>
        </div>
        
        {% if warnings %}
        <div class="warning-box">{{ warnings }}</div>
        {% endif %}
    </div>
    <div class="footer"><div class="footer-text">牛马人生 v3.0</div></div>
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
        <div style="font-size:10px;color:rgba(255,255,255,0.6);margin-bottom:12px">{{ luck_desc }}</div>
        
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
            <div class="row"><span class="row-label">🌙 睡眠加成</span><span class="row-value highlight">{{ sleep_bonus }}x</span></div>
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
}


def get_card_template(card_type: str) -> str:
    """获取完整HTML模板"""
    content = CONTENT_TEMPLATES.get(card_type, CONTENT_TEMPLATES.get(CardType.GENERIC, ""))
    return HTML_TEMPLATE.replace("{{ content }}", content)


def build_avatar_url(qq_id: str) -> str:
    """构建QQ头像URL"""
    return f"https://q.qlogo.cn/headimg_dl?dst_uin={qq_id}&spec=100&img_type=png"
