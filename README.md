# OpenClaw-CS / LocalModelService

LocalModelService is a FastAPI service for running local models through Ollama and exposing them to other applications through a stable HTTP interface.

It started as a local AI customer-service backend and later became a reusable service layer.

## Request path

```text
web app / agent / business service
        |
        v
HTTP / SSE / OpenAI-compatible API
        |
        v
FastAPI service
   |        |        |
   v        v        v
Ollama    tools   business adapters
```

## Current implementation

The repository includes:

- FastAPI service endpoints;
- normal and SSE streaming chat;
- OpenAI-compatible `/v1/chat/completions`;
- OpenAI-compatible `/v1/models`;
- Ollama model discovery/invocation;
- configurable text and vision models;
- tool registration;
- optional business integrations;
- deployment helpers.

## Main interfaces

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | service/Ollama health |
| GET | `/models` | available local models |
| POST | `/chat` | native chat |
| POST | `/chat/stream` | SSE chat |
| POST | `/v1/chat/completions` | OpenAI-compatible chat |
| GET | `/tools` | loaded tools |

## Configuration

Model names, endpoint, context size, temperature, and text/vision selection are configuration rather than client-side constants.

Business integrations and tools are optional modules. The inference service can run without embedding customer-service-specific behavior into the core request path.

## Quick start

Requirements: Python 3.10+ and Ollama.

```bash
git clone https://github.com/Jasonatafricanow/LocalModelService.git
cd LocalModelService
pip install -r requirements.txt
cp config/agent_llm_config.example.json config/agent_llm_config.json
python src/main.py
```

## Scope

The service is not a distributed inference scheduler, CRM, or benchmark suite. Its job is to provide one replaceable local-model API surface for applications that should not depend directly on Ollama internals.

## Stack

Python · FastAPI · LangChain / LangGraph · Ollama · Pydantic · SSE

## Repository history

This public repository is a cleaned publication of an earlier local project. Its public baseline commit is not the original development date.
