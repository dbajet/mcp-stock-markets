from __future__ import annotations

from mcp_stock_markets.structures.migration import Migration
from tests.conftest import is_namedtuple


def test_class() -> None:
    tested = Migration
    fields = {"version": "int", "description": "str", "statements": "tuple[str, ...]"}
    assert is_namedtuple(tested, fields)


def test_to_dict() -> None:
    tested = Migration(version=1, description="initial", statements=("CREATE TABLE a ()", "CREATE TABLE b ()"))
    result = tested.to_dict()
    expected = {"version": 1, "description": "initial", "statements": ["CREATE TABLE a ()", "CREATE TABLE b ()"]}
    assert result == expected


def test_from_dict() -> None:
    tested = Migration
    result = tested.from_dict({"version": "2", "description": "more", "statements": ["CREATE TABLE c ()"]})
    expected = Migration(version=2, description="more", statements=("CREATE TABLE c ()",))
    assert result == expected
