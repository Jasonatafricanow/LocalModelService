# OpenClaw-CS / LocalModelService

**A lightweight local model service for private AI applications.**

This project began from a concrete product need: run an AI customer-service layer on local infrastructure, keep the application independent from a specific UI, and expose a stable API that other business systems could consume.

It is one of the earliest project lines in this portfolio and later became a useful reference point for a broader principle:

> Model deployment should be replaceable infrastructure, not the place where business logic becomes trapped.

## Portfolio role

```text
Business application / Agent / UI
              |
              v
       LocalModelService
        /      |       \
       v       v        v
    Ollama   Tools   Business adapters
```

LocalModelService is the single-host/local-inference side of the infrastructure layer. [AutoRoute Gateway](https://github.com/Jasonatafricanow/AutoRoute-Gateway) addresses a later problem: routing across multiple upstreams and credentials.

## The problem

A local customer-service prototype quickly stops being "just call Ollama" once it needs:

- a stable API for several clients;
- streaming;
- text and vision models;
- business tools;
- configurable model replacement;
- deployment that does not require every client to know Ollama internals.

The useful abstraction is therefore a service boundary around inference, not another chat UI.

## How the design evolved

### 1. From a customer-service prototype to a reusable service

The original goal was local AI customer support. As the surrounding system grew, model invocation, tools, and business integration became separate concerns.

The service was reorganized so the model backend could change without rewriting every client.

### 2. Compatibility became more valuable than a custom protocol

Instead of forcing consumers onto project-specific request formats, the service exposes OpenAI-compatible model and chat-completion endpoints alongside its native routes.

That makes local models usable by existing agent frameworks and tools with minimal glue.

### 3. Business functions remain optional modules

Customer-service actions, RAG, or other business integrations belong behind explicit modules/adapters. They should not become hard dependencies of the inference service itself.

## Key design decisions

### Local-first by default

The primary backend is Ollama. Model weights and ordinary inference can remain on infrastructure controlled by the operator.

This is an architectural default, not a claim that every optional module or external integration keeps all data local.

### OpenAI-compatible boundary

Clients integrate against a common protocol rather than Ollama-specific details.

### Tools are extensions, not the core

Built-in and business-specific tools are loaded through a registry/module boundary so inference serving remains understandable without them.

### Model choice is configuration

Language and vision model names, context size, temperature, and endpoint are configuration rather than application constants.

### Business APIs are adapters

External store or service calls are optional and explicitly configured.

## Architecture

```text
Web / App / Agent / Business system
              |
        HTTP / SSE / OpenAI API
              |
              v
      FastAPI service boundary
        /          |          \
       v           v           v
 Agent dispatch  Tool registry  Business adapter
       |
       v
     Ollama
  text / vision models
```

## Current scope

The repository provides:

- FastAPI service endpoints;
- normal and SSE streaming chat;
- OpenAI-compatible `/v1/chat/completions` and `/v1/models`;
- local Ollama model discovery and invocation;
- text / vision model configuration;
- tool registration;
- optional business modules;
- deployment helpers.

## Boundaries and non-claims

LocalModelService is not:

- a complete CRM or ticketing platform;
- a distributed inference scheduler;
- a guarantee that every extension is private or offline;
- a benchmark claim about local-model quality.

Its role is to provide a small, replaceable inference/service boundary.

## Quick start

Requirements: Python 3.10+ and Ollama.

```bash
git clone https://github.com/Jasonatafricanow/LocalModelService.git
cd LocalModelService
pip install -r requirements.txt
cp config/agent_llm_config.example.json config/agent_llm_config.json
python src/main.py
```

Main interfaces:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | service and Ollama health |
| GET | `/models` | available local models |
| POST | `/chat` | native chat |
| POST | `/chat/stream` | SSE chat |
| POST | `/v1/chat/completions` | OpenAI-compatible chat |
| GET | `/tools` | loaded tools |

## Stack

Python · FastAPI · LangChain / LangGraph · Ollama · Pydantic · SSE

## Repository history

This public repository is a cleaned publication of an earlier local project. Its single public baseline commit is the publication point, not the original development date or full development history.

## Engineering philosophy

Keep the model layer replaceable.

Applications should be able to change models, inference hosts, or tool modules without reconstructing their entire business flow around one provider.
