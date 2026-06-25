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
from openai import OpenAI

# ==========================================================
# 第一步：模型调用（最底层，nothing magic）
# ==========================================================
# Agent 的"大脑"就是一个 API 调用。
# 和你用 Postman 调 /v1/chat/completions 没有区别。

client = OpenAI(
    api_key="your-deepseek-api-key",   # 替换为你的 DeepSeek API key
    base_url="https://api.deepseek.com"
)

def ask_llm(messages: list[dict]) -> str:
    """最朴素的 LLM 调用：发消息，拿回复"""
    response = client.chat.completions.create(
        model="deepseek-v4-pro",          # DeepSeek V4 Pro
        messages=messages,
        temperature=0.2,              # Agent 场景建议低温度，保证稳定性
    )
    return response.choices[0].message.content


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

# 工具注册表：描述 + 函数 一一对应
TOOLS = {
    "search": {
        "function": search,
        "description": "搜索外部信息。参数: query (搜索关键词)"
    },
    "calculate": {
        "function": calculate,
        "description": "执行数学计算。参数: expression (数学表达式, 如 '2+3*4')"
    }
}


# ==========================================================
# 第三步：让模型"知道"它能用什么工具
# ==========================================================
# 这里不用 OpenAI 的 function calling，
# 而是用最原始的方式——把工具说明写在 prompt 里。
# 这样做是为了让你理解本质，后面再换 function calling。

SYSTEM_PROMPT = f"""
你是一个智能助手，你可以使用以下工具：

1. search(query) - {TOOLS['search']['description']}
2. calculate(expression) - {TOOLS['calculate']['description']}

当你需要调用工具时，必须严格用以下格式回复：
TOOL: <工具名>
ARGS: <JSON格式参数>

当你得到最终答案时，直接回复用户，不要用 TOOL 格式。

示例：
  用户: 杭州在哪里？
  你:    TOOL: search
         ARGS: {{"query": "杭州"}}

  用户: 3+5等于几？
  你:    TOOL: calculate
         ARGS: {{"expression": "3+5"}}
"""


# ==========================================================
# 第四步：解析模型的输出（它到底想调用工具还是直接回答？）
# ==========================================================

def parse_llm_response(response: str) -> dict:
    """
    解析模型输出，判断它是：
    - "tool_call": 需要调用工具（包含工具名和参数）
    - "final":    最终回答
    """
    if "TOOL:" in response:
        # 简陋但直观的解析：找到 TOOL 和 ARGS
        lines = response.strip().split("\n")
        tool_name = None
        args_str = None
        for line in lines:
            if line.startswith("TOOL:"):
                tool_name = line.replace("TOOL:", "").strip()
            elif line.startswith("ARGS:"):
                args_str = line.replace("ARGS:", "").strip()
        if tool_name and args_str:
            try:
                return {
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": json.loads(args_str)
                }
            except json.JSONDecodeError:
                pass
    return {"type": "final", "content": response}


# ==========================================================
# 第五步：Agent 主循环（这才是 Agent 的"灵魂"）
# ==========================================================
# 前面的都是铺垫，这里才是 Agent 的核心控制流：
#   思考 → 行动 → 观察 → 再思考 → 再行动 → ... → 完成

async def agent_run(user_input: str, max_steps: int = 5):
    """
    Agent 主循环

    参数:
        user_input: 用户问题
        max_steps:  最大循环次数，防止无限循环（安全兜底）
    """
    # 初始化对话历史
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input}
    ]

    print("="*60)
    print(f"用户: {user_input}")
    print("="*60)

    for step in range(1, max_steps + 1):
        print(f"\n--- 第 {step} 步 ---")

        # 5.1 获取模型输出
        response = ask_llm(messages)
        print(f"模型输出:\n{response}")

        # 5.2 解析输出：是要调工具还是最终回答？
        parsed = parse_llm_response(response)

        if parsed["type"] == "final":
            # 没有 TOOL 标记 → 这就是最终答案
            print(f"\n✅ 最终回答: {parsed['content']}")
            return parsed["content"]

        if parsed["type"] == "tool_call":
            tool_name = parsed["tool"]
            args = parsed["args"]

            if tool_name not in TOOLS:
                print(f"❌ 未知工具: {tool_name}")
                break

            # 5.3 执行工具
            print(f"🔧 调用工具: {tool_name}({args})")
            tool_result = TOOLS[tool_name]["function"](**args)
            print(f"📋 工具结果: {tool_result}")

            # 5.4 把"我调了工具，结果是..."作为新消息喂回模型
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": f"工具执行结果: {tool_result}\n\n请根据这个结果继续回答用户的问题。"
            })
            # 回到循环开头 → 模型看到结果后继续思考

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
# 1. 换成 OpenAI Function Calling —— 把 TOOL 文本解析换成原生 tool_call
#    https://platform.openai.com/docs/guides/function-calling
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
