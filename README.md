# LocalModelService / OpenClaw-CS

LocalModelService is a local-first FastAPI service around Ollama. It exposes an
OpenAI-compatible model boundary plus native chat/tool endpoints so applications do not
need to couple directly to a specific local model process.

The current repository is best read as an infrastructure project, not as a claim of a
finished omnichannel customer-service platform.

## What is implemented

```text
client / business adapter
        |
        v
authenticated FastAPI surface
        |
        +--> OpenAI-compatible chat / streaming
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

## Security boundary

A later audit found that the original service exposed private API/tool surfaces without a
sufficient application authentication boundary and did not bind sessions strongly enough
to an authenticated owner.

The repair changed the service boundary rather than only adding endpoint checks:

- bearer authentication is required for protected API/tool access;
- sessions are partitioned by authenticated owner;
- the default server bind is loopback;
- public binding fails closed unless application authentication is configured;
- deployment helpers preserve the application authentication requirement;
- regressions cover missing auth, cross-owner session access, and public-bind behavior.

The relevant audit/fix history is visible in
`fix: close public API and session ownership P0 (#2)`.

Local inference can keep model requests on the Ollama host. That does **not** mean every
optional adapter is offline: external business/WhatsApp integrations may transmit data to
their configured services.

## Bounded completeness

LocalModelService is deliberately a service boundary around local inference, not a second
model platform.

It owns:

- the application-facing HTTP/OpenAI-compatible surface;
- local Ollama invocation and streaming adaptation;
- authenticated access to private API/tool surfaces;
- owner-partitioned sessions;
- module/tool registration seams;
- safe local/public binding behavior.

It does not own distributed scheduling, model training, fleet management, business-domain
authorization inside downstream applications, or a universal plugin sandbox. Keeping those
responsibilities outside this repository is part of the boundary: applications can replace
the inference backend without giving the model service authority over their business state.

Completeness here should be checked against the declared service/security contracts and
their regressions rather than repository size or the number of infrastructure layers.

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
| `POST /v1/chat/completions` | OpenAI-compatible chat |
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

See [DEVELOPMENT.md](DEVELOPMENT.md) for the development history and the distinction
between the initial feature-oriented prototype and the later security hardening.

## Scope / non-claims

This repository does not demonstrate:

- production-scale multi-tenant operation;
- a general distributed inference scheduler;
- universal isolation for arbitrary third-party modules;
- that optional external adapters keep data local;
- production reliability across every Ollama model/hardware combination.

It demonstrates a bounded local model service and the audit/rework needed to make its
network and session boundaries explicit.

## Stack

Python 3.10+ · FastAPI · Uvicorn · LangChain/LangGraph · Ollama · pytest

## License

MIT — see [LICENSE](LICENSE).
