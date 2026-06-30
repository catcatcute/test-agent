# Agent 开发知识点汇总（已掌握）

> 基于 `calling.py` 实现的 ReAct Agent 原型，系统性总结已涉及的 Agent 开发知识点。

---

## 1. Agent 是什么？

```
┌──────────────────────────────────────────────────┐
│                   Agent 核心循环                   │
│                                                   │
│   用户输入 → 模型推理 → 要调工具？                  │
│                   │                               │
│           ┌───────┴───────┐                       │
│           │ 是             │ 否                    │
│           ▼               ▼                       │
│   执行工具 → 结果喂回    输出最终答案               │
│      ↑                    │                       │
│      └──── 循环 ←─────────┘                       │
└──────────────────────────────────────────────────┘
```

**一句话**：Agent 就是一个「带工具调用的自动循环」，模型决定每一步做什么、你的代码执行它、结果再喂回去，直到模型觉得可以停为止。

---

## 2. Chat Completion API（LLM 调用层）

### 2.1 调用方式

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-xxx",                # 身份认证
    base_url="https://api.deepseek.com"  # API 地址
)

response = client.chat.completions.create(
    model="deepseek-v4-pro",         # 模型名称
    messages=[...],                  # 对话历史
    temperature=0.2,                 # 随机性（0=稳定, 1=创意）
)
```

### 2.2 messages 结构（消息角色）

| role | 含义 | 何时使用 |
|------|------|---------|
| `system` | 系统指令 | 设定 Agent 的角色和行为边界 |
| `user` | 用户输入 | 用户的问题或指令 |
| `assistant` | 模型回复 | 模型输出的文本（或 tool_calls） |
| `tool` | 工具执行结果 | 工具执行完的结果回传 |

### 2.3 response 完整结构

模型返回的 HTTP JSON 长这样：

```json
{
  "id": "chatcmpl-xxx",
  "choices": [{
    "index": 0,
    "finish_reason": "stop",        // "stop"=正常结束 "tool_calls"=要调工具
    "message": {                     // ← ask_llm() 返回的就是这个
      "role": "assistant",
      "content": "文本回答...",       // 调工具时为 null
      "tool_calls": [...]            // 不调工具时这个字段不存在
    }
  }]
}
```

**关键理解**：`content`、`role`、`tool_calls` 这些字段名不是你定义的，是 **OpenAI Chat Completion API 协议**规定的。DeepSeek 因为实现了 OpenAI 兼容接口，所以返回格式一模一样。

### 2.4 message 对象 vs dict

| 对象（SDK解析后） | 字典（原始JSON） | 串行协议 |
|-------------------|------------------|---------|
| `msg.content` | `{"content": "..."}` | |
| `msg.tool_calls` | `{"tool_calls": [...]}` | |
| `msg.model_dump()` | 整个 message 转 dict | **把这个 dict 放回 messages 列表** |
| `msg.model_dump_json(exclude_unset=True)` | JSON 字符串 | 调试用，查看原始输出 |

---

## 3. Function Calling（工具调用机制）

### 3.1 工具的完整生命周期

```
① 定义 Schema            ② 传给模型            ③ 模型返回 tool_calls
TOOL_SCHEMAS (JSON)  →   tools=TOOL_SCHEMAS  →   msg.tool_calls = [{
                        (在 create() 调用时)        id: "call_xxx",
                                                   function: {
                                                     name: "search",
                                                     arguments: '{"query":"杭州"}'
                                                   }
                                                 }]

④ 你的代码执行工具        ⑤ 结果回传
search(query="杭州")  →   messages.append({
                            role: "tool",
                            tool_call_id: "call_xxx",
                            content: "查询结果"
                          })

⑥ 回到 ②，模型看到工具结果后继续推理或输出答案
```

### 3.2 TOOL_SCHEMAS（输入方向：你告诉模型有哪些工具）

```python
TOOL_SCHEMAS = [
    {
        "type": "function",              # 固定写法
        "function": {
            "name": "search",            # 工具名称（= 要调用的函数名）
            "description": "搜索外部信息", # 模型据此判断何时用这个工具
            "parameters": {              # JSON Schema 格式的参数定义
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]    # 必填参数
            }
        }
    }
]
```

### 3.3 tool_calls（输出方向：模型告诉你它想调用哪个工具）

```python
# msg.tool_calls 是一个列表，每个元素包含：
tool_call.id               # "call_abc123" — 唯一标识，回传时用于配对
tool_call.type             # "function" — 固定值
tool_call.function.name    # "search" — 工具名
tool_call.function.arguments  # '{"query":"杭州"}' — JSON 字符串，需 json.loads()
```

### 3.4 两种 Function Calling 方式对比

| | 文本解析方式（旧） | 原生 Function Calling（新） |
|---|---|---|
| 工具描述位置 | 写在 System Prompt 里 | `TOOL_SCHEMAS` JSON 通过 `tools` 参数传入 |
| 模型返回格式 | 自由文本 `TOOL: search\nARGS: {"query":"杭州"}` | 结构化 `tool_calls[].function.name/arguments` |
| JSON 解析 | 可能失败（格式不对） | 模型保证输出合法 JSON |
| 标准程度 | 自己约定的格式 | OpenAI 定义的 API 标准 |
| 多工具并行 | 需要自己定义分隔符 | 原生支持，一个列表里多个 tool_call |

---

## 4. ReAct 模式（Agent 的核心控制流）

### 4.1 概念

ReAct = **Re**asoning + **Act**ing，即推理和行动交替进行。

```
第1步：模型看到问题 → 推理 → "我需要搜索"

第2步：你的代码执行 search → 拿到结果 → 喂回给模型

第3步：模型看到搜索结果 → 推理 → "我已知答案，不需要再调工具"

第4步：输出最终答案 → Agent 停止
```

### 4.2 代码实现要点

```python
for step in range(1, max_steps + 1):  # max_steps 防止死循环

    msg = ask_llm(messages, tools=TOOL_SCHEMAS)

    if not msg.tool_calls:            # 模型不调工具 → 最终答案
        return msg.content

    # 把 assistant 消息加入历史（含 tool_calls）
    messages.append(msg.model_dump())

    for tool_call in msg.tool_calls:  # 遍历每个工具调用
        result = execute_tool(tool_call)
        # 把工具结果以 role="tool" 回传
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })
    # 循环回去，模型看到结果继续推理
```

### 4.3 关键设计点

| 设计点 | 做法 | 原因 |
|--------|------|------|
| **max_steps** | 限制循环次数（如 5） | 防止模型陷入无限调用 |
| **temperature** | 设为较低值（0.2） | Agent 场景需要稳定输出，不要创意 |
| **消息序列** | 严格按 system → user → assistant → tool → assistant → ... | 协议要求，顺序乱了模型会困惑 |
| **msg.model_dump()** | 把 SDK 对象转 dict 再放回 messages | SDK 对象不能直接放到列表里 |

### 4.4 messages 的生命周期示例

```
初始:
  [{role: "system", content: "你是助手"},
   {role: "user", content: "杭州在哪里？"}]

第1步 模型回复 tool_calls:
  [{role: "system", ...},
   {role: "user", ...},
   {role: "assistant", content: null, tool_calls: [{...}]}]  ← msg.model_dump()

第1步 工具执行:
  [{role: "system", ...},
   {role: "user", ...},
   {role: "assistant", content: null, tool_calls: [...]},
   {role: "tool", tool_call_id: "call_xxx", content: "杭州是浙江..."}]

第2步 模型看到结果，直接回答:
  模型输出 content = "杭州是浙江省的省会..." → tool_calls 数组为空 → 停止
```

---

## 5. API 兼容性（OpenAI 生态）

### 5.1 DeepSeek 如何兼容 OpenAI

DeepSeek 实现了和 OpenAI 完全一致的 HTTP API 接口：

```
OpenAI:  https://api.openai.com/v1/chat/completions
DeepSeek: https://api.deepseek.com/v1/chat/completions    ← SDK 自动拼接 /v1/...

POST 请求体、响应体、tool_calls 结构 → 完全一样
```

切换只需改两行：
```python
client = OpenAI(
    base_url="https://api.deepseek.com",  # ← 改这里
)
# model="deepseek-v4-pro"                 # ← 改这里
```

### 5.2 其他兼容 OpenAI 接口的服务商

同样的模式适用于：智谱（GLM）、月之暗面（Moonshot）、Ollama（本地）、vLLM（自部署）、通义千问、百度文心等。

---

## 6. 知识图谱总结

```
Agent 开发已掌握的知识点
│
├── LLM 调用层
│   ├── OpenAI Python SDK 用法
│   ├── Chat Completion API（POST /v1/chat/completions）
│   ├── messages 结构（system/user/assistant/tool 四种 role）
│   ├── 响应结构（choices[0].message → content / tool_calls）
│   └── temperature 参数含义
│
├── Function Calling（工具调用）
│   ├── TOOL_SCHEMAS（JSON Schema 定义工具）
│   │   ├── type: "function"
│   │   ├── function.name / description
│   │   └── parameters（properties + required）
│   ├── tools 参数传入方式
│   ├── tool_calls 响应解析
│   │   ├── id / function.name / function.arguments
│   │   └── arguments 是 JSON 字符串，需 json.loads()
│   ├── tool 角色消息回传（role: "tool" + tool_call_id）
│   └── 文本解析 vs 原生 function calling 对比
│
├── ReAct 控制流
│   ├── 思考 → 行动 → 观察 → 再思考 循环
│   ├── for 循环实现
│   ├── max_steps 安全兜底
│   ├── messages 列表的增删管理
│   └── msg.model_dump() 序列化
│
├── 工程基础
│   ├── Python AsyncIO（asyncio.run）
│   ├── Optional 类型注解（Python 3.9 兼容）
│   ├── json.loads() 解析
│   ├── eval 安全用法（{"__builtins__": {}}）
│   └── 服务商 API 切换（base_url + model）
│
└── 还未涉及（下一步）
    ├── LangGraph（将手写循环改为状态图管理）
    ├── 记忆系统（Chroma 向量数据库）
    ├── RAG（检索增强生成）
    ├── MCP 协议（标准化工具接口）
    ├── FastAPI 服务化部署
    └── 多 Agent 协作
```

---

## 7. 对应该文件

| 文件 | 内容 |
|------|------|
| [calling.py](calling.py) | 本文档所有知识点的可运行代码实现 |
| [agent-developer-guide.md](agent-developer-guide.md) | 岗位分析 + 四周学习计划 |
| [work.md](work.md) | 原始需求说明 |
