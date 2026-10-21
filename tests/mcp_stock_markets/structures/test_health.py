from __future__ import annotations

from mcp_stock_markets.structures.health import Health
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = Health
    fields = {"ok": "bool", "version": "str", "commit": "str"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = Health(ok=True, version="2026-10-19.1", commit="abc123")
    result = tested.to_dict()
    expected = {"ok": True, "version": "2026-10-19.1", "commit": "abc123"}
    assert result == expected


def test_from_dict() -> None:
    tested = Health
    result = tested.from_dict({"ok": False, "version": "dev", "commit": "dev"})
    expected = Health(ok=False, version="dev", commit="dev")
    assert result == expected
