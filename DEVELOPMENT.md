# OpenClaw-CS · 架构设计与研发演进历程

本文档记录 OpenClaw-CS（LocalModelService）的技术选型、架构演进历程、工程规范与测试基线。

---

## 1. 技术选型与设计原则

### 1.1 核心技术栈
* **服务层**：FastAPI + Uvicorn（异步高并发、原生 OpenAPI 文档规范、轻量依赖）。
* **Agent 运行时**：LangChain / LangGraph + Ollama API。
* **模型生态**：
  * 对话推理：Qwen2.5 (3B / 7B / 14B) 或 Llama 3 系列。
  * 图像与多模态：Qwen2.5-VL / MiniCPM-V。
* **业务模块**：插件化（通过 `modules/` 目录实现动态反射加载）。

### 1.2 设计原则
1. **模块隔离与绝对导入**：全部内部模块统一采用 `src.` 绝对命名空间导入，消除根目录与包内双重导入引起的单例状态不一致。
2. **零硬件强绑定**：提供 CPU 降级、紧显存（<16GB 换出策略）与高性能 GPU 动态自适应。
3. **健康检查无推理开销**：`/health` 仅探测 Ollama `/api/tags` 端口可达性与模型清单，避免健康探针频繁触发模型前向推理。
4. **协议兼容性**：优先保障标准 `/v1/chat/completions` 与主流前端 UI 及客户端的兼容。

---

## 2. 研发演进与里程碑

### 2.1 初始阶段：原型构建与核心服务搭建
* 搭建基于 FastAPI 的 OpenAI 兼容接口骨架与基础 Agent 执行器。
* 完成与 Ollama 本地接口（`/api/chat`、`/api/tags`）的基础通讯打通。
* 编写跨平台安装与引导脚本 `install.sh` 与 `install.py`。

### 2.2 演进阶段：服务加固与逻辑优化
* **安装链与自动化配置**：
  * 支持命令行 `--port` 与模型参数贯通。
  * 支持 `--non-interactive` 无人值守自动化部署。
  * 增加 GPU 显存自动探测（根据显存容量智能推荐 3B / 7B / 14B 模型）。
* **核心路由与状态治理**：
  * 彻底修复路由注册顺序，规范 friendly 404 捕获与异常返回。
  * 修复历史会话截断与上下文长度（`num_ctx`）动态传递。
* **多模态与客服模块接入**：
  * 新增 WhatsApp 客服适配层（`modules/whatsapp_cs`），规范图片 Base64 编码传递与流式答复。
  * 引入 RAG 知识库隔离检索，避免不相关元数据污染上下文。

### 2.3 当前阶段：系统基线冻结与稳定性验收
* 完成全面单测与回归验证，保持 137 项测试通过。
* 服务具备自愈与状态降级能力（在 Ollama 未启动时正确返回 degraded 状态）。

---

## 3. 测试与验证基线

运行完整单元测试集：

```bash
# 执行单元测试
pytest -v

# 仅执行核心路由与服务测试
pytest tests/test_server.py tests/test_routes.py
```

### 已验证特性清单
- [x] `/health` 与 `/models` 在 Ollama 正常与降级状态下的响应
- [x] `/chat` 与 `/chat/stream` 的完整对话与 SSE 流式返回
- [x] `/v1/chat/completions` 流式与非流式调用兼容
- [x] 模块动态挂载与 Tools Registry 动态调用
- [x] 安装脚本配置读写与参数解析
