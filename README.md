# LocalModelService

[English](README.md) | [简体中文](README.zh-CN.md)

A local AI customer-service appliance prototype: prepare an Ubuntu installer USB, provision Ollama on first boot, then connect a WhatsApp support module with Portuguese and English templates.

## From installation to a conversation

1. [USB installer](bootusb/README.md): unattended Ubuntu installation, best-effort GPU setup and model selection by available VRAM.
2. FastAPI service: authenticated local inference, streaming and owner-partitioned sessions.
3. [WhatsApp module](modules/whatsapp_cs): intent handling, knowledge lookup and store-service adapters.

The installer **erases the target disk selected by its installation policy** and needs network access for first-boot downloads. Review the installer guide before using dedicated hardware. The appliance workflow has not been validated on every GPU or a real store deployment.

## Run locally

```bash
python -m pip install -e ".[test]"
cp config/agent_llm_config.example.json config/agent_llm_config.json
python src/main.py
```

Requires Python 3.10+ and Ollama. Configure bearer authentication before exposing private routes. Public binding fails closed without it; optional WhatsApp/business adapters can send data to external services.

## API compatibility and verification

```bash
python -m pytest tests/ -q
```

`/v1/chat/completions` forwards messages (including system/tool messages), model, tools and generation options to Ollama’s [OpenAI-compatible chat endpoint](https://docs.ollama.com/api/openai-compatibility). It preserves upstream usage, streaming metadata, finish reasons and error responses. Compatibility is bounded by the installed Ollama version and model; this is not a complete implementation of every OpenAI endpoint. This route is stateless and does not execute local agent tools. Native `/chat` and `/chat/stream` sessions persist in SQLite across restarts. Completed turns are saved atomically; default retention is 30 days, 200 messages per session and 100 sessions per authenticated owner. Set `OPENCLAW_MEMORY_DB`, `OPENCLAW_MEMORY_TTL_SECONDS`, `OPENCLAW_MEMORY_MAX_MESSAGES` or `OPENCLAW_MEMORY_MAX_SESSIONS` to override these limits. Expired messages are removed on the next read/write. The default database is `data/conversations.sqlite3` under the installed project; give the service a writable persistent path. API-key rotation changes the owner identity. WhatsApp module state is separate. See [implementation details](docs/IMPLEMENTATION.md) and [security hardening history](docs/AUDIT-HISTORY.md).

Native and compatible chat share a bounded process-local inference queue: one running request, up to eight waiting, and a 30-second queue timeout by default. Saturation/timeouts return 503 with `Retry-After`. Configure `OPENCLAW_INFERENCE_CONCURRENCY`, `OPENCLAW_INFERENCE_MAX_WAITING` and `OPENCLAW_INFERENCE_WAIT_SECONDS`; use one server worker for a single shared queue. Streaming retains its slot until completion or cancellation. Protocol tests use a simulated upstream, not hardware benchmarks.

Some existing installer/service names contain `OpenClaw` or `OpenClaw-CS`; they are historical names within this repository, not a statement of affiliation with another project.

## License

MIT — see [LICENSE](LICENSE).
