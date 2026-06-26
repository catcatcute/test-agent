# AI Agent Learning Project

从后端工程师（Go/Node.js）向 AI Agent 开发岗位转型的学习项目。

## 项目结构

```
├── work.md                     # 项目需求与学习目标
├── agent-developer-guide.md    # Agent 岗位分析 + 四周学习计划 + 资源汇总
├── calling.py                  # 从零构建的 ReAct Agent 最小原型（DeepSeek 驱动）
└── README.md                   # 本文件
```

## 快速开始

```bash
# 1. 安装依赖
pip3 install openai

# 2. 填入 DeepSeek API Key（编辑 calling.py 第 26 行）
#    api_key="sk-xxxx"

# 3. 运行
python calling.py
```

## 当前进度

- [x] 理解 Agent 核心概念与岗位要求
- [x] 手写 ReAct Agent 主循环（思考 → 工具调用 → 观察 → 再思考）
- [x] 接入 DeepSeek V4 Pro 模型
- [ ] 替换为 OpenAI 原生 Function Calling
- [ ] 接入 LangGraph 管理控制流
- [ ] 集成 RAG 记忆系统
- [ ] 接入 MCP 协议
- [ ] FastAPI 部署上线

## 参考资料

- [DeepSeek API 文档](https://platform.deepseek.com/api-docs)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
