from __future__ import annotations

import pytest

from mcp_stock_markets.libraries.blind_index import BlindIndex
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.libraries.user_store import UserStore
from mcp_stock_markets.structures.user_account import UserAccount
from tests.conftest import helper_database

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_store(database: Database) -> UserStore:
    return UserStore(database, SecretSealer(KEY), BlindIndex(KEY))


def helper_disabled(database: Database) -> list[dict[str, object]]:
    return database.rows("SELECT id, disabled_at IS NOT NULL AS is_disabled FROM users ORDER BY id", ())


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    sealer = SecretSealer(KEY)
    index = BlindIndex(KEY)
    tested = UserStore(database, sealer, index)
    result = (tested._database is database, tested._sealer is sealer, tested._index is index)
    expected = (True, True, True)
    assert result == expected


@pytest.mark.database
def test_owned() -> None:
    """Made when missing; found, and enabled again, when it exists."""
    database = helper_database()
    tested = helper_store(database)
    result = tested.owned("  Ada@Example.COM ", "ada")
    database.executed("UPDATE users SET disabled_at = now()", ())
    again = tested.owned("ada@example.com", "another name")
    stored = database.row("SELECT email_sealed, email_hash FROM users WHERE id = %s", (1,))
    count = database.row("SELECT count(*) AS users FROM users", ())
    expected = UserAccount(1, "ada@example.com", "ada", False)
    assert result == expected
    exp_again = UserAccount(1, "ada@example.com", "ada", False)
    assert again == exp_again
    exp_count = {"users": 1}
    assert count == exp_count
    # Sealed at rest: only the key opens the stored bytes back into the address.
    exp_opened = "ada@example.com"
    assert SecretSealer(KEY).opened(bytes(stored["email_sealed"])) == exp_opened
    exp_hash = "b7dcba6642c68e73715cc669ae86293d5bcf299d0c82964b5928553d93d86727"
    assert stored["email_hash"] == exp_hash


@pytest.mark.database
def test_others_disabled() -> None:
    database = helper_database()
    tested = helper_store(database)
    tested.owned("ada@example.com", "ada")
    tested.owned("bob@example.com", "bob")
    tested.owned("eve@example.com", "eve")
    result = (tested.others_disabled(1), tested.others_disabled(1))
    expected = (2, 0)
    assert result == expected
    exp_rows = [
        {"id": 1, "is_disabled": False},
        {"id": 2, "is_disabled": True},
        {"id": 3, "is_disabled": True},
    ]
    assert helper_disabled(database) == exp_rows


@pytest.mark.database
def test_by_id() -> None:
    database = helper_database()
    tested = helper_store(database)
    tested.owned("ada@example.com", "Ada")
    result = (tested.by_id(1), tested.by_id(2))
    expected = (UserAccount(1, "ada@example.com", "Ada", False), None)
    assert result == expected


@pytest.mark.database
def test_by_email() -> None:
    database = helper_database()
    tested = helper_store(database)
    tested.owned("ada@example.com", "Ada")
    result = (tested.by_email(" ADA@example.com  "), tested.by_email("bob@example.com"))
    expected = (UserAccount(1, "ada@example.com", "Ada", False), None)
    assert result == expected


@pytest.mark.parametrize(
    "disabled_at, is_disabled",
    [
        pytest.param(None, False, id="enabled"),
        pytest.param("2026-10-19T10:00:00+00:00", True, id="disabled"),
    ],
)
def test__account(disabled_at: str | None, is_disabled: bool) -> None:
    tested = helper_store(Database("postgresql://u:p@h/d"))
    row = {
        "id": 4,
        "email_sealed": SecretSealer(KEY).sealed("ada@example.com"),
        "display_name": "Ada",
        "disabled_at": disabled_at,
    }
    result = tested._account(row)
    expected = UserAccount(4, "ada@example.com", "Ada", is_disabled)
    assert result == expected
