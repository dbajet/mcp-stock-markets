from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from mcp_stock_markets.handlers.universe_request import UniverseRequest


def test_class() -> None:
    tested = UniverseRequest
    result = {name: (field.annotation, field.default) for name, field in tested.model_fields.items()}
    expected = {"symbol": (str, PydanticUndefined)}
    assert result == expected


def test_class__symbol_is_required() -> None:
    tested = UniverseRequest
    with pytest.raises(ValidationError) as exc_info:
        tested.model_validate({})
    result = [(error["type"], error["loc"]) for error in exc_info.value.errors()]
    expected = [("missing", ("symbol",))]
    assert result == expected
