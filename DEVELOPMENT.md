# LocalModelService — Development Record

This file records the project's development direction. It is historical context, not a
stronger source of truth than the current code, tests, CI, and README.

## 1. Initial product goal

The project started as a practical local AI customer-service service around Ollama:

```text
application
  -> stable HTTP / OpenAI-compatible service
  -> local inference backend
```

The first implementation emphasized model selection, streaming, tools/business modules,
multimodal-capable model configuration, and deployment helpers.

## 2. Why the service boundary mattered

Once several clients and business modules shared the same model service, direct coupling
to Ollama became less useful than a stable application-facing boundary. FastAPI and the
OpenAI-compatible surface provide that replaceable seam; model/provider details remain
behind the service.

The implementation also keeps health checks separate from model generation so liveness
does not require an inference call.

## 3. Security audit correction

The initial release had a more important defect than feature completeness: protected
service surfaces and sessions were not sufficiently tied to an authenticated caller.

The subsequent P0 audit/fix introduced:

- bearer authentication for private API/tool access;
- session ownership partitioning;
- loopback default binding;
- fail-closed checks before public binding;
- deployment/config updates that preserve application authentication;
- regression tests for unauthenticated and cross-owner access.

This is the current security direction. Older feature descriptions should not be read as
evidence that the original release already had these boundaries.

## 4. Verification

CI currently installs the declared dependencies and executes the tests on pushes and pull
requests.

```bash
python -m pip install -e ".[test]"
python -m pytest tests/ -q
```

For current dependency authority, use `pyproject.toml`. The repository retains
`requirements.txt` because existing deployment scripts consume it.

## 5. Current boundary

LocalModelService owns the model-serving/service boundary. Business systems using it
remain responsible for their own domain authorization and side effects. Optional external
modules can call external services; "local model serving" is therefore not a blanket
claim that all configured data paths remain on one machine.
