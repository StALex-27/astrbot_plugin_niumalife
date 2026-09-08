"""
LLM Tools —— 牛马人生游戏数据工具集。

让 LLM (AstrBot 接入的丽贝卡 persona) 可以自主调用这些工具访问玩家游戏数据、
执行常用操作。所有工具的 user_id 由 AstrBot 框架从当前会话上下文自动注入（plugin 注册的 llm_tool
handler 第一个 event 参数自带 get_sender_id）。

设计原则:
1. 只读工具直接返回 JSON 字符串, LLM 拿到后自行组织自然语言回复。
2. 写入工具（execute_sell）需要智能确认：
   - 玩家明确命令 ("把草鱼都卖了") → 直接执行, 不再询问
   - LLM 推测玩家意图 ("要不要把包里的杂物清一下?") → 必须 yield 确认卡, 等用户回复是/否
3. 所有工具返回字符串, AstrBot 会把它喂给下一轮 LLM 让其总结; 不能返回 None。

调用方: main.py -> initialize() 里调用 register_game_tools(plugin) 注册。
"""
from .game_tools import register_game_tools

__all__ = ["register_game_tools"]
