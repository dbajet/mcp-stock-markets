from __future__ import annotations

from unittest.mock import call, patch

from mcp_stock_markets.libraries import token_maker as token_maker_module
from mcp_stock_markets.libraries.token_maker import TokenMaker


def test_token() -> None:
    tested = TokenMaker
    with patch.object(token_maker_module.secrets, "token_urlsafe", side_effect=["tok123"]) as mock_token_urlsafe:
        result = tested.token()
    expected = "tok123"
    assert result == expected
    exp_calls = [call(32)]
    assert mock_token_urlsafe.mock_calls == exp_calls


def test_token__is_random_and_url_safe() -> None:
    tested = TokenMaker
    first = tested.token()
    second = tested.token()
    result = (len(first), first != second, first.replace("-", "a").replace("_", "a").isalnum())
    expected = (43, True, True)
    assert result == expected


def test_digest() -> None:
    tested = TokenMaker
    result = tested.digest("tok123")
    expected = "4f6e1f65055263866dedb3c5fe22defb0cc045648cf0b87afac54cc6420e5647"
    assert result == expected
