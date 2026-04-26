"""
命令模块
优化后的交互式命令系统 (interactive.py)
其他遗留命令已归档至 legacy/ 目录
"""

from .interactive import register_interactive_commands


def register_all_commands(plugin):
    """注册所有交互式命令"""
    register_interactive_commands(plugin)


__all__ = ['register_all_commands']
