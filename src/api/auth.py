"""Authentication for the OpenClaw HTTP API.

Public endpoints are intentionally limited to service metadata/health. Private
chat/session endpoints use OPENCLAW_API_KEY. Tool enumeration/invocation uses a
separate OPENCLAW_TOOLS_API_KEY so enabling chat does not automatically grant
local tool execution.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class ApiPrincipal:
    owner_id: str
    scope: str


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    return token


def _principal_for(
    authorization: str | None,
    *,
    env_name: str,
    scope: str,
) -> ApiPrincipal:
    expected = os.getenv(env_name, "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=f"{env_name} is not configured",
        )

    token = _bearer_token(authorization)
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # The memory layer stores ownership, not the secret itself.
    owner_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
    return ApiPrincipal(owner_id=owner_id, scope=scope)


def require_api_principal(
    authorization: str | None = Header(default=None),
) -> ApiPrincipal:
    return _principal_for(
        authorization,
        env_name="OPENCLAW_API_KEY",
        scope="api",
    )


def require_tools_principal(
    authorization: str | None = Header(default=None),
) -> ApiPrincipal:
    return _principal_for(
        authorization,
        env_name="OPENCLAW_TOOLS_API_KEY",
        scope="tools",
    )
