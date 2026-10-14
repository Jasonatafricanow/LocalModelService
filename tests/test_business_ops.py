"""Order lookups over WhatsApp must not leak other customers' orders."""
from pathlib import Path
import sys

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from unittest.mock import patch

from modules.whatsapp_cs import business_ops


def _store_order(record):
    return patch.multiple(
        business_ops.store_api,
        is_enabled=lambda: True,
        fetch_order=lambda oid: {"data": record},
    )


def test_unknown_mock_order_is_not_invented():
    info = business_ops.get_order_status("99999999")
    assert info["found"] is False
    assert info["status"] == "not_found"


def test_store_order_owned_by_requester_is_returned():
    record = {"id": "123", "status": "shipped", "phone": "(11) 98765-4321"}
    with _store_order(record):
        info = business_ops.get_order_status("123", requester_phone="5511987654321")
    assert info["found"] is True and info["status"] == "shipped"
    assert "phone" not in info


def test_store_order_of_another_phone_is_hidden():
    record = {"id": "123", "status": "shipped", "total": 99.0, "phone": "5511987654321"}
    with _store_order(record):
        info = business_ops.get_order_status("123", requester_phone="5521912345678")
    assert info == {"order_id": "123", "found": False, "status": "not_found",
                    "estimated_delivery": "—", "total": None}


def test_mock_order_bound_to_creator_phone():
    created = business_ops.create_order({"name": "A", "phone": "+55 11 98765-4321"}, [])
    oid = created["order_id"]
    owner = business_ops.get_order_status(oid, requester_phone="5511987654321")
    other = business_ops.get_order_status(oid, requester_phone="5521912345678")
    assert owner["found"] is True
    assert other["found"] is False
