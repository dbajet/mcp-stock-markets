from __future__ import annotations

import logging
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.owner_command import OwnerCommand
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.user_account import UserAccount

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_instance() -> OwnerCommand:
    return OwnerCommand(UserStore(Database("postgresql://u:p@h/d"), SecretSealer(KEY), BlindIndex(KEY)))


def helper_owner() -> UserAccount:
    return UserAccount(user_id=1, email="owner@example.com", display_name="owner", is_disabled=False)


def test___init__() -> None:
    users = UserStore(Database("postgresql://u:p@h/d"), SecretSealer(KEY), BlindIndex(KEY))
    tested = OwnerCommand(users)
    result = tested._users
    expected = users
    assert result == expected


@pytest.mark.parametrize(
    "disabled, exp_messages",
    [
        pytest.param(0, [], id="alone-already"),
        pytest.param(2, ["[USERS] 2 other accounts disabled"], id="others-disabled"),
    ],
)
def test_owner(caplog: pytest.LogCaptureFixture, disabled: int, exp_messages: list[str]) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(UserStore, "owned", side_effect=[helper_owner()]) as mock_owned,
        patch.object(UserStore, "others_disabled", side_effect=[disabled]) as mock_others_disabled,
    ):
        result = tested.owner("owner@example.com")
    expected = helper_owner()
    assert result == expected
    assert caplog.messages == exp_messages
    exp_calls = [call("owner@example.com", "owner")]
    assert mock_owned.mock_calls == exp_calls
    exp_calls = [call(1)]
    assert mock_others_disabled.mock_calls == exp_calls


def test_owner__no_address(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_instance()
    with (
        caplog.at_level(logging.WARNING, logger="mcp_stock_markets"),
        patch.object(UserStore, "owned", side_effect=[]) as mock_owned,
    ):
        result = tested.owner("")
    assert result is None
    exp_messages = ["[USERS] no owner address: nobody can sign in"]
    assert caplog.messages == exp_messages
    exp_calls = []
    assert mock_owned.mock_calls == exp_calls
