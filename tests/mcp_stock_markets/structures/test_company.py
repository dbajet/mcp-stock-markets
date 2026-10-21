from __future__ import annotations

from typing import Any

import pytest

from mcp_stock_markets.structures.company import Company
from tests.conftest import is_namedtuple


def helper_instance() -> Company:
    return Company(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        sub_industry="Technology Hardware, Storage & Peripherals",
        headquarters="Cupertino, California",
        exchange="NASDAQ",
    )


def helper_data() -> dict[str, Any]:
    return {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "sub_industry": "Technology Hardware, Storage & Peripherals",
        "headquarters": "Cupertino, California",
        "exchange": "NASDAQ",
    }


def test_class() -> None:
    tested = Company
    fields = {
        "symbol": "str",
        "name": "str",
        "sector": "str",
        "sub_industry": "str",
        "headquarters": "str",
        "exchange": "str",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = helper_instance()
    result = tested.to_dict()
    expected = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "sub_industry": "Technology Hardware, Storage & Peripherals",
        "headquarters": "Cupertino, California",
        "exchange": "NASDAQ",
    }
    assert result == expected


def test_from_dict() -> None:
    tested = Company
    result = tested.from_dict(helper_data())
    expected = Company(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Information Technology",
        sub_industry="Technology Hardware, Storage & Peripherals",
        headquarters="Cupertino, California",
        exchange="NASDAQ",
    )
    assert result == expected


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("symbol", id="symbol"),
        pytest.param("name", id="name"),
        pytest.param("sector", id="sector"),
        pytest.param("sub_industry", id="sub_industry"),
        pytest.param("headquarters", id="headquarters"),
        pytest.param("exchange", id="exchange"),
    ],
)
def test_from_dict__a_missing_field_raises(field: str) -> None:
    tested = Company
    data = {key: value for key, value in helper_data().items() if key != field}
    with pytest.raises(KeyError) as exc_info:
        tested.from_dict(data)
    expected = (field,)
    assert exc_info.value.args == expected
