from __future__ import annotations

from mcp_stock_markets.structures.user_account import UserAccount
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = UserAccount
    fields = {
        "user_id": "int",
        "email": "str",
        "display_name": "str",
        "is_disabled": "bool",
    }
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = UserAccount(
        user_id=7,
        email="ada@example.com",
        display_name="Ada",
        is_disabled=False,
    )
    result = tested.to_dict()
    expected = {
        "user_id": 7,
        "email": "ada@example.com",
        "display_name": "Ada",
        "is_disabled": False,
    }
    assert result == expected


def test_from_dict() -> None:
    tested = UserAccount
    result = tested.from_dict(
        {
            "user_id": "7",
            "email": "ada@example.com",
            "display_name": "Ada",
            "is_disabled": 1,
        }
    )
    expected = UserAccount(
        user_id=7,
        email="ada@example.com",
        display_name="Ada",
        is_disabled=True,
    )
    assert result == expected
