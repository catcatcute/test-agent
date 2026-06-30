"""
============================================================
从零构建一个最基础的 ReAct Agent
============================================================

Agent 的核心骨架就是下面这个循环：
  1. 模型输出"想法 + 要调用的工具"
  2. 你的代码执行这个工具
  3. 把执行结果喂回模型
  4. 模型看到结果后继续想，或者给出最终答案

以下按步骤分解，每一块都可以独立运行理解。
"""

import asyncio
import json
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

# .env 文件中的敏感配置统一在这里加载
load_dotenv()

# ==========================================================
# 第一步：模型调用（最底层，nothing magic）
# ==========================================================
# Agent 的"大脑"就是一个 API 调用。
# 和你用 Postman 调 /v1/chat/completions 没有区别。

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

def ask_llm(messages: list[dict], tools: Optional[list[dict]] = None):
    """
    LLM 调用 —— 兼容 Function Calling
    返回 ChoiceMessage 对象，上层根据 .tool_calls / .content 判断行为
    """
    kwargs = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        kwargs["tools"] = tools
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message


# ==========================================================
# 第二步：定义工具（让 Agent 能"做"事）
# ==========================================================
# Agent 不是空谈，它需要调用真实的函数。
# 这里定义两个工具：搜索和计算器。

def search(query: str) -> str:
    """模拟搜索引擎"""
    # 真实场景换成 Google/Bing API 或内部知识库
    fake_db = {
        "杭州": "浙江省省会，2024年GDP约2.2万亿元",
        "openai": "OpenAI 是一家美国AI研究公司，2023年估值约290亿美元",
        "python": "Python 是一种高级编程语言，由 Guido van Rossum 于1991年发布"
    }
    for key, value in fake_db.items():
        if key in query.lower():
            return value
    return f"未找到与 '{query}' 相关信息"

def calculate(expression: str) -> str:
    """安全计算数学表达式"""
    try:
        # 安全：只允许数字和基本运算符
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"

# 工具实现：名称 → 函数 映射
TOOL_FUNCTIONS = {
    "search": search,
    "calculate": calculate,
}

# 工具 Schema：OpenAI 原生 tools 格式（JSON Schema 描述）
# 模型看到这个就会自动返回结构化的 tool_calls，不需要文本解析
# 所有可用工具的汇总描述
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "搜索外部信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '2+3*4'"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]


# ==========================================================
# 第三步：System Prompt（极简版）
# ==========================================================
# 工具信息不再写在 prompt 里，而是通过 tools 参数传给 API。
# 模型会自动根据 tools schema 决定是否调用工具、调用哪个。
# 不再需要手写 TOOL:/ARGS: 格式！

SYSTEM_PROMPT = "你是一个智能助手。如果需要搜索信息或进行计算，请使用可用的工具。"


# ==========================================================
# 第四步：工具调用解析（原生 tool_calls，不再手动拆文本）
# ==========================================================
# 当模型需要调工具时，message.tool_calls 会包含结构化的调用信息：
#   tool_calls[0].id               → "call_xxx"（唯一标识）
#   tool_calls[0].function.name    → "search"
#   tool_calls[0].function.arguments → '{"query": "杭州"}'（JSON 字符串，不会解析错）
# 不再需要手写文本解析，不再有解析失败的情况。


# ==========================================================
# 第五步：Agent 主循环（这才是 Agent 的"灵魂"）
# ==========================================================
# 前面的都是铺垫，这里才是 Agent 的核心控制流：
#   思考 → 行动 → 观察 → 再思考 → 再行动 → ... → 完成

async def agent_run(user_input: str, max_steps: int = 5):
    """
    Agent 主循环（原生 Function Calling 版本）

    参数:
        user_input: 用户问题
        max_steps:  最大循环次数，防止无限循环
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ]

    print("="*60)
    print(f"用户: {user_input}")
    print("="*60)

    for step in range(1, max_steps + 1):
        print(f"\n--- 第 {step} 步 ---")

        # 5.1 调用模型（传入 tools schema）
        msg = ask_llm(messages, tools=TOOL_SCHEMAS)

        # 🔍 模型原始输出（JSON 格式），可以看到 tool_calls 的完整结构
        print(f"\n{'='*40}")
        print("📦 模型原始输出 (model_dump_json):")
        print("="*40)
        print(msg.model_dump_json(indent=2, exclude_unset=True))
        print("="*40)

        # 5.2 判断：tool_calls 有值 → 模型要调工具；无值 → 最终回答
        if not msg.tool_calls:
            print(f"模型输出:\n{msg.content}")
            print(f"\n✅ 最终回答: {msg.content}")
            return msg.content

        # 5.3 模型要调工具
        # 先把这条 assistant 消息（含 tool_calls）加入历史
        messages.append(msg.model_dump())  # ChatCompletionMessage → dict

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            print(f"模型输出: 要调用 {tool_name}({args})")

            if tool_name not in TOOL_FUNCTIONS:
                print(f"❌ 未知工具: {tool_name}")
                continue

            # 5.4 执行工具
            print(f"🔧 调用工具: {tool_name}({args})")
            tool_result = TOOL_FUNCTIONS[tool_name](**args)
            print(f"📋 工具结果: {tool_result}")

            # 5.5 把执行结果以 tool 角色消息喂回（注意 role 是 "tool"，不是 "user"）
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })
        # 回到循环开头 → 模型看到工具结果后继续思考

    print("\n⚠️ 达到最大步数限制，Agent 停止")


# ==========================================================
# 第六步：跑起来
# ==========================================================

async def main():
    # 测试 1：单工具调用
    await agent_run("杭州是哪个省的省会？GDP多少？")

    print("\n\n")

    # 测试 2：需要计算
    await agent_run("小明有5个苹果，吃掉2个，又买了8个，现在有几个？")

    # 真实使用前需要：
    # 1. 填入真实的 API key
    # 2. pip install openai
    # 3. python calling.py

if __name__ == "__main__":
    asyncio.run(main())


# ==========================================================
# 附录：下一步可以做什么
# ==========================================================
#
# ✅ 1. 原生 Function Calling —— 已完成（TOOL_SCHEMAS + tool_calls）
#
# 2. 用 LangGraph 替换手写循环 —— 状态图管理更复杂的流程
#    https://langchain-ai.github.io/langgraph/
#
# 3. 加入记忆系统 —— 用 Chroma 存储历史对话，实现长期记忆
#    https://docs.trychroma.com/
#
# 4. 加入 MCP 协议 —— 把工具做成标准化的 MCP Server
#    https://modelcontextprotocol.io/
#
# 5. 包装成 FastAPI 服务 —— 把 Agent 变成 HTTP API
#    https://fastapi.tiangolo.com/
