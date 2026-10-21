from __future__ import annotations

from unittest.mock import call, patch

import pytest

from mcp_stock_markets.commands.session_command import SessionCommand
from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.session_store import SessionStore
from mcp_stock_markets.libraries.token_maker import TokenMaker
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.user_account import UserAccount


def helper_users() -> UserStore:
    key = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="
    return UserStore(Database("postgresql://u:p@h/d"), SecretSealer(key), BlindIndex(key))


def helper_instance() -> SessionCommand:
    return SessionCommand(helper_users(), SessionStore(Database("postgresql://u:p@h/d")))


def helper_user() -> UserAccount:
    return UserAccount(
        user_id=7,
        email="ada@example.com",
        display_name="Ada",
        is_disabled=False,
    )


def test___init__() -> None:
    users = helper_users()
    sessions = SessionStore(Database("postgresql://u:p@h/d"))
    tested = SessionCommand(users, sessions)
    result = (tested._users, tested._sessions)
    expected = (users, sessions)
    assert result == expected


def test_started() -> None:
    tested = helper_instance()
    with (
        patch.object(TokenMaker, "token", side_effect=["tok-1"]) as mock_token,
        patch.object(SessionStore, "created", side_effect=[None]) as mock_created,
    ):
        result = tested.started(7)
    expected = "tok-1"
    assert result == expected
    exp_calls = [call()]
    assert mock_token.mock_calls == exp_calls
    exp_calls = [call(7, "65dcf16ea3dfa49069628089eb4a75483070f5584b2a21ee64912b5f621f12da")]
    assert mock_created.mock_calls == exp_calls


@pytest.mark.parametrize(
    "token, user_ids, users, expected, exp_user_id_of_calls, exp_by_id_calls",
    [
        pytest.param("", [], [], None, [], [], id="no_cookie"),
        pytest.param(
            "tok-1",
            [None],
            [],
            None,
            [call("65dcf16ea3dfa49069628089eb4a75483070f5584b2a21ee64912b5f621f12da")],
            [],
            id="unknown_session",
        ),
        pytest.param(
            "tok-1",
            [7],
            [None],
            None,
            [call("65dcf16ea3dfa49069628089eb4a75483070f5584b2a21ee64912b5f621f12da")],
            [call(7)],
            id="vanished_user",
        ),
        pytest.param(
            "tok-1",
            [7],
            [helper_user()],
            helper_user(),
            [call("65dcf16ea3dfa49069628089eb4a75483070f5584b2a21ee64912b5f621f12da")],
            [call(7)],
            id="signed_in",
        ),
    ],
)
def test_current(
    token: str,
    user_ids: list[int | None],
    users: list[UserAccount | None],
    expected: UserAccount | None,
    exp_user_id_of_calls: list,
    exp_by_id_calls: list,
) -> None:
    tested = helper_instance()
    with (
        patch.object(SessionStore, "user_id_of", side_effect=user_ids) as mock_user_id_of,
        patch.object(UserStore, "by_id", side_effect=users) as mock_by_id,
    ):
        result = tested.current(token)
    assert result == expected
    assert mock_user_id_of.mock_calls == exp_user_id_of_calls
    assert mock_by_id.mock_calls == exp_by_id_calls


@pytest.mark.parametrize(
    "token, exp_calls",
    [
        pytest.param("", [], id="no_cookie"),
        pytest.param("tok-1", [call("65dcf16ea3dfa49069628089eb4a75483070f5584b2a21ee64912b5f621f12da")], id="cookie"),
    ],
)
def test_ended(token: str, exp_calls: list) -> None:
    tested = helper_instance()
    with patch.object(SessionStore, "deleted", side_effect=[None]) as mock_deleted:
        result = tested.ended(token)
    assert result is None
    assert mock_deleted.mock_calls == exp_calls
