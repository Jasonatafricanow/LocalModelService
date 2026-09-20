# OpenClaw-CS (LocalModelService)

> 基于 Ollama 本地大模型的轻量级私有化 AI 智能客服服务。轻量、模块化、高安全性、一键部署。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/Framework-FastAPI-teal.svg)](https://fastapi.tiangolo.com/)

---

## 📖 项目简介

**OpenClaw-CS** 专为企业与个人业务打造的本地化 AI 客服中台。它直接连接本地 Ollama 推理引擎，支持多种主流开源大模型（如 Qwen2.5、Llama 3 系列及多模态视觉模型），实现零数据外流、低推理延迟、高隐私安全的全天候智能问答与业务办理。

### 核心亮点

* 🔒 **数据零外流**：模型与知识库均运行在本地/私有服务器，客户对话与业务数据不出内网。
* ⚡ **OpenAI 兼容**：原生兼容 `/v1/chat/completions` 与 `/v1/models`，可无缝对接任何支持 OpenAI 格式的前端或工作流工具。
* 💬 **全渠道适配**：支持 Web 网页对话、流式输出（SSE），并内置企业级 WhatsApp 客服模块。
* 👁️ **多模态视觉支持**：支持图像输入与理解，方便客户上传商品截图、故障照片并进行智能解答。
* 🧩 **模块化工具箱**：内置时间工具、系统工具，支持在 `modules/` 目录下热插拔自定义 Python 业务工具与 RAG 知识库。
* 🚀 **一键自动化部署**：提供完善的交互式及无人值守安装脚本，自动安装依赖、拉取模型并配置服务。

---

## 🏗️ 系统架构

```
                   +--------------------------------+
                   |       用户端 (Web / App)        |
                   |   或 WhatsApp / 第三方系统     |
                   +---------------+----------------+
                                   |
                         HTTP / RESTful / SSE
                                   v
             +---------------------------------------------+
             |         OpenClaw-CS (FastAPI Server)        |
             |                                             |
             |   +-------------------+  +---------------+  |
             |   | OpenAI 兼容路由   |  | 原生业务路由   |  |
             |   | /v1/*             |  | /chat, /tools |  |
             |   +---------+---------+  +-------+-------+  |
             |             |                    |          |
             |             v                    v          |
             |      +-------------------------------+      |
             |      |       Agent 核心调度层        |      |
             |      |   (LangChain / LangGraph)     |      |
             |      +---------------+---------------+      |
             |                      |                      |
             +----------------------|----------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+-----------------------+                       +-----------------------+
|    Tools Registry     |                       |    本地推理引擎       |
| ├── builtin/ 内置工具 |                       |    (Ollama Server)    |
| └── modules/ 业务模块 |                       |  ├── Qwen2.5 (语言)   |
|     ├── WhatsApp 客服 |                       |  └── Qwen-VL (视觉)   |
|     └── RAG 知识库    |                       +-----------------------+
+-----------------------+
```

---

## 🚀 快速开始

### 前置要求

* **操作系统**：Linux / macOS / Windows
* **Python**：>= 3.10
* **Ollama**：安装脚本可自动安装，亦可自行提前安装并启动

### 方式一：一键自动部署（推荐）

```bash
# 默认使用 qwen2.5 模型与默认端口
bash install.sh

# 或指定模型与端口启动
bash install.sh llama3.2 8080
```

安装脚本会自动检测硬件环境（CPU / GPU 显存）、安装 Python 依赖、配置 Ollama 模型并创建运行时配置文件。

### 方式二：手动运行

1. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **配置服务**：
   复制配置模板并调整：
   ```bash
   cp config/agent_llm_config.example.json config/agent_llm_config.json
   ```

3. **启动服务**：
   ```bash
   python src/main.py
   # 服务将默认监听 http://0.0.0.0:5000
   ```

---

## 📡 API 接口参考

| 请求方式 | 路径 | 功能说明 |
| :--- | :--- | :--- |
| `GET` | `/health` | 服务健康检查与 Ollama 状态探测 |
| `GET` | `/models` | 查询本地 Ollama 可用模型列表 |
| `POST` | `/chat` | 标准对话接口（JSON 响应） |
| `POST` | `/chat/stream` | 流式对话接口（Server-Sent Events） |
| `POST` | `/v1/chat/completions` | **OpenAI 兼容** 对话接口（支持流式与普通模式） |
| `GET` | `/tools` | 查看已加载的工具与模块列表 |
| `POST` | `/tools/{name}/invoke` | 显式调用特定工具模块 |

---

## ⚙️ 配置说明

核心配置文件路径：`config/agent_llm_config.json`

```json
{
    "llm": {
        "provider": "ollama",
        "model": "qwen2.5",
        "vision_model": "qwen2.5-vl",
        "base_url": "http://localhost:11434",
        "temperature": 0.7,
        "num_ctx": 4096,
        "keep_alive": -1
    },
    "agent": {
        "system_prompt": "你是一个专业的智能客服助手，负责解答用户咨询...",
        "max_history": 40,
        "enable_tools": true
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5000
    },
    "business": {
        "enabled": false,
        "base_url": "https://api.yourstore.com",
        "timeout": 8,
        "auth": { "scheme": "bearer", "token_env": "STORE_API_TOKEN" }
    }
}
```

---

## 🧩 自定义业务扩展

在 `modules/` 目录下新增 Python 脚本，即可实现免编译热加载自定义业务逻辑或工具。详情请参阅 [modules/README.md](modules/README.md)。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 授权。
