from __future__ import annotations

from mcp_stock_markets.structures.app_exception import AppException


def test_inheritance() -> None:
    assert issubclass(AppException, RuntimeError)


def test___init__() -> None:
    tested = AppException(404, "Not found.")
    result = (tested.status_code, tested.message, str(tested))
    expected = (404, "Not found.", "Not found.")
    assert result == expected
