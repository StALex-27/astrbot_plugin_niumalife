"""
卡片渲染器模块
牛马人生项目

使用AstrBot的html_renderer.render_custom_template()生成图片卡片

9/5 重构：每个 render_xxx 函数现在声明 ViewSpec（required_fields + defaults）。
_render() 入口会先 data.update(SPEC.defaults) 自动补齐缺字段。
这样调用方不用再在 25 个命令文件里各自 try/except 补默认值。
"""

from typing import Optional, Dict, Any, List
import jinja2
from astrbot.core import html_renderer
from .templates import CardType, get_card_template, build_avatar_url


# ============================================================
# ViewSpec — 渲染数据契约（ARCHITECTURE.md P0 #2）
# ============================================================
#
# 每个 render_xxx 函数声明一个 ViewSpec:
#   - card_type:  对应 CardType 枚举
#   - defaults:   data 缺这些字段时自动补齐（避免 Jinja 报错或空字符串）
#   - required:   真正必填的关键字段（缺时报 warning, 不抛异常, 走 fallback）
#
# 优点：
#   1. 调用方（25 个命令文件）不用再各自 try/except 补默认值
#   2. 改 render_xxx 的字段时，spec 集中维护，不用全局搜索
#   3. 文档化：每个 view 需要哪些字段一目了然

class ViewSpec:
    """单个 view 的渲染数据契约"""

    __slots__ = ("card_type", "defaults", "required")

    def __init__(
        self,
        card_type: str,
        defaults: Optional[Dict[str, Any]] = None,
        required: Optional[List[str]] = None,
    ):
        self.card_type = card_type
        self.defaults = defaults or {}
        self.required = required or []

    def apply_defaults(self, data: dict) -> dict:
        """补齐 data 中缺失的字段（不覆盖已有值）。"""
        for k, v in self.defaults.items():
            data.setdefault(k, v)
        return data

    def check_required(self, data: dict) -> list[str]:
        """返回 data 中缺失的 required 字段列表（空 list 表示全有）。"""
        return [k for k in self.required if k not in data or data[k] is None]


# 全局视图规格表 —— 每个 render_xxx 必填 1 个 entry
# 数值默认 0, 字符串默认 "", 列表默认 []  (与 _SilentUndefined 兜底一致)
VIEW_SPECS: Dict[str, ViewSpec] = {
    CardType.PROFILE: ViewSpec(
        card_type=CardType.PROFILE,
        defaults={
            "nickname": "未知", "gold": 0, "residence": "桥下", "residence_emoji": "🏠",
            "status": "空闲", "rent_per_day": 0, "residence_days_left": 0,
            "streak": 0, "total_days": 0, "total_gold_earned": 0, "peak_gold": 0,
            "today_gold_work": 0, "today_gold_spent": 0,
            "fish_count": 0, "fish_value": 0, "fish_species": 0,
            "fish_title": "", "biggest_fish": "", "biggest_fish_weight": 0, "biggest_fish_length": "",
            "luck_emoji": "🎲", "luck_name": "普通人", "luck_desc": "普通人",
            "buff_tags": "", "skills": {}, "skills_html": "", "warnings": "",
            "health": 0, "strength": 0, "mood": 0, "satiety": 0, "energy": 0, "sanity": 0,
            "user_id_short": "", "avatar_url": "",
        },
        required=["nickname", "gold"],
    ),
    CardType.STATUS: ViewSpec(
        card_type=CardType.STATUS,
        defaults={
            "nickname": "未知", "status": "空闲", "gold": 0, "health": 0, "strength": 0,
            "mood": 0, "satiety": 0, "energy": 0, "sanity": 0,
            "body_pressure": 0, "mind_pressure": 0,
            "active_debuffs": [], "residence": "桥下",
        },
        required=["nickname"],
    ),
    CardType.CHECKIN: ViewSpec(
        card_type=CardType.CHECKIN,
        defaults={
            "nickname": "未知", "gold_gained": 0, "streak": 0, "lucky_drop": "",
            "luck_emoji": "🎲", "luck_name": "普通人", "luck_desc": "",
            "already_checked": False, "buff_tags": "",
        },
        required=["nickname"],
    ),
    CardType.FISHING_CARD: ViewSpec(
        card_type=CardType.FISHING_CARD,
        defaults={
            "nickname": "未知", "fish_name": "未知鱼", "fish_emoji": "🐟",
            "weight_kg": 0, "length_cm": 0, "size_label": "",
            "rarity": "common", "rarity_emoji": "⚪", "estimated_price": 0,
            "exp_gain": 0, "new_title": "", "levelup_info": None,
            "spot_name": "", "fish_title": "",
        },
        required=["fish_name"],
    ),
    CardType.SHOP: ViewSpec(
        card_type=CardType.SHOP,
        defaults={
            "nickname": "未知", "gold": 0, "shop_name": "商店",
            "categories": [], "tier_groups": [],
            "item_list": [], "fixed_items": [], "random_items": [],
        },
        required=["shop_name"],
    ),
    CardType.BACKPACK: ViewSpec(
        card_type=CardType.BACKPACK,
        defaults={
            "nickname": "未知", "items": [], "filter_label": "",
            "total_count": 0, "total_value": 0, "categories": [],
        },
        required=["nickname"],
    ),
    CardType.FISH_DEX: ViewSpec(
        card_type=CardType.FISH_DEX,
        defaults={
            "nickname": "未知", "fish_caught": {}, "all_fish": {},
            "completion_pct": 0.0, "biggest_catch": {}, "fish_title": "",
        },
        required=["nickname"],
    ),
    CardType.FISHING_GEAR: ViewSpec(
        card_type=CardType.FISHING_GEAR,
        defaults={
            "nickname": "未知", "gear": {}, "empty_slots": [],
            "gear_slots": [],  # 9/6 v9.5: 改为 list, 模板 {% for slot in gear_slots %} 迭代
            "effects": {}, "effects_summary": "",
            # 9/7 命名统一: capacity_rod → capacity_fishing_rod (与 slot 名一致)
            # 9/7 命名统一: capacity_line → capacity_fishing_line (与 slot 名一致)
            "load_capacity": 0, "capacity_fishing_rod": 0, "capacity_fishing_line": 0,
            "diet_zh": "不限", "inventory_gear": [], "inventory_gear_count": 0,
            "equipped_count": 0,
        },
        required=["nickname"],
    ),
    CardType.ERROR: ViewSpec(
        card_type=CardType.ERROR,
        defaults={"title": "出错了", "message": "未知错误", "emoji": "❌", "error_code": 0},
        required=["message"],
    ),
    CardType.SUCCESS: ViewSpec(
        card_type=CardType.SUCCESS,
        defaults={"message": "操作成功", "emoji": "✅", "title": "", "gold_delta": 0},
        required=["message"],
    ),
    CardType.HELP: ViewSpec(
        card_type=CardType.HELP,
        defaults={"commands": [], "categories": [], "title": "帮助", "command_count": 0},
        required=[],
    ),
    CardType.GENERIC: ViewSpec(
        card_type=CardType.GENERIC,
        defaults={"content": "", "title": "", "emoji": "📌", "height": 200},
        required=[],
    ),
    CardType.SELL_OVERVIEW: ViewSpec(
        card_type=CardType.SELL_OVERVIEW,
        defaults={
            "nickname": "未知", "items": [], "total_count": 0,
            "estimated_gold": 0, "filter_label": "",
        },
        required=["nickname"],
    ),
}


def get_view_spec(card_type: str) -> Optional[ViewSpec]:
    """查找某 card_type 对应的 ViewSpec。找不到返回 None（不会抛）。"""
    if not card_type:
        return None
    return VIEW_SPECS.get(card_type)


# ============================================================
# 卡片渲染器
# ============================================================

class CardRenderer:
    """HTML卡片渲染器 - 使用AstrBot内置渲染服务"""
    
    # 渲染尺寸配置
    DEFAULT_WIDTH = 380
    DEFAULT_HEIGHT = 500
    MAX_HEIGHT = 800
    
    async def _render(self, card_type: str, data: dict, height: int = None, width: int = None, full_page: bool = False) -> str:
        """内部渲染方法 - 9/5: 优先本地 Chromium, fallback AstrBot 网络 API

        9/5 重构：入口加 ViewSpec 默认值兜底 + required 字段检查
          - data 自动补齐 spec.defaults 里声明的缺字段（不覆盖已有值）
          - data 缺 spec.required 关键字段时打 warning 日志（不抛, 走 fallback 渲染）
        """
        import logging as _lr
        _lr.getLogger(__name__).info(f"[CardRenderer._render] {card_type} data_keys={list(data.keys())}")

        # === ViewSpec 兜底（ARCHITECTURE.md P0 #2）===
        spec = get_view_spec(card_type)
        if spec is not None:
            spec.apply_defaults(data)
            missing = spec.check_required(data)
            if missing:
                _lr.getLogger(__name__).warning(
                    f"[CardRenderer._render] {card_type} 缺关键字段 {missing}, "
                    f"将用默认值渲染（请在调用方补齐）"
                )

        template = get_card_template(card_type)
        if not template:
            template = get_card_template(CardType.GENERIC)

        render_height = height or self.DEFAULT_HEIGHT
        render_width = width or self.DEFAULT_WIDTH

        # === 优先: 本地 Chromium (绕过远程 T2I) ===
        try:
            if not hasattr(self, "_local_renderer"):
                self._local_renderer = _LocalRenderer()
            if self._local_renderer._enabled:
                path = await self._local_renderer.render(
                    template, data,
                    width=render_width, height=render_height,
                    full_page=full_page, card_type=card_type,
                )
                if path:
                    _lr.getLogger(__name__).info(f"[CardRenderer._render] {card_type} -> {path}")
                    return await self._local_path_to_url(path)
                else:
                    _lr.getLogger(__name__).warning(f"[CardRenderer._render] {card_type} 本地渲染返回空")
        except Exception as e:
            _lr.getLogger(__name__).warning(
                f"[CardRenderer._render] {card_type} 本地渲染异常: {type(e).__name__}: {e}"
            )

        # === Fallback: AstrBot 网络 T2I ===
        url = await html_renderer.render_custom_template(
            template,
            data,
            return_url=True,
            options={
                "type": "png",
                "quality": None,
                "full_page": False,
                "clip": {
                    "x": 0,
                    "y": 0,
                    "width": self.DEFAULT_WIDTH,
                    "height": render_height
                },
                "scale": "device",
                "device_scale_factor_level": "ultra"
            }
        )
        return url

    async def _local_path_to_url(self, png_path: str) -> str:
        """本地 PNG 文件转 AstrBot 可用 URL/file

        9/5: 返回绝对路径, 让 Image.fromFileSystem 自动转 file:// URL。
        9/5 (修正): base64:// 不能走 image_result (被当路径导致 File name too long)
        9/5 (修正2): file:// URL 路径不再加, 直接给绝对路径
        """
        import os
        if not png_path or not os.path.exists(png_path):
            return ""

        # 返回绝对路径 - Image.fromFileSystem() 会自动处理
        return os.path.abspath(png_path)
    
    def _get_base_data(self, user_id: str) -> dict:
        """获取基础数据"""
        return {
            "avatar_url": build_avatar_url(user_id),
            "user_id_short": user_id[:8] + "..." if len(user_id) > 8 else user_id,
        }
    
    async def render_profile(self, user: dict, event) -> str:
        """渲染档案卡片"""
        from .buff import BuffManager
        from .checkin import get_luck_rating
        from ..src.fishing.fishing_manager import format_weight, format_length_compact  # 9/8: 紧凑格式
        
        user_id = str(event.get_sender_id())
        attrs = user.get("attributes", {})
        checkin = user.get("checkin", {})
        
        streak = checkin.get("streak", 0)
        total_days = checkin.get("total_days", 0)
        last_luck = checkin.get("last_luck", 50)
        active_buffs = checkin.get("active_buffs", [])
        
        luck_rating = get_luck_rating(last_luck)
        
        # Buff标签
        buff_tags = ""
        valid_buffs = [b for b in active_buffs if not BuffManager.is_expired(b)]
        if valid_buffs:
            buff_tags = " ".join([
                f"<span class='buff-tag'>{b.get('emoji','')}{b.get('name','')}</span>" 
                for b in valid_buffs[:3]
            ])
        
        # 技能标签
        skills_html = ""
        skills = user.get("skills", {})
        if isinstance(skills, dict):
            for name, data in skills.items():
                lvl = data.get("level", 0) if isinstance(data, dict) else (int(data) if data else 0)
                if lvl > 0 or name == "苦力":
                    skills_html += f"<span class='skill-tag active'>◆ {name} Lv.{lvl}</span>"
        
        # 警告
        warnings = ""
        if attrs.get("satiety", 100) < 20:
            warnings += "⚠️ 饱食度过低！ "
        if attrs.get("mood", 100) < 20:
            warnings += "⚠️ 心情过低！ "
        if attrs.get("health", 100) < 50:
            warnings += "⚠️ 健康偏低！"
        
        # 计算累计经验值和综合等级
        skill_exp = user.get("skill_exp", {})
        total_exp = sum(skill_exp.values()) if skill_exp else 0
        from .skills import get_skill_level, get_skill_exp_rate
        max_level = 0
        for skill_name, exp in skill_exp.items():
            lvl = get_skill_level(exp, get_skill_exp_rate(skill_name))
            if lvl > max_level:
                max_level = lvl
        user_level = max_level
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "gold": int(user.get("gold", 0)),
            "residence": user.get("residence", "桥下"),
            "residence_emoji": user.get("residence_emoji", "🏠"),
            "status": user.get("status", "空闲"),
            "rent_per_day": int(user.get("rent_per_day", 0)),
            "residence_days_left": user.get("residence_days_left", 0),
            "streak": streak,
            "total_days": total_days,
            "total_gold_earned": int(user.get("total_gold_earned", 0)),
            "peak_gold": int(user.get("peak_gold", 0)),
            "today_gold_work": int(user.get("today_gold_work", 0)),
            "today_gold_spent": int(user.get("today_gold_spent", 0)),
            "fish_count": int(user.get("fish_count", 0)),
            "fish_value": int(user.get("fish_value", 0)),
            "fish_species": int(user.get("fish_species", 0)),
            "fish_title": user.get("fish_title", ""),
            "biggest_fish": user.get("biggest_fish", ""),
            "biggest_fish_weight": user.get("biggest_fish_weight", 0),
            "biggest_fish_weight_str": format_weight(user.get("biggest_fish_weight", 0)) if user.get("biggest_fish") else "",  # 9/8: 紧凑格式
            "biggest_fish_length": user.get("biggest_fish_length", ""),
            "biggest_fish_length_str": format_length_compact(user.get("biggest_fish_length")) if user.get("biggest_fish") else "",  # 9/8: 紧凑格式
            "luck_emoji": luck_rating.get("emoji", "🎲"),
            "luck_name": luck_rating.get("name", "普通人"),
            "luck_desc": luck_rating.get("description", user.get("title", "普通人")),
            "buff_tags": buff_tags,
            "skills": user.get("skills", {}),
            "skills_html": skills_html or "<span class='skill-tag'>暂无技能</span>",
            "warnings": warnings,
            # 9/5: clamp mood/health 等数值到 [0, 100], 避免显示负数
            "health": int(max(0, min(100, attrs.get("health", 0)))),
            "strength": int(max(0, min(100, attrs.get("strength", 0)))),
            "energy": int(max(0, min(100, attrs.get("energy", 0)))),
            "mood": int(max(0, min(100, attrs.get("mood", 0)))),
            "satiety": int(max(0, min(100, attrs.get("satiety", 0)))),
            "user_level": user_level,
            "total_exp": total_exp,
        }
        
        height = 450 + (30 if buff_tags else 0) + (25 if skills_html else 0) + (20 if warnings else 0)
        return await self._render(CardType.PROFILE, data, height)
    
    async def render_status(self, user: dict, event) -> str:
        """渲染状态卡片"""
        from .buff import BuffManager
        
        user_id = str(event.get_sender_id())
        attrs = user.get("attributes", {})
        
        # 进度
        progress = None
        action_detail = user.get("action_detail")
        if action_detail:
            progress = {
                "action": action_detail.get("action_type", user.get("current_action", "")),
                "current": action_detail.get("hours_completed", 0),
                "total": action_detail.get("planned_hours", action_detail.get("hours", 0)),
            }
        
        # Buff
        buff_tags = ""
        active_buffs = user.get("checkin", {}).get("active_buffs", [])
        valid_buffs = [b for b in active_buffs if not BuffManager.is_expired(b)]
        if valid_buffs:
            buff_tags = " ".join([
                f"<span class='buff-tag'>{b.get('emoji','')}{b.get('name','')}</span>" 
                for b in valid_buffs[:3]
            ])
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "gold": int(user.get("gold", 0)),
            "residence": user.get("residence", "桥下"),
            "status": user.get("status", "空闲"),
            "progress": progress,
            "buff_tags": buff_tags,
            "health": int(attrs.get("health", 0)),
            "strength": int(attrs.get("strength", 0)),
            "energy": int(attrs.get("energy", 0)),
            "mood": int(attrs.get("mood", 0)),
            "satiety": int(attrs.get("satiety", 0)),
        }
        
        height = 400 + (40 if progress else 0) + (35 if buff_tags else 0)
        return await self._render(CardType.STATUS, data, height)
    
    async def render_checkin(self, user: dict, event, result: dict, already_checked: bool = False) -> str:
        """渲染签到卡片"""
        from .checkin import get_luck_rating
        
        user_id = str(event.get_sender_id())
        checkin = user.get("checkin", {})
        streak = checkin.get("streak", 0)
        
        # 优先使用新版品级信息，否则降级到旧版兼容
        grade_info = result.get("grade_info")
        fortune_text = result.get("fortune", "")
        
        if grade_info:
            luck_emoji = grade_info.get("emoji", "🎲")
            luck_name = grade_info.get("name", "神秘品级")
            luck_desc = fortune_text  # 签文作为描述
        else:
            # 降级：旧版兼容
            luck_rating = get_luck_rating(result.get("luck_value", 50))
            luck_emoji = luck_rating.get("emoji", "🎲")
            luck_name = luck_rating.get("name", "普通人")
            luck_desc = luck_rating.get("desc", "")

        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "luck_emoji": luck_emoji,
            "luck_name": luck_name,
            "luck_desc": luck_desc,
            "gold": result.get("total_gold", 0),
            "streak": streak,
            "streak_bonus": result.get("streak_bonus", 0) if not already_checked else None,
            "drop": result.get("drop_info", ""),
            "already": already_checked,
            "is_new_user": result.get("is_new_user", False),
        }
        
        return await self._render(CardType.CHECKIN, data, 400)
    
    async def render_checkin_stats(self, user: dict, event) -> str:
        """渲染签到统计卡片"""
        user_id = str(event.get_sender_id())
        checkin = user.get("checkin", {})
        
        luck_history = checkin.get("luck_history", [])
        total_days = checkin.get("total_days", 0)
        total_gold = checkin.get("total_gold", 0)
        lucky_drops = checkin.get("lucky_drops", 0)
        max_streak = checkin.get("max_streak", 0)
        
        # 统计各等级次数
        super_lucky = lucky = normal = unlucky = super_unlucky = 0
        for luck in luck_history:
            if luck >= 90:
                super_lucky += 1
            elif luck >= 70:
                lucky += 1
            elif luck >= 40:
                normal += 1
            elif luck >= 20:
                unlucky += 1
            else:
                super_unlucky += 1
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "total_days": total_days,
            "total_gold": total_gold,
            "lucky_drops": lucky_drops,
            "max_streak": max_streak,
            "super_lucky": super_lucky,
            "lucky": lucky,
            "normal": normal,
            "unlucky": unlucky,
            "super_unlucky": super_unlucky,
        }
        
        return await self._render(CardType.CHECKIN_STATS, data, 380)
    
    async def render_buff_list(self, user: dict, event) -> str:
        """渲染Buff列表卡片"""
        from .buff import BuffManager
        
        user_id = str(event.get_sender_id())
        checkin = user.get("checkin", {})
        active_buffs = checkin.get("active_buffs", [])
        valid_buffs = [b for b in active_buffs if not BuffManager.is_expired(b)]
        
        buffs = []
        for buff in valid_buffs:
            buffs.append({
                "emoji": buff.get("emoji", "✨"),
                "name": buff.get("name", "未知"),
                "desc": buff.get("desc", ""),
            })
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "buffs": buffs,
        }
        
        height = 150 + len(buffs) * 35 if buffs else 150
        return await self._render(CardType.BUFF_LIST, data, min(height, 800))
    
    async def render_job_list(self, jobs: dict, user: dict, event) -> str:
        """渲染工作列表卡片"""
        user_id = str(event.get_sender_id())
        
        physical_jobs = []
        mental_jobs = []
        
        for job_id, job in jobs.items():
            job_type = job.get("type", "physical")
            emoji = "💪" if job_type == "physical" else "🧠" if job_type == "mental" else "⭐"
            item = {
                "emoji": emoji,
                "name": job.get("name", job_id),
                "skill": job.get("skill_required", "无"),
                "gold": job.get("hourly_gold", 0),
            }
            if job_type == "physical":
                physical_jobs.append(item)
            elif job_type == "mental":
                mental_jobs.append(item)
            else:
                physical_jobs.append(item)  # 归入体力类
        
        data = {
            **self._get_base_data(user_id),
            "physical_jobs": physical_jobs[:5],
            "mental_jobs": mental_jobs[:5],
        }
        
        height = 200 + (len(physical_jobs) + len(mental_jobs)) * 45
        return await self._render(CardType.JOB_LIST, data, min(height, 800))
    
    async def render_job_start(self, user: dict, event, job_name: str, job_emoji: str, 
                               hours: int, expected_gold: int, expected_exp: int,
                               consume_strength: int, consume_energy: int, consume_satiety: int,
                               active_buffs: str = None) -> str:
        """渲染开始工作卡片"""
        user_id = str(event.get_sender_id())
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "job_name": job_name,
            "job_emoji": job_emoji,
            "hours": hours,
            "expected_gold": expected_gold,
            "expected_exp": expected_exp,
            "consume_strength": consume_strength,
            "consume_energy": consume_energy,
            "consume_satiety": consume_satiety,
            "active_buffs": active_buffs,
        }
        
        return await self._render(CardType.JOB_START, data, 420)

    async def render_job_pool(self, user: dict, pool: list, recommended: dict,
                             fmgr, jmgr, event) -> str:
        """渲染委托池卡片"""
        user_id = str(event.get_sender_id())

        DIFF_ICON = {"D": "🟢", "C": "🔵", "B": "🟡", "A": "🟠", "S": "🔴", "S+": "💜"}

        pools_data = []
        for i, job in enumerate(pool, 1):
            company = jmgr.get_company_info(job.company_id)
            pools_data.append({
                "index": i,
                "title": f"{i}. {job.title}",
                "emoji": company.get("emoji", "📋") if company else "📋",
                "company_emoji": company.get("emoji", "") if company else "",
                "company_name": company.get("name", job.company_id) if company else job.company_id,
                "base_reward": job.base_reward,
                "duration_hours": job.duration_hours,
                "difficulty": job.difficulty,
                "diff_icon": DIFF_ICON.get(job.difficulty, "⚪"),
            })

        recommended_data = []
        favor_data = user.get("company_favorability", {})
        for cid, jobs in recommended.items():
            company = jmgr.get_company_info(cid)
            if not company:
                continue
            favor = favor_data.get(cid, 0)
            level = fmgr.get_favor_level(favor)
            recommended_data.append({
                "emoji": company.get("emoji", ""),
                "name": company.get("name", cid),
                "level": level["level"],
                "level_name": level["name"],
                "jobs": [
                    {
                        "title": f"[{j.get('job_id', '??')}] {j.get('title', '')}",
                        "emoji": company.get("emoji", "📋"),
                        "base_reward": j.get("base_reward", 0),
                        "duration_hours": j.get("duration_hours", 1),
                        "difficulty": j.get("difficulty", "D"),
                        "diff_icon": DIFF_ICON.get(j.get("difficulty", "D"), "⚪"),
                    }
                    for j in jobs[:2]
                ],
            })

        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "pools": pools_data,
            "recommended": recommended_data,
        }

        height = 200 + len(pools_data) * 60 + len(recommended_data) * 120
        return await self._render(CardType.JOB_POOL, data, min(height, 800))

    async def render_job_complete(self, user: dict, event, eval_result: dict,
                                  rewards: dict) -> str:
        """渲染委托完成卡片"""
        user_id = str(event.get_sender_id())

        grade = eval_result.get("grade", "B")
        GRADE_EMOJI = {"S": "🏆", "A": "🌟", "B": "👍", "C": "😐", "D": "😥", "F": "💀"}
        GRADE_NAME = {"S": "完美", "A": "优秀", "B": "良好", "C": "合格", "D": "较差", "F": "失败"}

        exp_str = ""
        if rewards.get("exp"):
            exp_str = ", ".join([f"{k}+{v}" for k, v in rewards.get("exp", {}).items()])

        favor_change = rewards.get("favor_change", 0)

        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "grade_emoji": GRADE_EMOJI.get(grade, "👍"),
            "grade_name": GRADE_NAME.get(grade, grade),
            "total_score": eval_result.get("score", 0),
            "total_gold": rewards.get("gold", 0),
            "gold": rewards.get("gold", 0),
            "favor_change": favor_change,
            "exp_str": exp_str,
            "efficiency": eval_result.get("efficiency", 0),
            "quality": eval_result.get("quality", 0),
            "stress_bonus": eval_result.get("stress_bonus", 0),
            "mood_bonus": eval_result.get("mood_bonus", 0),
            "skill_bonus": eval_result.get("skill_bonus", 0),
            "buff_bonus": eval_result.get("buff_bonus", 0),
        }

        return await self._render(CardType.JOB_COMPLETE, data, 420)

    async def render_course_list(self, courses: dict, user: dict, event) -> str:
        """渲染课程列表卡片"""
        user_id = str(event.get_sender_id())
        
        course_list = []
        for course_id, course in courses.items():
            course_list.append({
                "name": course.get("name", course_id),
                "type": course.get("type", "通用"),
                "skill": course.get("skill", "无"),
                "cost": course.get("cost", 0),
                "exp": course.get("exp", 0),
            })
        
        data = {
            **self._get_base_data(user_id),
            "courses": course_list[:8],
        }
        
        height = 150 + len(course_list) * 50
        return await self._render(CardType.COURSE_LIST, data, min(height, 800))

    async def render_course_start(self, user: dict, event, course_name: str, course_emoji: str,
                                   hours: int, gain_exp: int,
                                   consume_strength: int, consume_energy: int, consume_mood: int) -> str:
        """渲染开始学习卡片"""
        user_id = str(event.get_sender_id())

        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "course_name": course_name,
            "course_emoji": course_emoji,
            "hours": hours,
            "gain_exp": gain_exp,
            "consume_strength": consume_strength,
            "consume_energy": consume_energy,
            "consume_mood": consume_mood,
        }

        return await self._render(CardType.COURSE_START, data, 380)

    async def render_food_list(self, foods: dict, user: dict, event) -> str:
        """渲染食物列表卡片"""
        user_id = str(event.get_sender_id())
        
        food_list = []
        for food_id, food in foods.items():
            effects = []
            for key, label in [("restore_health", "❤️"), ("restore_strength", "💪"), 
                              ("restore_energy", "⚡"), ("restore_mood", "😊"), ("restore_satiety", "🍖")]:
                val = food.get(key, 0)
                if val > 0:
                    effects.append(f"{label}+{val}")
            
            food_list.append({
                "emoji": food.get("emoji", "🍖"),
                "name": food.get("name", food_id),
                "price": food.get("price", 0),
                "effects": " ".join(effects) if effects else "无效果",
            })
        
        data = {
            **self._get_base_data(user_id),
            "foods": food_list[:8],
        }
        
        height = 150 + len(food_list) * 50
        return await self._render(CardType.FOOD_LIST, data, min(height, 550))
    
    async def render_eat(self, user: dict, event, food_name: str, food_emoji: str,
                        restore_health: int, restore_strength: int, restore_energy: int,
                        restore_mood: int, restore_satiety: int = 0) -> str:
        """渲染吃东西卡片"""
        user_id = str(event.get_sender_id())
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "food_name": food_name,
            "food_emoji": food_emoji,
            "restore_health": restore_health,
            "restore_strength": restore_strength,
            "restore_energy": restore_energy,
            "restore_mood": restore_mood,
            "restore_satiety": restore_satiety,
        }
        
        return await self._render(CardType.EAT, data, 380)
    
    async def render_residence(self, user: dict, event, residence_info: dict = None) -> str:
        """渲染住所卡片"""
        user_id = str(event.get_sender_id())
        
        res_name = user.get("residence", "桥下")
        res_emoji = "🏠"
        res_type = "免费住所"
        cost_label = "租金"
        cost_value = "免费"
        passive_strength = 2
        passive_energy = 2
        sleep_bonus = 1.0
        
        if residence_info:
            res_emoji = residence_info.get("emoji", "🏠")
            res_type = residence_info.get("type", "住所")
            if residence_info.get("type") == "租":
                cost_label = "租金"
                cost_value = f"{residence_info.get('rent', 0)}金/天"
                passive_strength = residence_info.get("passive_strength", 5)
                passive_energy = residence_info.get("passive_energy", 5)
                sleep_bonus = residence_info.get("sleep_bonus", 1.5)
            else:
                cost_label = "售价"
                cost_value = f"{residence_info.get('price', 0)}金"
                passive_strength = residence_info.get("passive_strength", 10)
                passive_energy = residence_info.get("passive_energy", 10)
                sleep_bonus = residence_info.get("sleep_bonus", 2.0)
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "res_emoji": res_emoji,
            "res_name": res_name,
            "res_type": res_type,
            "cost_label": cost_label,
            "cost_value": cost_value,
            "passive_strength": passive_strength,
            "passive_energy": passive_energy,
            "sleep_bonus": sleep_bonus,
        }
        
        return await self._render(CardType.RESIDENCE, data, 350)
    
    async def render_housing_list(self, rentals: dict, purchases: dict, user: dict, event) -> str:
        """渲染房产列表卡片"""
        user_id = str(event.get_sender_id())
        
        rental_list = []
        for house_id, house in rentals.items():
            rental_list.append({
                "emoji": house.get("emoji", "🏠"),
                "name": house.get("name", house_id),
                "desc": house.get("desc", ""),
                "rent": house.get("rent", 0),
            })
        
        purchase_list = []
        for house_id, house in purchases.items():
            purchase_list.append({
                "emoji": house.get("emoji", "🏠"),
                "name": house.get("name", house_id),
                "desc": house.get("desc", ""),
                "price": house.get("price", 0),
            })
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "rentals": rental_list[:5],
            "purchases": purchase_list[:5],
        }
        
        height = 150 + (len(rental_list) + len(purchase_list)) * 50
        return await self._render(CardType.HOUSING_LIST, data, min(height, 800))
    
    async def render_entertainment_list(self, entertainments: dict, user: dict, event) -> str:
        """渲染娱乐列表卡片"""
        user_id = str(event.get_sender_id())
        
        ent_list = []
        for ent_id, ent in entertainments.items():
            ent_list.append({
                "emoji": ent.get("emoji", "🎮"),
                "name": ent.get("name", ent_id),
                "type": ent.get("type", "娱乐"),
                "cost": ent.get("cost", 0),
                "gain_mood": ent.get("gain_mood", 0),
                "consume_satiety": ent.get("consume_satiety", 0),
            })
        
        data = {
            **self._get_base_data(user_id),
            "entertainments": ent_list[:8],
        }
        
        height = 150 + len(ent_list) * 50
        return await self._render(CardType.ENTERTAINMENT_LIST, data, min(height, 550))
    
    async def render_entertain_start(self, user: dict, event, ent_name: str, ent_emoji: str,
                                    hours: int, gain_mood: int, consume_satiety: int) -> str:
        """渲染开始娱乐卡片"""
        user_id = str(event.get_sender_id())
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "ent_name": ent_name,
            "ent_emoji": ent_emoji,
            "hours": hours,
            "gain_mood": gain_mood,
            "consume_satiety": consume_satiety,
        }
        
        return await self._render(CardType.JOB_START, data, 380)
    
    async def render_sleep(self, user: dict, event, hours: int, residence: str, 
                          sleep_bonus: float, strength_rec: int, energy_rec: int,
                          mood_rec: int, health_rec: int) -> str:
        """渲染开始睡眠卡片"""
        user_id = str(event.get_sender_id())
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "res_name": residence,
            "hours": hours,
            "sleep_bonus": sleep_bonus,
            "strength_rec": strength_rec,
            "energy_rec": energy_rec,
            "mood_rec": mood_rec,
            "health_rec": health_rec,
        }
        
        return await self._render(CardType.JOB_START, data, 400)
    
    async def render_error(self, title: str, message: str, event) -> str:
        """渲染错误卡片"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = {
            **self._get_base_data(user_id),
            "error_title": title,
            "error_message": message,
        }
        return await self._render(CardType.ERROR, data, 160)
    
    async def render_success(self, message: str, event) -> str:
        """渲染成功卡片"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = {
            **self._get_base_data(user_id),
            "success_message": message,
        }
        return await self._render(CardType.SUCCESS, data, 120)
    
    async def render_help(self, event) -> str:
        """渲染帮助卡片"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = self._get_base_data(user_id)
        return await self._render(CardType.HELP, data, 460)
    
    async def render_stock_market(self, stocks: list, user: dict, event, status: str) -> str:
        """渲染股票市场卡片，渲染失败时回退纯文本"""
        user_id = str(event.get_sender_id())
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "gold": int(user.get("gold", 0)),
            "status": status,
            "stocks": stocks,
        }
        
        height = 150 + len(stocks) * 50
        try:
            return await self._render(CardType.STOCK_MARKET, data, min(height, 450))
        except RuntimeError as e:
            if "All endpoints failed" in str(e):
                raise
            raise
    
    async def render_stock_holdings(self, holdings: list, user: dict, event, total_profit: int) -> str:
        """渲染持股卡片"""
        user_id = str(event.get_sender_id())
        
        total_profit_str = f"+{total_profit}" if total_profit >= 0 else str(total_profit)
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "holdings": holdings,
            "total_profit": total_profit,
            "total_profit_str": total_profit_str,
        }
        
        height = 150 + len(holdings) * 70 if holdings else 150
        return await self._render(CardType.STOCK_HOLDINGS, data, min(height, 500))
    
    async def render_backpack(self, items: list, user: dict, event, filter_label: str = "") -> str:
        """渲染背包卡片 (9/5: 加 filter_label)"""
        user_id = str(event.get_sender_id()) if event else "system"

        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "items": items,
            "filter_label": filter_label,
        }
        
        height = 150 + len(items) * 45 if items else 150
        return await self._render(CardType.BACKPACK, data, min(height, 500))

    async def render_shop(self, shop_name: str, fixed_items: list = None, random_items: list = None,
                     user: dict = None, event = None, section_title: str = None,
                     categories: list = None, tier_groups: list = None) -> str:
        """渲染商店卡片

        9/5: 支持三种入参格式:
        - categories: 整合页面 (模板 for cat in categories / item in cat.item_list)
        - tier_groups: 单分类按 tier 分组 (模板 for group in tier_groups)
        - fixed_items: 扁平模式 (向后兼容)
        """
        user_id = str(event.get_sender_id()) if event else "system"
        # 9/5: 优先用 categories 模式 (与模板一致)
        if categories is not None:
            data = {
                **self._get_base_data(user_id),
                "nickname": (user or {}).get("nickname", "未知"),
                "gold": int((user or {}).get("gold", 0)),
                "shop_name": shop_name,
                "section_title": section_title or "",
                "categories": categories,
                "tier_groups": tier_groups or [],
                "fixed_items": fixed_items or [],
                "random_items": random_items or [],
            }
        elif tier_groups is not None:
            data = {
                **self._get_base_data(user_id),
                "nickname": (user or {}).get("nickname", "未知"),
                "gold": int((user or {}).get("gold", 0)),
                "shop_name": shop_name,
                "section_title": section_title or "",
                "tier_groups": tier_groups,
                "categories": categories or [],
                "fixed_items": fixed_items or [],
                "random_items": random_items or [],
            }
        else:
            # 老接口兼容 (固定物品+随机物品模式)
            data = {
                **self._get_base_data(user_id),
                "nickname": (user or {}).get("nickname", "未知"),
                "gold": int((user or {}).get("gold", 0)),
                "shop_name": shop_name,
                "section_title": section_title or "",
                "fixed_items": fixed_items or [],
                "random_items": random_items or [],
                "tier_groups": tier_groups or [],
            }
        total_items = (len(fixed_items or []) + len(random_items or []) +
                       sum(len(c.get("item_list", [])) for c in (categories or [])) +
                       sum(len(g.get("item_list", [])) for g in (tier_groups or [])))
        # 9/5: 商店模板按分类分块, 每分类有自己的 sub-title + grid 区域
        # 实测: 头部140 + 每分类sub-title 25 + 每行grid 90 (含 3 件物品 + 间距)
        n_categories = len(categories or []) if categories else (len(tier_groups or []) if tier_groups else 1)
        rows_per_category = (total_items / 3.0) / max(1, n_categories) if n_categories else 0
        height = 140 + (n_categories * 25) + (n_categories * rows_per_category * 90) + (total_items * 5) + 60
        # 9/5: 商店模板是 880px 宽, 用更宽 viewport + full_page 截完整高度
        return await self._render(CardType.SHOP, data, int(height), width=880, full_page=True)
    
    async def render_generic(self, content: str, event, height: int = 200) -> str:
        """渲染通用卡片"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = {
            **self._get_base_data(user_id),
            "nickname": "玩家",
            "content": content,
        }
        return await self._render(CardType.GENERIC, data, height)

    async def render_fishing_catch(self, user: dict, catch: dict, title_unlocked: str = None,
                                exp_gain: int = 0) -> str:
        """渲染钓鱼结果卡片 (9/5: 加 exp_gain; 9/6: rarity_color 染色; 9/8: weight_str + length_str_compact)"""
        from ..src.fishing.fishing_manager import format_weight, format_length_compact
        user_id = str(user.get("user_id", "system"))
        fish = catch.get("fish", {})
        # 9/8: 优先用 final_rarity (catch 顶层), 兜底用基础 rarity (fish 字典)
        rarity = catch.get("rarity") or fish.get("rarity", "common")
        rarity_cn = {"common": "常见", "uncommon": "不凡", "rare": "稀有", "epic": "史诗", "legendary": "传奇", "mythic": "神话"}.get(
            rarity, "常见"
        )
        rarity_color_map = {  # 9/6: 与 modules.item.RARITY_HEX_COLORS 同步
            "common": ("#9e9e9e", "rgba(158,158,158,0.3)"),
            "uncommon": ("#7bed9f", "rgba(123,237,159,0.3)"),
            "rare": ("#4fc3f7", "rgba(79,195,247,0.3)"),
            "epic": ("#c586c0", "rgba(197,134,192,0.3)"),
            "legendary": ("#ffa726", "rgba(255,167,38,0.3)"),
            "mythic": ("#ff6b6b", "rgba(255,107,107,0.3)"),
        }
        rarity_hex_val, rarity_bg = rarity_color_map.get(rarity, rarity_color_map["common"])
        base = self._get_base_data(user_id)
        weight = catch.get("weight", 0)
        length_cm = catch.get("length_cm")
        data = {
            **base,
            "nickname": user.get("nickname", "玩家"),
            "fish_emoji": fish.get("emoji", "🐟"),
            "fish_name": fish.get("name", "未知"),
            "size_label": catch.get("size_label", "普通"),
            "weight": weight,
            "weight_str": format_weight(weight),  # 9/8: 紧凑格式
            "length_cm": length_cm,
            "length_str_compact": format_length_compact(length_cm),  # 9/8: 紧凑格式
            "rarity_cn": rarity_cn,
            "rarity_color": rarity_hex_val,  # 9/6: UI 染色
            "rarity_bg": rarity_bg,  # 9/6: 鱼展示区背景渐变
            "rarity": rarity,  # 9/6: 给模板判断加粗
            "estimated_price": catch.get("estimated_price", 0),
            "spot": catch.get("spot", catch.get("_spot", "")),
            "exp_gain": exp_gain or fish.get("exp_reward", 0),
            "title_unlocked": title_unlocked,
            "satiety_restore": fish.get("satiety_restore", 0),
            "mood_restore": fish.get("mood_restore", 0),
        }
        return await self._render(CardType.FISHING_CARD, data, 520, full_page=True)

    # 9/7 命名统一: 参数名 capacity_rod → capacity_fishing_rod
    # 9/7 命名统一: 参数名 capacity_line → capacity_fishing_line
    async def render_fishing_gear(self, user: dict, event,
                                  gear_slots: dict, effects: dict,
                                  capacity_fishing_rod: float, capacity_fishing_line: float,
                                  diet_zh: str,
                                  inventory_gear: list) -> str:
        """渲染渔具卡片 (9/5 补)"""
        user_id = str(event.get_sender_id()) if event else "system"
        # gear_slots 可能是 dict 或 list, 模板用 for slot 迭代
        if isinstance(gear_slots, dict):
            gear_slots_list = list(gear_slots.values())
        elif isinstance(gear_slots, list):
            gear_slots_list = gear_slots
        else:
            gear_slots_list = []
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "user_id": user_id,
            "gear_slots": gear_slots_list,
            "effects": effects or {},
            # 9/7 命名统一: 参数名 capacity_line → capacity_fishing_line
            "capacity_fishing_rod": capacity_fishing_rod or 0,
            "capacity_fishing_line": capacity_fishing_line or 0,
            "diet_zh": diet_zh or "不限",
            "inventory_gear": inventory_gear or [],
            "inventory_gear_count": len(inventory_gear or []),
        }
        height = 200 + len(gear_slots_list) * 55 + len(data["inventory_gear"]) * 45
        return await self._render(CardType.FISHING_GEAR, data, min(height, 700), full_page=True)

    async def render_fishing_spots(self, user: dict, event, spots: list, current_spot: str = "",
                                   skill_level: int = 1, gold: int = 0,
                                   rod_id: str = "", bait_id: str = "") -> str:
        """渲染钓鱼水域选择卡片 (9/5 补)"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "user_id": user_id,
            "spots": spots or [],
            "current_spot": current_spot,
            "skill_level": skill_level,
            "gold": gold,
            "rod_id": rod_id or "空手",
            "bait_id": bait_id or "无",
        }
        height = 200 + len(spots or []) * 60
        return await self._render(CardType.FISHING_SPOTS, data, min(height, 600), full_page=True)

    async def render_fish_dex(self, user: dict, event, caught: dict, all_fish: dict) -> str:
        """渲染鱼塘图鉴卡片。"""
        user_id = str(event.get_sender_id()) if event else "system"
        fish_items = []
        for fname, info in all_fish.items():
            cnt = caught.get(fname, 0)
            fish_items.append({
                "emoji": info.get("emoji", "🐟"),
                "name": fname,
                "rarity": info.get("rarity", "common"),
                "caught": cnt,
                "locked": cnt == 0,
            })
        # 按稀有度排序
        order = {"legendary": 0, "epic": 1, "rare": 2, "uncommon": 3, "common": 4}
        fish_items.sort(key=lambda x: (order.get(x["rarity"], 99), x["name"]))

        from ..src.fishing.fishing_manager import format_weight  # 9/8: 紧凑重量格式
        biggest = user.get("fishing", {}).get("biggest_catch", {})
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "玩家"),
            "fish_items": fish_items,
            "caught_count": len(caught),
            "total_count": len(all_fish),
            "biggest": biggest,
            "biggest_weight_str": format_weight(biggest.get("weight", 0)) if biggest else "",  # 9/8: 紧凑格式
            "title": user.get("fishing", {}).get("fish_title", ""),
        }
        height = 200 + len(fish_items) * 40
        return await self._render(CardType.FISH_DEX, data, min(height, 700))
    
    # ========== 便捷包装方法 ==========

    async def render(self, card_type: str, data: dict, event, height: int = None) -> str:
        """通用渲染接口"""
        return await self._render(card_type, data, height)

    # 9/4晚: 附魔结果卡片 (含词条一览 + 基础属性)
    async def render_enchant(
        self,
        event,
        user: dict,
        target_entry: dict,
        old_rarity: str,
        old_mult: float,
        new_rarity: str,
        new_mult: float,
        new_effects: dict,
        scroll_name: str,
        scroll_remaining: int,
        scroll_color: str,
    ) -> str:
        """渲染附魔结果卡片

        Args:
            target_entry: inventory entry (附魔后的)
            old_rarity/old_mult: 附魔前
            new_rarity/new_mult: 附魔后
            new_effects: resolve_effects(item, new_rarity, new_mult) 的结果
            scroll_name: 附魔券名
            scroll_remaining: 附魔券剩余数量
        """
        from .item import RARITY_NAMES, rarity_hex  # 9/6: rarity 染色
        from .entry_lib import COMMON_ENTRY_LIB, SPECIAL_ENTRY

        user_id = str(event.get_sender_id()) if event else "system"
        nickname = user.get("nickname", "玩家")
        item_name = target_entry.get("name") or target_entry.get("id", "未知")

        # 9/4晚: 明确区分词条 vs 基础属性
        # 基础属性白名单 (装备专属属性)
        BASE_ATTR_KEYS = {"load_capacity_max", "max_hook_slots", "duration_reduce",
                          "habitat_filter", "target_diet", "target_size_weights"}

        # 词条分类: flat vs pct
        entries = []
        for k, v in new_effects.items():
            if not isinstance(v, (int, float)):
                continue
            if k in BASE_ATTR_KEYS:
                continue
            # 9/4晚: 处理 *_pct 后缀字段 - 取出原始 key + 标记 type="pct"
            is_pct_field = k.endswith("_pct")
            raw_k = k[:-4] if is_pct_field else k
            entry_type = "pct" if is_pct_field else "flat"

            if raw_k in COMMON_ENTRY_LIB:
                # flat 字段用 entry_def.type, pct 字段强制 pct
                if not is_pct_field:
                    entry_type = COMMON_ENTRY_LIB[raw_k].get("type", "flat")
            elif raw_k in SPECIAL_ENTRY:
                if not is_pct_field:
                    entry_type = SPECIAL_ENTRY[raw_k].get("type", "flat")
            else:
                continue
            # 跳过 0 词条
            if v == 0:
                continue
            entries.append({
                "icon": get_entry_icon(raw_k),
                "name": get_entry_name(raw_k),
                "type": entry_type,
                "value": round(v, 2),
            })
        entries.sort(key=lambda e: (0 if e["type"] == "pct" else 1, -e["value"]))

        # 基础属性
        base_attrs = []
        for k, v in new_effects.items():
            if not isinstance(v, (int, float)):
                continue
            if k not in BASE_ATTR_KEYS:
                continue
            # duration_reduce > 0 才显示
            if k == "duration_reduce" and v <= 0:
                continue
            base_attrs.append({
                "name": get_base_attr_name(k),
                "old": "",
                "new": format_base_attr_value(k, v),
                "diff": False,
            })

        rarity_color_map = {
            "common":    ("#9e9e9e", "#616161"),
            "uncommon":  ("#7CFC00", "#228B22"),
            "rare":      ("#4FC3F7", "#0288D1"),
            "epic":      ("#BA68C8", "#7B1FA2"),
            "legendary": ("#FFB74D", "#E65100"),
            "mythic":    ("#EF5350", "#B71C1C"),
        }
        new_rarity_color, new_rarity_color_dark = rarity_color_map.get(new_rarity, ("#9e9e9e", "#616161"))

        data = {
            **self._get_base_data(user_id),
            "nickname": nickname,
            "item_name": item_name,
            "old_rarity_cn": RARITY_NAMES.get(old_rarity, old_rarity),
            "old_mult": old_mult,
            "new_rarity_cn": RARITY_NAMES.get(new_rarity, new_rarity),
            "new_mult": new_mult,
            "new_rarity_color": new_rarity_color,
            "new_rarity_color_dark": new_rarity_color_dark,
            "entries": entries,
            "entry_count": len(entries),
            "base_attrs": base_attrs,
            "scroll_name": scroll_name,
            "scroll_color": scroll_color,
            "scroll_remaining": scroll_remaining,
        }
        return await self._render(CardType.ENCHANT, data, height=600)


# ============================================================
# 9/4晚: 附魔卡片辅助 (模块级)
# ============================================================

_ENTRY_ICON = {
    "success_rate": "🎣",
    "habitat_pond": "🏞️", "habitat_river": "🏞️", "habitat_reservoir": "🌊",
    "habitat_coast": "🌊", "habitat_deep_sea": "🌊",
    "rarity_common_bonus": "⬆️", "rarity_legendary_bonus": "🌟", "rarity_mythic_bonus": "💎",
    "rarity_pct_bonus": "📈",
    "exp_bonus": "✨",
    "size_titan_bonus": "📏", "size_giant_bonus": "📏", "size_huge_bonus": "📏",
    "size_large_bonus": "📏", "size_medium_bonus": "📏", "size_small_bonus": "📏", "size_tiny_bonus": "📏",
    "price_bonus": "💰",
    "stamina_reduce": "⚡",
    "load_capacity": "⚖️",
    "bait_no_consume": "🪱",
    "diet_carnivore_bonus": "🥩", "diet_herbivore_bonus": "🌿", "diet_omnivore_bonus": "🍽️",
    "max_hook_slots": "🪝",
}

_ENTRY_NAME = {
    "success_rate": "中鱼权重",
    "habitat_pond": "池塘水域", "habitat_river": "河流水域", "habitat_reservoir": "水库水域",
    "habitat_coast": "海岸水域", "habitat_deep_sea": "深海水域",
    "rarity_common_bonus": "非普通鱼权重", "rarity_legendary_bonus": "传说鱼权重", "rarity_mythic_bonus": "神话鱼权重",
    "rarity_pct_bonus": "非普通鱼权重(%)",
    "exp_bonus": "钓鱼经验加成",
    "size_titan_bonus": "泰坦级鱼权重", "size_giant_bonus": "超巨型鱼权重", "size_huge_bonus": "巨型鱼权重",
    "size_large_bonus": "大型鱼权重", "size_medium_bonus": "中型鱼权重", "size_small_bonus": "小型鱼权重", "size_tiny_bonus": "微型鱼权重",
    "price_bonus": "鱼价值加成",
    "stamina_reduce": "体力消耗减免",
    "load_capacity": "承载力加成",
    "bait_no_consume": "鱼饵不消耗概率",
    "diet_carnivore_bonus": "肉食鱼权重", "diet_herbivore_bonus": "草食鱼权重", "diet_omnivore_bonus": "杂食鱼权重",
    "max_hook_slots": "钩槽数+1",
}

_BASE_ATTR_NAME = {
    "load_capacity_max": "承载力上限",
    "max_hook_slots": "钩槽数",
    "duration_reduce": "收竿加速",
}


def get_entry_icon(key: str) -> str:
    return _ENTRY_ICON.get(key, "📊")


def get_entry_name(key: str) -> str:
    return _ENTRY_NAME.get(key, key)


def get_base_attr_name(key: str) -> str:
    return _BASE_ATTR_NAME.get(key, key)


def format_base_attr_value(key: str, value) -> str:
    if key == "load_capacity_max":
        return f"{value}kg"
    if key == "max_hook_slots":
        return str(int(value))
    if key == "duration_reduce":
        return f"-{value}s"
    return str(value)


# ============================================================
# 9/5: 本地 Chromium 渲染器 (绕过 AstrBot 远程 T2I)
# ============================================================
import logging as _logging

_log = _logging.getLogger(__name__)

# Playwright Chromium 路径
import glob as _glob
_PLAYWRIGHT_CHROME_PATHS = (
    _glob.glob("/home/alex/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
    + _glob.glob("/home/alex/.cache/ms-playwright/chromium-*/chrome-linux*/headless_shell")
)


class _SilentUndefined(jinja2.Undefined):
    """Jinja2 自定义 Undefined: 缺失字段静默当作空, 任何比较返回 False"""
    def __str__(self): return ""
    def __repr__(self): return ""
    def __bool__(self): return False
    def __int__(self): return 0
    def __float__(self): return 0.0
    def __len__(self): return 0
    def __iter__(self): return iter([])
    def __call__(self, *args, **kwargs): return self
    def __getitem__(self, key): return self
    def __getattr__(self, name): return self
    def __lt__(self, other): return False
    def __le__(self, other): return False
    def __gt__(self, other): return False
    def __ge__(self, other): return False
    def __eq__(self, other): return False
    def __ne__(self, other): return True
    def __add__(self, other): return other if isinstance(other, (int, float, str)) else self
    def __radd__(self, other): return other if isinstance(other, (int, float, str)) else self
    def __sub__(self, other): return 0
    def __rsub__(self, other): return other if isinstance(other, (int, float)) else 0
    def __mul__(self, other): return 0
    def __rmul__(self, other): return 0
    def __truediv__(self, other): return 0
    def __hash__(self): return 0


class _LocalRenderer:
    """本地 Chromium HTML -> PNG 渲染器 (独立模块, 不依赖 _dispatcher)

    比 AstrBot 内置 html_renderer 快 10-20 倍, 不依赖网络。
    """

    def __init__(self):
        self._enabled = bool(_PLAYWRIGHT_CHROME_PATHS)
        if self._enabled:
            self.chrome_path = _PLAYWRIGHT_CHROME_PATHS[0]
        else:
            self.chrome_path = ""

    async def render(self, tmpl_str, tmpl_data, width=380, height=500,
                     full_page=False, card_type=None):
        if not self._enabled:
            return ""
        # 1. Jinja2 渲染模板 (静默缺失字段, 不抛错)
        try:
            from jinja2 import Environment, select_autoescape
            env = Environment(
                autoescape=select_autoescape(["html", "xml"]),
                undefined=_SilentUndefined,
            )
            # 9/7: 加 intf 过滤器 - 任何数值 → int (截掉小数)
            def _intf(v):
                try:
                    if v is None or v == "":
                        return v
                    return int(float(v))
                except (ValueError, TypeError):
                    return v
            env.filters["intf"] = _intf
            tmpl = env.from_string(tmpl_str)
            html = tmpl.render(**tmpl_data)
        except Exception as e:
            _log.warning(f"[_LocalRenderer] Jinja2 渲染失败: {type(e).__name__}: {e}")
            return ""

        # 2. Playwright 截图
        import tempfile as _tf
        from pathlib import Path
        html_path = ""
        png_path = ""
        try:
            with _tf.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
                f.write(html)
                html_path = f.name
            png_path = html_path.replace(".html", ".png")

            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                )
                try:
                    # 9/5: viewport 用 height, 让 full_page 截实际内容高度
                    initial_height = height
                    context = await browser.new_context(
                        viewport={"width": width, "height": initial_height},
                        device_scale_factor=2,
                    )
                    page = await context.new_page()
                    await page.goto(f"file://{html_path}", wait_until="domcontentloaded")
                    await page.wait_for_load_state("networkidle", timeout=5000)
                    if full_page:
                        # 9/5: 用 JS 拿 body.scrollHeight, 让截图刚好裁到内容底部
                        scroll_h = await page.evaluate("document.body.scrollHeight")
                        await page.set_viewport_size({"width": width, "height": int(scroll_h) + 20})
                    await page.screenshot(path=png_path, full_page=full_page, type="png")
                finally:
                    await browser.close()
        except Exception as e:
            _log.warning(f"[_LocalRenderer] Playwright 渲染失败: {type(e).__name__}: {e}")
            return ""
        finally:
            if html_path:
                try:
                    Path(html_path).unlink(missing_ok=True)
                except Exception:
                    pass

        if png_path and Path(png_path).exists():
            _log.debug(f"[_LocalRenderer] 渲染成功 ({card_type}): {png_path}")
            return png_path
        return ""