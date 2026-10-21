from __future__ import annotations

from mcp_stock_markets.structures.connection_health import ConnectionHealth
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = ConnectionHealth
    fields = {"connection_id": "int", "is_ok": "bool", "detail": "str", "elapsed_ms": "float"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = ConnectionHealth(1, False, "The API key was refused.", 92.5)
    result = tested.to_dict()
    expected = {"connection_id": 1, "is_ok": False, "detail": "The API key was refused.", "elapsed_ms": 92.5}
    assert result == expected


def test_from_dict() -> None:
    tested = ConnectionHealth
    result = tested.from_dict({"connection_id": "1", "is_ok": True, "detail": "Connected.", "elapsed_ms": "12"})
    expected = ConnectionHealth(1, True, "Connected.", 12.0)
    assert result == expected
