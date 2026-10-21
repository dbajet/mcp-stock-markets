from __future__ import annotations

import pytest

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.structures.llm_connection import LlmConnection
from tests.conftest import is_namedtuple


def helper_instance(api_key: str) -> LlmConnection:
    return LlmConnection(2, "Local", LlmKind.OPENAI, "https://llm.example.com/v1", api_key, "good", True)


def test_class() -> None:
    tested = LlmConnection
    fields = {
        "connection_id": "int",
        "name": "str",
        "kind": "LlmKind",
        "base_url": "str",
        "api_key": "str",
        "model": "str",
        "disable_thinking": "bool",
    }
    assert is_namedtuple(tested, fields)


@pytest.mark.parametrize(
    "api_key, exp_has_key",
    [
        pytest.param("secret", True, id="key"),
        pytest.param("", False, id="no-key"),
    ],
)
def test_public_dict(api_key: str, exp_has_key: bool) -> None:
    tested = helper_instance(api_key)
    result = tested.public_dict()
    expected = {
        "connection_id": 2,
        "name": "Local",
        "kind": "openai",
        "base_url": "https://llm.example.com/v1",
        "has_key": exp_has_key,
        "model": "good",
        "disable_thinking": True,
    }
    assert result == expected


def test_to_dict() -> None:
    tested = helper_instance("secret")
    result = tested.to_dict()
    expected = {
        "connection_id": 2,
        "name": "Local",
        "kind": "openai",
        "base_url": "https://llm.example.com/v1",
        "api_key": "secret",
        "model": "good",
        "disable_thinking": True,
    }
    assert result == expected


def test_from_dict() -> None:
    tested = LlmConnection
    result = tested.from_dict(
        {
            "connection_id": "2",
            "name": "Local",
            "kind": "openai",
            "base_url": "https://llm.example.com/v1",
            "api_key": "secret",
            "model": "good",
            "disable_thinking": True,
        }
    )
    expected = helper_instance("secret")
    assert result == expected
