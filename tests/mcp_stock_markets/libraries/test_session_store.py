from __future__ import annotations

from datetime import timedelta

import pytest

from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.session_store import SessionStore
from tests.conftest import helper_database


def helper_user(database: Database, name: str) -> None:
    database.executed(
        "INSERT INTO users (email_sealed, email_hash, display_name) VALUES (%s, %s, %s)",
        (b"sealed", f"hash-{name}", name),
    )


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    tested = SessionStore(database)
    result = tested._database is database
    assert result is True


@pytest.mark.database
def test_created() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = SessionStore(database)
    tested.created(1, "token-old")
    database.executed(
        "UPDATE sessions SET expires_at = now() - interval '1 second' WHERE token_hash = %s", ("token-old",)
    )
    tested.created(1, "token-live")
    result = tested.created(1, "token-a")
    stored = database.rows(
        "SELECT user_id, token_hash, expires_at - created_at AS lifetime FROM sessions ORDER BY id", ()
    )
    assert result is None
    # The expired session went as the next one came.
    exp_stored = [
        {"user_id": 1, "token_hash": "token-live", "lifetime": timedelta(days=30)},
        {"user_id": 1, "token_hash": "token-a", "lifetime": timedelta(days=30)},
    ]
    assert stored == exp_stored


@pytest.mark.database
def test_user_id_of() -> None:
    database = helper_database()
    helper_user(database, "ada")
    helper_user(database, "bob")
    tested = SessionStore(database)
    tested.created(1, "token-a")
    tested.created(2, "token-b")
    result = (tested.user_id_of("token-a"), tested.user_id_of("token-b"), tested.user_id_of("unknown"))
    expected = (1, 2, None)
    assert result == expected


@pytest.mark.database
def test_user_id_of__expired_session() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = SessionStore(database)
    tested.created(1, "token-a")
    database.executed(
        "UPDATE sessions SET expires_at = now() - interval '1 second' WHERE token_hash = %s", ("token-a",)
    )
    result = tested.user_id_of("token-a")
    assert result is None


@pytest.mark.database
def test_user_id_of__disabled_user() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = SessionStore(database)
    tested.created(1, "token-a")
    database.executed("UPDATE users SET disabled_at = now() WHERE id = %s", (1,))
    result = tested.user_id_of("token-a")
    assert result is None


@pytest.mark.database
def test_deleted() -> None:
    database = helper_database()
    helper_user(database, "ada")
    tested = SessionStore(database)
    tested.created(1, "token-a")
    tested.created(1, "token-b")
    result = tested.deleted("token-a")
    stored = database.rows("SELECT token_hash FROM sessions ORDER BY id", ())
    assert result is None
    exp_stored = [{"token_hash": "token-b"}]
    assert stored == exp_stored


@pytest.mark.database
def test_deleted_for() -> None:
    database = helper_database()
    helper_user(database, "ada")
    helper_user(database, "bob")
    tested = SessionStore(database)
    tested.created(1, "token-a1")
    tested.created(2, "token-b")
    tested.created(1, "token-a2")
    result = tested.deleted_for(1)
    stored = database.rows("SELECT user_id, token_hash FROM sessions ORDER BY id", ())
    assert result is None
    exp_stored = [{"user_id": 2, "token_hash": "token-b"}]
    assert stored == exp_stored
