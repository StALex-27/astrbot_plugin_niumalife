"""
命令模块
新的交互式命令系统 - 2次交互内完成操作
"""

from .interactive import register_interactive_commands


def register_all_commands(plugin):
    """
    注册所有命令到插件实例
    使用新的交互式命令系统
    """
    register_interactive_commands(plugin)


__all__ = ['register_all_commands']
