from __future__ import annotations

from mcp_stock_markets.constants.trade_side import TradeSide


def test_enum() -> None:
    tested = TradeSide
    expected = {"BUY": "buy", "SELL": "sell"}
    assert {member.name: member.value for member in tested} == expected
