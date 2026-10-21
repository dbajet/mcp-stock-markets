from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from mcp_stock_markets.handlers.token_request import TokenRequest


def test_class() -> None:
    tested = TokenRequest
    result = {name: (field.annotation, field.default) for name, field in tested.model_fields.items()}
    expected = {"token": (str, PydanticUndefined)}
    assert result == expected


def test_class__a_token_is_a_string() -> None:
    tested = TokenRequest
    with pytest.raises(ValidationError) as exc_info:
        tested.model_validate({"token": 12})
    result = [(error["type"], error["loc"]) for error in exc_info.value.errors()]
    expected = [("string_type", ("token",))]
    assert result == expected
