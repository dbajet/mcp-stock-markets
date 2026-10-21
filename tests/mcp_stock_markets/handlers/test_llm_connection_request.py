from __future__ import annotations

from pydantic_core import PydanticUndefined

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.handlers.llm_connection_request import LlmConnectionRequest


def test_class() -> None:
    tested = LlmConnectionRequest
    result = {name: (field.annotation, field.default) for name, field in tested.model_fields.items()}
    expected = {
        "name": (str, PydanticUndefined),
        "kind": (LlmKind, PydanticUndefined),
        "base_url": (str, ""),
        "api_key": (str, ""),
        "model": (str, PydanticUndefined),
        "disable_thinking": (bool, True),
    }
    assert result == expected
