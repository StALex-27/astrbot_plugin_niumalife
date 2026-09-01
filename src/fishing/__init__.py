"""fishing 子包：钓鱼系统"""
from .fishing_manager import (
    roll_catch, apply_catch, check_fish_title,
    get_fishing_skill_level, get_spot, get_fish,
    FISHES, FISHING_SPOTS,
)

__all__ = [
    "roll_catch", "apply_catch", "check_fish_title",
    "get_fishing_skill_level", "get_spot", "get_fish",
    "FISHES", "FISHING_SPOTS",
]
