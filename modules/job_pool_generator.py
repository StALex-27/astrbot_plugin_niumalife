"""
打工系统 V2 - 委托池生成器
根据玩家等级和技能，程序化生成可接取的委托列表
"""

import random
import json
import uuid
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class JobPoolGenerator:
    """程序化委托池生成器"""
    
    def __init__(self, config_dir: str = None):
        """初始化生成器，加载配置文件"""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "data" / "config"
        self.config_dir = Path(config_dir)
        
        self._load_configs()
        
    def _load_configs(self):
        """加载所有配置文件"""
        # 加载公司配置
        with open(self.config_dir / "companies.json", "r", encoding="utf-8") as f:
            companies_data = json.load(f)
            # 移除元数据
            self.companies = {k: v for k, v in companies_data.items() 
                            if not k.startswith("_")}
            self.difficulty_multiplier = companies_data.get("_difficulty_reward_multiplier", {})
            self.consume_multiplier = companies_data.get("_difficulty_consume_multiplier", {})
            
        # 加载委托模板
        with open(self.config_dir / "job_templates.json", "r", encoding="utf-8") as f:
            templates_data = json.load(f)
            self.templates = templates_data.get("templates", [])
            
        # 建立模板索引
        self._build_template_index()
        
    def _build_template_index(self):
        """构建模板索引，加速查询"""
        self.template_index: Dict[str, List[dict]] = {}
        for template in self.templates:
            company_id = template["company_id"]
            if company_id not in self.template_index:
                self.template_index[company_id] = []
            self.template_index[company_id].append(template)
            
    def generate_pool(self, player_data: dict, count: int = 8, 
                     include_all_difficulties: bool = False) -> List[dict]:
        """
        根据玩家数据生成委托池
        
        Args:
            player_data: 玩家数据，包含技能、等级、好感度等信息
            count: 生成委托数量，默认8个
            include_all_difficulties: 是否包含所有难度，默认False只根据好感度
            
        Returns:
            委托列表
        """
        pool = []
        player_level = player_data.get("level", 1)
        player_skills = player_data.get("skills", {})
        company_favors = player_data.get("company_favorability", {})
        
        # 收集所有可用的模板
        available_templates = self._filter_templates_by_player(
            player_level, player_skills, company_favors, include_all_difficulties
        )
        
        if not available_templates:
            return pool
            
        # 生成指定数量的委托
        for _ in range(count):
            if not available_templates:
                break
            template = random.choice(available_templates)
            job = self._instantiate_template(template, player_data)
            pool.append(job)
            # 避免重复：从可用列表中移除刚使用的模板（简单去重策略）
            if template in available_templates and len(available_templates) > count:
                available_templates.remove(template)
                
        return pool
        
    def _filter_templates_by_player(self, player_level: int, player_skills: dict,
                                     company_favors: dict,
                                     include_all_difficulties: bool = False) -> List[dict]:
        """根据玩家等级和技能过滤可用的模板"""
        available = []
        
        for template in self.templates:
            company_id = template["company_id"]
            
            # 检查公司难度档位
            company = self.companies.get(company_id, {})
            difficulty_tier = company.get("difficulty_tier", "T1")
            tier_config = self.companies.get("_difficulty_tiers", {}).get(difficulty_tier, {})
            available_diffs_in_tier = tier_config.get("available_difficulties", ["D", "C", "B"])
            
            # 检查好感度等级
            favor_level = self._get_favor_level(company_favors.get(company_id, 0))
            favor_diff_limit = self._get_difficulty_limit_by_favor(favor_level)
            
            # 获取模板支持的难度范围
            template_diffs = template.get("difficulty_range", ["D", "C"])
            
            # 找出该模板在玩家可接受范围内的难度
            for diff in template_diffs:
                # 检查难度是否在公司档位内
                if diff not in available_diffs_in_tier:
                    continue
                # 检查难度是否在好感度限制内
                if not include_all_difficulties and not self._is_difficulty_allowed(diff, favor_diff_limit):
                    continue
                # 检查玩家技能是否满足要求
                required_skills = template.get("skill_required", {}).get(diff, {})
                if self._check_skills_satisfied(player_skills, required_skills):
                    available.append(template)
                    break
                    
        return available
        
    def _check_skills_satisfied(self, player_skills: dict, required: dict) -> bool:
        """检查玩家技能是否满足要求"""
        if not required:
            return True  # 无技能要求，任何人都可以
            
        for skill, level in required.items():
            if player_skills.get(skill, 0) < level:
                return False
        return True
        
    def _get_favor_level(self, favorability: int) -> int:
        """根据好感度数值获取等级"""
        if favorability < 50:
            return 1
        elif favorability < 100:
            return 2
        elif favorability < 150:
            return 3
        elif favorability < 200:
            return 4
        elif favorability < 300:
            return 5
        elif favorability < 400:
            return 6
        elif favorability < 500:
            return 7
        elif favorability < 600:
            return 8
        elif favorability < 800:
            return 9
        else:
            return 10
            
    def _get_difficulty_limit_by_favor(self, favor_level: int) -> str:
        """根据好感度等级获取可接难度上限"""
        limits = {
            1: "D", 2: "D", 3: "C", 4: "C",
            5: "B", 6: "B", 7: "A", 8: "A",
            9: "S", 10: "S+"
        }
        return limits.get(favor_level, "D")
        
    def _is_difficulty_allowed(self, difficulty: str, limit: str) -> bool:
        """检查难度是否在允许范围内"""
        difficulty_order = ["D", "C", "B", "A", "S", "S+"]
        try:
            diff_idx = difficulty_order.index(difficulty)
            limit_idx = difficulty_order.index(limit)
            return diff_idx <= limit_idx
        except ValueError:
            return False
            
    def _instantiate_template(self, template: dict, player_data: dict) -> dict:
        """将模板实例化为具体委托"""
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        
        # 随机选择难度
        difficulty = random.choice(template.get("difficulty_range", ["D"]))
        
        # 随机选择标题
        title = random.choice(template.get("title_pool", ["任务"]))
        
        # 生成描述
        description = self._generate_description(template)
        
        # 计算基础奖励
        base_reward_range = template.get("base_reward_range", [50, 100])
        base_reward = random.randint(base_reward_range[0], base_reward_range[1])
        
        # 获取难度倍率
        diff_reward_mult = self.difficulty_multiplier.get(difficulty, 1.0)
        
        # 随机持续时间
        duration_range = template.get("duration_hours_range", [1, 4])
        duration_hours = random.randint(duration_range[0], duration_range[1])
        
        # 获取技能要求
        skill_required = template.get("skill_required", {}).get(difficulty, {})
        
        # 生成消耗
        consume = self._generate_consume(template, difficulty)
        
        # 生成经验奖励
        exp_reward = self._generate_exp(template, difficulty)
        
        # 计算好感度变化
        favor_gain = self._calculate_favorability_gain(template, difficulty)
        
        return {
            "job_id": job_id,
            "company_id": template["company_id"],
            "template_id": template["template_id"],
            "title": title,
            "description": description,
            "difficulty": difficulty,
            "difficulty_reward_multiplier": diff_reward_mult,
            "duration_hours": duration_hours,
            "base_reward": base_reward,
            "skill_required": skill_required,
            "consume": consume,
            "exp_reward": exp_reward,
            "favorability_gain": favor_gain,
            "is_public": True,
            "is_hidden": False
        }
        
    def _generate_description(self, template: dict) -> str:
        """生成描述文本"""
        desc_template = template.get("desc_template", "完成任务")
        desc_params = template.get("desc_params", {})
        
        description = desc_template
        for key, options in desc_params.items():
            placeholder = f"{{{key}}}"
            if placeholder in description and options:
                replacement = random.choice(options)
                description = description.replace(placeholder, replacement)
                
        return description
        
    def _generate_consume(self, template: dict, difficulty: str) -> dict:
        """生成属性消耗"""
        consume_template = template.get("consume_template", {})
        diff_consume_mult = self.consume_multiplier.get(difficulty, 1.0)
        
        consume = {}
        for attr, range_def in consume_template.items():
            min_val = range_def.get("min", 0)
            max_val = range_def.get("max", 10)
            base_val = random.randint(min_val, max_val)
            consume[attr] = int(base_val * diff_consume_mult)
            
        return consume
        
    def _generate_exp(self, template: dict, difficulty: str) -> dict:
        """生成经验奖励"""
        exp_template = template.get("exp_reward_template", {})
        
        exp_reward = {}
        for skill, range_def in exp_template.items():
            min_val = range_def.get("min", 5)
            max_val = range_def.get("max", 15)
            exp_reward[skill] = random.randint(min_val, max_val)
            
        return exp_reward
        
    def _calculate_favorability_gain(self, template: dict, difficulty: str) -> int:
        """计算好感度变化"""
        company_id = template.get("company_id")
        company = self.companies.get(company_id, {})
        favor_table = company.get("favorability_table", {})
        
        base = favor_table.get("complete_base", 10)
        diff_bonus = favor_table.get("complete_difficulty_bonus", 5)
        
        # 难度对应加成
        diff_bonus_map = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4, "S+": 5}
        diff_idx = diff_bonus_map.get(difficulty, 0)
        
        return base + (diff_bonus * diff_idx)
        
    def get_company_recommended_jobs(self, player_data: dict, 
                                    max_per_company: int = 2) -> Dict[str, List[dict]]:
        """
        获取按公司推荐的委托
        
        Args:
            player_data: 玩家数据
            max_per_company: 每个公司最多推荐数量
            
        Returns:
            Dict[company_id, List[job]]
        """
        result = {}
        company_favors = player_data.get("company_favorability", {})
        player_skills = player_data.get("skills", {})
        player_level = player_data.get("level", 1)
        
        # 获取所有公司
        for company_id in self.companies.keys():
            if company_id.startswith("_"):
                continue
                
            favor = company_favors.get(company_id, 0)
            favor_level = self._get_favor_level(favor)
            
            # 获取该公司模板
            templates = self.template_index.get(company_id, [])
            
            jobs = []
            for template in templates:
                template_diffs = template.get("difficulty_range", ["D"])
                
                # 检查每个难度
                for diff in template_diffs:
                    # 难度检查
                    favor_diff_limit = self._get_difficulty_limit_by_favor(favor_level)
                    if not self._is_difficulty_allowed(diff, favor_diff_limit):
                        continue
                        
                    # 技能检查
                    required = template.get("skill_required", {}).get(diff, {})
                    if not self._check_skills_satisfied(player_skills, required):
                        continue
                        
                    job = self._instantiate_template(template, player_data)
                    job["is_recommended"] = True
                    jobs.append(job)
                    
                    if len(jobs) >= max_per_company:
                        break
                        
                if len(jobs) >= max_per_company:
                    break
                    
            if jobs:
                result[company_id] = jobs
                
        return result
        
    def generate_single_job(self, company_id: str, difficulty: str = None,
                           player_data: dict = None) -> Optional[dict]:
        """
        生成单个指定公司的委托
        
        Args:
            company_id: 公司ID
            difficulty: 指定难度，不指定则随机
            player_data: 玩家数据（可选）
            
        Returns:
            委托dict或None
        """
        templates = self.template_index.get(company_id, [])
        if not templates:
            return None
            
        template = random.choice(templates)
        
        if difficulty is None:
            difficulty = random.choice(template.get("difficulty_range", ["D"]))
            
        if player_data is None:
            player_data = {}
            
        return self._instantiate_template(template, player_data)


def get_generator(config_dir: str = None) -> JobPoolGenerator:
    """获取生成器单例"""
    if not hasattr(get_generator, "_instance"):
        get_generator._instance = JobPoolGenerator(config_dir)
    return get_generator._instance


if __name__ == "__main__":
    # 测试代码
    gen = JobPoolGenerator()
    
    test_player = {
        "level": 5,
        "skills": {"编程": 3, "数学": 2, "计算机基础": 2},
        "company_favorability": {
            "company_tech": 250,
            "company_labor": 50,
            "company_business": 100
        }
    }
    
    # 测试生成公共委托池
    print("=== 公共委托池 ===")
    public_pool = gen.generate_pool(test_player, count=5)
    for job in public_pool:
        company = gen.companies.get(job["company_id"], {})
        print(f"[{job['job_id']}] {company.get('emoji', '')} {job['title']} ({job['difficulty']}) - {job['duration_hours']}小时")
        
    print("\n=== 按公司推荐 ===")
    recommended = gen.get_company_recommended_jobs(test_player, max_per_company=1)
    for cid, jobs in recommended.items():
        company = gen.companies.get(cid, {})
        print(f"\n{company.get('emoji', '')} {company.get('name', cid)}:")
        for job in jobs:
            print(f"  - {job['title']} ({job['difficulty']}) - {job['duration_hours']}小时")
