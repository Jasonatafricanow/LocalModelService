# LocalModelService

[English](README.md) | [简体中文](README.zh-CN.md)

本地 AI 客服盒子原型：制作 Ubuntu 安装 U 盘，首次启动配置 Ollama，再接入带葡萄牙语和英语模板的 WhatsApp 客服模块。

## 从装机到对话

1. [U 盘安装器](bootusb/README.md)：无人值守安装 Ubuntu，尽力配置 GPU，按显存选择模型。
2. FastAPI 服务：带鉴权的本地推理、流式响应和按所有者隔离的会话。
3. [WhatsApp 模块](modules/whatsapp_cs)：意图处理、知识查询、门店服务适配。

安装器会**清空安装策略所选的目标磁盘**，首次启动下载需要联网。使用专用硬件前请先阅读安装指南。目前没有完成所有 GPU 或真实门店部署验证。

## 本地运行

```bash
python -m pip install -e ".[test]"
cp config/agent_llm_config.example.json config/agent_llm_config.json
python src/main.py
```

需要 Python 3.10+ 和 Ollama。对外提供私有接口前需配置 Bearer 鉴权；缺少鉴权时拒绝公开绑定。可选 WhatsApp 和业务适配器可能向外部服务发送数据。

## 接口兼容与验证

```bash
python -m pytest tests/ -q
```

`/v1/chat/completions` 是**部分 OpenAI 风格兼容接口**，完整消息及参数透传、准确 usage 和完整流式元数据仍待实现。原生 `/chat` 和 `/chat/stream` 会话已改为 SQLite 持久化，重启后保留；完整对话轮次原子写入。默认保留 30 天，每会话最多 200 条消息，每个鉴权所有者最多 100 个会话；过期消息在下次读写时清理。可用 `OPENCLAW_MEMORY_DB`、`OPENCLAW_MEMORY_TTL_SECONDS`、`OPENCLAW_MEMORY_MAX_MESSAGES`、`OPENCLAW_MEMORY_MAX_SESSIONS` 调整。默认数据库为安装项目下的 `data/conversations.sqlite3`，服务需有可写的持久路径。更换 API 密钥会改变所有者身份。WhatsApp 模块状态另行管理。见[实现说明](docs/IMPLEMENTATION.md)和[安全加固历史](docs/AUDIT-HISTORY.md)。

安装脚本和服务名中的 `OpenClaw` / `OpenClaw-CS` 是本仓库历史命名，不表示与其他同名项目存在关联。

## 许可

MIT，见 [LICENSE](LICENSE)。
