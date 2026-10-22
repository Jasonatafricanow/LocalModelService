# LocalModelService

LocalModelService is a local-first FastAPI service around Ollama. It exposes an
partially OpenAI-compatible model boundary plus native chat/tool endpoints so applications do not
need to couple directly to a specific local model process.

The current repository is best read as an infrastructure project, not as a claim of a
finished omnichannel customer-service platform.

The compatibility limits and in-memory session lifecycle are listed in the [current entry guide](../README.md#api-compatibility-and-verification).

## What is implemented

```text
client / business adapter
        |
        v
authenticated FastAPI surface
        |
        +--> partially OpenAI-compatible chat / streaming
        +--> native chat / tools
        |
        v
session ownership + agent/tool layer
        |
        v
Ollama
```

Current code includes:

- `/v1/chat/completions` and model discovery compatibility surfaces;
- native chat and SSE streaming paths;
- Ollama-backed text/model integration with configurable model selection;
- modular tools/business adapters under `modules/`;
- local configuration and deployment helpers;
- authenticated private API/tool surfaces and owner-partitioned sessions.

## Verification

GitHub Actions installs the declared dependencies and runs the repository test suite on
pushes and pull requests.

Local verification:

```bash
python -m pip install -e ".[test]"
python -m pytest tests/ -q
```

The package manifest is `pyproject.toml`; `requirements.txt` is kept for the existing
deployment scripts.

## Run locally

Requirements:

- Python 3.10+
- Ollama

Install and start:

```bash
python -m pip install -e .
cp config/agent_llm_config.example.json config/agent_llm_config.json
python src/main.py
```

The checked-in example/default configuration is intended for local binding. Review the
authentication and deployment settings before exposing the service beyond loopback.

The repository also contains `install.sh` / `install.py` for the existing deployment
workflow.

## Main surfaces

| Surface | Purpose |
| --- | --- |
| `GET /health` | service/Ollama health |
| `GET /models` | available local models |
| `POST /chat` | native chat |
| `POST /chat/stream` | native SSE chat |
| `POST /v1/chat/completions` | partially OpenAI-compatible chat |
| `GET /tools` | registered tools |
| `POST /tools/{name}/invoke` | explicit tool invocation |

## Repository layout

```text
src/          service/API/agent implementation
modules/      optional business/tool modules
config/       example and runtime configuration
deploy/       deployment helpers
tests/        regression and service tests
tools/        supporting utilities
```

See [DEVELOPMENT.md](../DEVELOPMENT.md) for the development history and the distinction
between the initial feature-oriented prototype and the later security hardening.

## Stack

Python 3.10+ · FastAPI · Uvicorn · LangChain/LangGraph · Ollama · pytest

## License

MIT — see [LICENSE](../LICENSE).
