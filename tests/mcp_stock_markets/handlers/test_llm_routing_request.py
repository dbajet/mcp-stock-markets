from __future__ import annotations

from mcp_stock_markets.handlers.llm_routing_request import LlmRoutingRequest


def test_class() -> None:
    tested = LlmRoutingRequest
    result = {name: (field.annotation, field.default) for name, field in tested.model_fields.items()}
    expected = {"agent": (int | None, None)}
    assert result == expected
