"""Business operations (stock / orders) for WhatsApp customer service.

Pluggable data source:
  * If the ``business`` REST backend is configured **and** enabled
    (see :mod:`store_api`), stock / order / product lookups hit the real
    store API.
  * Otherwise it falls back to in-memory MOCK data, so the demo, an
    unconfigured appliance, or a transient API outage all keep working
    without crashing the conversation.

The public return contracts are STABLE — ``handler.py`` depends only on the
dict shapes below, so the data source can be swapped without touching
anything else.

>>> To go live: set ``business.enabled=true`` + ``base_url`` in the config,
>>> export the token env var, and adjust the two ``_map_*`` adapters so the
>>> field names match YOUR API's JSON. Everything else stays as-is.
"""
import logging
import random
from typing import Any, Optional

from . import store_api

logger = logging.getLogger(__name__)

# Friendly "please hold" line shown when the live backend errors out
# (Portuguese, matches the CS persona). Keep the flow alive, never crash.
_BUSY_MSG = "Estou verificando no sistema, um momento por favor…"

# ---------------------------------------------------------------------------
# In-memory mock data (used only when the REST backend is disabled)
# ---------------------------------------------------------------------------
MOCK_STOCK: dict[str, dict] = {
    "X200": {"in_stock": True, "quantity": 15, "price": 2999.00},
    "X200 PRO": {"in_stock": True, "quantity": 8, "price": 4599.00},
    "X300": {"in_stock": False, "quantity": 0, "price": 3999.00},
    "TAB-A70": {"in_stock": True, "quantity": 42, "price": 1899.00},
    "TAB-A80": {"in_stock": True, "quantity": 3, "price": 2499.00},
    "SMART-WATCH Z5": {"in_stock": False, "quantity": 0, "price": 1299.00},
    "FONE-BT100": {"in_stock": True, "quantity": 60, "price": 299.00},
}
MOCK_ORDERS: dict[str, dict] = {}
_next_order_id: int = 10000


# ---------------------------------------------------------------------------
# Field-mapping adapters  ——  >>> ADJUST TO YOUR API's JSON <<<
# These are the ONLY places that know your API's field names.
# ---------------------------------------------------------------------------
def _pick(d: Any, *keys, default=None):
    if isinstance(d, dict):
        for k in keys:
            if d.get(k) is not None:
                return d[k]
    return default


def _map_stock(raw: Any, queried: str) -> dict:
    """Map your API's stock JSON -> stable check_stock() contract."""
    # If your API wraps the record (e.g. {"data": {...}}), unwrap here:
    rec = _pick(raw, "data", "result", "item", default=raw)
    qty = int(_pick(rec, "quantity", "qty", "stock", "estoque", default=0) or 0)
    price = _pick(rec, "price", "preco", "valor")
    in_stock = bool(_pick(rec, "in_stock", "available", "disponivel", default=(qty > 0)))
    name = _pick(rec, "product", "name", "nome", "code", "sku", "codigo", default=queried)
    found = bool(_pick(rec, "found", "exists", default=(rec is not None)))
    if not found:
        return {"product": queried, "found": False, "in_stock": False,
                "quantity": 0, "price": None,
                "message": f"Produto '{queried}' não encontrado no catálogo."}
    try:
        price_txt = f"R$ {float(price):.2f}" if price is not None else "—"
    except (TypeError, ValueError):
        price_txt = str(price)
    message = (
        f"Temos {qty} unidade(s) em estoque a {price_txt} cada."
        if in_stock else "Este produto está esgotado no momento."
    )
    return {"product": name, "found": True, "in_stock": in_stock,
            "quantity": qty, "price": price, "message": message}


def _map_order(raw: Any, queried: str) -> dict:
    """Map your API's order JSON -> stable get_order_status() contract."""
    rec = _pick(raw, "data", "result", "order", default=raw)
    found = bool(_pick(rec, "found", "exists", default=(rec is not None)))
    return {
        "order_id": str(_pick(rec, "order_id", "id", "numero", default=queried)),
        "found": found,
        "status": _pick(rec, "status", "situacao", "state", default="unknown"),
        "estimated_delivery": _pick(rec, "estimated_delivery", "eta", "previsao",
                                    default="—"),
        "total": _pick(rec, "total", "valor_total", "amount"),
    }


def _map_products(raw: Any) -> list[str]:
    """Map your API's product-list JSON -> list of code/SKU strings."""
    items = raw if isinstance(raw, list) else _pick(raw, "items", "data", "products", default=[])
    codes: list[str] = []
    for it in items or []:
        code = _pick(it, "code", "sku", "codigo", "model", "name") if isinstance(it, dict) else it
        if code:
            codes.append(str(code))
    return codes


# ---------------------------------------------------------------------------
# Public API  ——  STABLE contracts (handler.py depends on these)
# ---------------------------------------------------------------------------
def get_known_products() -> list[str]:
    """Return all known product identifiers (for intent/product matching)."""
    if store_api.is_enabled():
        try:
            return _map_products(store_api.fetch_products())
        except Exception as e:  # noqa: BLE001 - degrade to mock, never crash
            logger.warning("store_api products failed, using mock: %s", e)
    return list(MOCK_STOCK.keys())


def check_stock(product_model: str) -> dict:
    """Check stock availability. Returns:
    {product, found, in_stock, quantity, price, message}
    """
    key = product_model.upper().strip()
    if store_api.is_enabled():
        try:
            return _map_stock(store_api.fetch_stock(key), product_model)
        except Exception as e:  # noqa: BLE001 - graceful degradation
            logger.warning("store_api stock lookup failed for %s: %s", key, e)
            return {"product": product_model, "found": False, "in_stock": False,
                    "quantity": 0, "price": None, "message": _BUSY_MSG}

    # ---- mock fallback ----
    info = MOCK_STOCK.get(key)
    if info is None:
        return {"product": product_model, "found": False, "in_stock": False,
                "quantity": 0, "price": None,
                "message": f"Product '{product_model}' was not found in our catalog."}
    return {
        "product": key, "found": True, "in_stock": info["in_stock"],
        "quantity": info["quantity"], "price": info["price"],
        "message": (
            f"We have {info['quantity']} unit(s) in stock at ${info['price']:.2f} each."
            if info["in_stock"] else "This product is currently out of stock."
        ),
    }


def get_order_status(order_id: str) -> dict:
    """Look up an order's status. Returns:
    {order_id, found, status, estimated_delivery, total}
    """
    oid = str(order_id).strip()
    if store_api.is_enabled():
        try:
            return _map_order(store_api.fetch_order(oid), oid)
        except Exception as e:  # noqa: BLE001 - graceful degradation
            logger.warning("store_api order lookup failed for %s: %s", oid, e)
            return {"order_id": oid, "found": False, "status": "unknown",
                    "estimated_delivery": "—", "total": None}

    # ---- mock fallback ----
    if oid in MOCK_ORDERS:
        order = MOCK_ORDERS[oid]
        return {"order_id": oid, "found": True, "status": order["status"],
                "estimated_delivery": "3-5 business days", "total": order.get("total")}
    chosen = random.choice(["processing", "shipped", "in_transit", "delivered"])
    return {"order_id": oid, "found": True, "status": chosen,
            "estimated_delivery": "3-5 business days", "total": None}


def create_order(customer_info: Optional[dict] = None,
                 products: Optional[list[dict]] = None) -> dict:
    """Create an order. (Mock only — wire a POST in store_api when needed.)"""
    global _next_order_id
    customer_info = customer_info or {}
    products = products or []
    order_id = str(_next_order_id)
    _next_order_id += 1
    total = sum(p.get("price", 0) * p.get("quantity", 1) for p in products)
    MOCK_ORDERS[order_id] = {"order_id": order_id, "customer": customer_info,
                             "products": products, "status": "confirmed",
                             "total": round(total, 2)}
    logger.info("Order %s created for %s", order_id, customer_info.get("name", "unknown"))
    return {"order_id": order_id, "status": "confirmed", "total": round(total, 2),
            "message": f"Order #{order_id} confirmed! Total: ${total:.2f}"}
