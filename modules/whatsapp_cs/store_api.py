"""Thin REST client for the store's inventory / order backend.

Transport only — no business logic. ``business_ops`` maps the raw JSON these
functions return onto its stable contracts and handles fallback.

Configuration lives under the ``business`` key of the runtime config
(``config/agent_llm_config.json``); the **secret token is read from an
environment variable**, never from the config file (the config gets baked
into the appliance ISO, so credentials must not live there).

Example config block::

    "business": {
        "enabled": true,
        "base_url": "https://api.suatloja.com",
        "timeout": 8,
        "auth": { "scheme": "bearer", "token_env": "STORE_API_TOKEN" },
        "endpoints": {
            "stock":    "/stock/{code}",
            "order":    "/orders/{order_id}",
            "products": "/products"
        }
    }

Then on the appliance: ``export STORE_API_TOKEN=xxxxx`` (or put it in an
EnvironmentFile referenced by openclaw.service — not in git).
"""
import logging
import os
from typing import Any

import requests

from src.core.config import load_config

logger = logging.getLogger(__name__)


class StoreAPIError(Exception):
    """Raised on any transport/HTTP failure talking to the store backend."""


def _cfg() -> dict:
    try:
        return (load_config() or {}).get("business", {}) or {}
    except Exception:
        return {}


def is_enabled() -> bool:
    """True only when a business backend is configured and switched on."""
    c = _cfg()
    return bool(c.get("enabled") and c.get("base_url"))


def _headers() -> dict:
    auth = _cfg().get("auth", {}) or {}
    scheme = str(auth.get("scheme", "")).lower()
    token = os.getenv(auth.get("token_env", "STORE_API_TOKEN"), "")
    headers = {"Accept": "application/json"}
    if not token:
        return headers
    if scheme == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    elif scheme in ("apikey", "api_key", "header"):
        headers[auth.get("header", "X-API-Key")] = token
    return headers


def _auth_tuple():
    auth = _cfg().get("auth", {}) or {}
    if str(auth.get("scheme", "")).lower() == "basic":
        user = os.getenv(auth.get("user_env", "STORE_API_USER"), "")
        pwd = os.getenv(auth.get("token_env", "STORE_API_TOKEN"), "")
        if user:
            return (user, pwd)
    return None


def _get(endpoint_key: str, default_path: str, **fmt) -> Any:
    c = _cfg()
    base = str(c.get("base_url", "")).rstrip("/")
    path = (c.get("endpoints", {}) or {}).get(endpoint_key, default_path)
    url = base + path.format(**fmt)
    try:
        resp = requests.get(
            url,
            headers=_headers(),
            auth=_auth_tuple(),
            timeout=c.get("timeout", 8),
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        raise StoreAPIError(f"GET {url} failed: {e}") from e


def fetch_stock(code: str) -> Any:
    """Raw JSON for one product's stock, looked up by product code/SKU."""
    return _get("stock", "/stock/{code}", code=requests.utils.quote(str(code), safe=""))


def fetch_order(order_id: str) -> Any:
    """Raw JSON for one order, looked up by order id."""
    return _get("order", "/orders/{order_id}", order_id=requests.utils.quote(str(order_id), safe=""))


def fetch_products() -> Any:
    """Raw JSON of the product catalog (list of products or a wrapper dict)."""
    return _get("products", "/products")
