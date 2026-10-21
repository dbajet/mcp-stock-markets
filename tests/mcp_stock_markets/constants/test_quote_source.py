from __future__ import annotations

from mcp_stock_markets.constants.quote_source import QuoteSource


def test_enum() -> None:
    tested = QuoteSource
    expected = {"GOOGLE_FINANCE": "google_finance", "ALPHA_VANTAGE": "alpha_vantage"}
    assert {member.name: member.value for member in tested} == expected
