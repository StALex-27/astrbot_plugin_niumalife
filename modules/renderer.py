"""
卡片渲染器模块
牛马人生项目

使用AstrBot的html_renderer.render_custom_template()生成图片卡片
"""

from typing import Optional, Dict, Any, List
from astrbot.core import html_renderer
from .templates import CardType, get_card_template, build_avatar_url


# ============================================================
# 卡片渲染器
# ============================================================

class CardRenderer:
    """HTML卡片渲染器 - 使用AstrBot内置渲染服务"""
    
    # 渲染尺寸配置
    DEFAULT_WIDTH = 380
    DEFAULT_HEIGHT = 400
    
    async def _render(self, card_type: str, data: dict, height: int = None) -> str:
        """内部渲染方法"""
        template = get_card_template(card_type)
        if not template:
            template = get_card_template(CardType.GENERIC)
        
        render_height = height or self.DEFAULT_HEIGHT
        
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
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "gold": int(user.get("gold", 0)),
            "residence": user.get("residence", "桥下"),
            "status": user.get("status", "空闲"),
            "streak": streak,
            "total_days": total_days,
            "luck_emoji": luck_rating.get("emoji", "🎲"),
            "luck_name": luck_rating.get("name", "普通人"),
            "buff_tags": buff_tags,
            "skills_html": skills_html or "<span class='skill-tag'>暂无技能</span>",
            "warnings": warnings,
            "health": int(attrs.get("health", 0)),
            "strength": int(attrs.get("strength", 0)),
            "energy": int(attrs.get("energy", 0)),
            "mood": int(attrs.get("mood", 0)),
            "satiety": int(attrs.get("satiety", 0)),
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
        
        luck_rating = get_luck_rating(result.get("luck_value", 50))
        
        data = {
            **self._get_base_data(user_id),
            "nickname": user.get("nickname", "未知"),
            "luck_emoji": luck_rating.get("emoji", "🎲"),
            "luck_name": luck_rating.get("name", "普通人"),
            "luck_desc": luck_rating.get("desc", ""),
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
        return await self._render(CardType.BUFF_LIST, data, min(height, 500))
    
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
        return await self._render(CardType.JOB_LIST, data, min(height, 600))
    
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
        return await self._render(CardType.COURSE_LIST, data, min(height, 550))
    
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
                        restore_mood: int) -> str:
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
        return await self._render(CardType.HOUSING_LIST, data, min(height, 600))
    
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
    
    async def render_generic(self, content: str, event, height: int = 200) -> str:
        """渲染通用卡片"""
        user_id = str(event.get_sender_id()) if event else "system"
        data = {
            **self._get_base_data(user_id),
            "nickname": "玩家",
            "content": content,
        }
        return await self._render(CardType.GENERIC, data, height)
    
    # ========== 便捷包装方法 ==========
    
    async def render(self, card_type: str, data: dict, event, height: int = None) -> str:
        """通用渲染接口"""
        return await self._render(card_type, data, height)