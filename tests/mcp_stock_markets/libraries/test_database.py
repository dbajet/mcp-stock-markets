from __future__ import annotations

import hashlib
import logging
import os
from unittest.mock import call, patch

import psycopg
import pytest

from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.structures.app_exception import AppException
from tests.conftest import helper_database


def helper_scratch() -> Database:
    """A Database of the test's own on the worker's scratch database, for the
    tests about connections and migrations: the shared one from
    `helper_database` is never closed or dropped under the other tests."""
    return Database(os.environ["TEST_DATABASE_URL"])


def helper_schema_dropped(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")


def test___init__() -> None:
    tested = Database("postgresql://u:p@h/d")
    result = (tested._url, tested._opened, getattr(tested._local, "connection", None))
    expected = ("postgresql://u:p@h/d", [], None)
    assert result == expected


def test_migrations() -> None:
    tested = Database
    result = tested.migrations()
    expected = (
        (1, "the owner, the market, the portfolio and the agent's runs", 21, "20cb0d4f1f3d3ec79e4412d43dc710b3"),
    )
    text = "\n\n".join("\n".join(migration.statements) for migration in result)
    digests = tuple(
        (
            migration.version,
            migration.description,
            len(migration.statements),
            hashlib.md5("\n".join(migration.statements).encode()).hexdigest(),
        )
        for migration in result
    )
    assert digests == expected, text


@pytest.mark.database
def test_transaction() -> None:
    tested = helper_database()
    with tested.transaction() as outer:
        outer.execute("INSERT INTO schema_migrations (version, description) VALUES (%s, %s)", (50, "kept"))
        with tested.transaction() as inner:
            is_same = inner is outer
    with pytest.raises(AppException) as exc_info:
        with tested.transaction() as connection:
            connection.execute("INSERT INTO schema_migrations (version, description) VALUES (%s, %s)", (51, "x"))
            raise AppException(409, "Rolled back.")
    result = tested.rows("SELECT version FROM schema_migrations WHERE version >= %s ORDER BY version", (50,))
    tested.executed("DELETE FROM schema_migrations WHERE version >= %s", (50,))
    expected = [{"version": 50}]
    assert result == expected
    assert is_same is True
    exp_error = (409, "Rolled back.")
    assert (exc_info.value.status_code, exc_info.value.message) == exp_error


@pytest.mark.database
def test_transaction__a_database_error_is_unavailable(caplog: pytest.LogCaptureFixture) -> None:
    tested = helper_database()
    with caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        with pytest.raises(AppException) as exc_info:
            tested.rows("SELECT * FROM no_such_table", ())
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (503, "The database is unavailable.")
    assert result == expected
    exp_messages = ["[DATABASE] UndefinedTable"]
    assert [record.getMessage() for record in caplog.records] == exp_messages


@pytest.mark.database
def test_rows() -> None:
    tested = helper_database()
    result = tested.rows("SELECT version, description FROM schema_migrations ORDER BY version", ())
    expected = [{"version": 1, "description": "the owner, the market, the portfolio and the agent's runs"}]
    assert result == expected


@pytest.mark.database
def test_row() -> None:
    tested = helper_database()
    result = (
        tested.row("SELECT description FROM schema_migrations WHERE version = %s", (1,)),
        tested.row("SELECT description FROM schema_migrations WHERE version = %s", (999,)),
    )
    expected = ({"description": "the owner, the market, the portfolio and the agent's runs"}, None)
    assert result == expected


@pytest.mark.database
def test_returned() -> None:
    tested = helper_database()
    result = tested.returned(
        "INSERT INTO users (email_sealed, email_hash, display_name) VALUES (%s, %s, %s) RETURNING id, display_name",
        (b"sealed", "hash-ada", "Ada"),
    )
    expected = {"id": 1, "display_name": "Ada"}
    assert result == expected


def test_returned__nothing_returned_is_an_error() -> None:
    tested = Database("postgresql://u:p@h/d")
    with patch.object(Database, "row", side_effect=[None]) as mock_row:
        with pytest.raises(AppException) as exc_info:
            tested.returned("INSERT INTO t (a) VALUES (%s) RETURNING a", (1,))
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (500, "The database returned nothing.")
    assert result == expected
    exp_calls = [call("INSERT INTO t (a) VALUES (%s) RETURNING a", (1,))]
    assert mock_row.mock_calls == exp_calls


@pytest.mark.database
def test_executed() -> None:
    tested = helper_database()
    tested.executed(
        "INSERT INTO users (email_sealed, email_hash, display_name) VALUES (%s, %s, %s)", (b"s", "hash-ada", "Ada")
    )
    result = (
        tested.executed("UPDATE users SET display_name = %s WHERE id = %s", ("Ada L.", 1)),
        tested.executed("UPDATE users SET display_name = %s WHERE id = %s", ("Nobody", 999)),
    )
    expected = (1, 0)
    assert result == expected


@pytest.mark.database
def test_held() -> None:
    """A free lock is taken for the block: another connection cannot take it
    meanwhile, and can once the block ends."""
    tested = helper_scratch()
    other = psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True, connect_timeout=10)
    try:
        with tested.held(7_310_499) as is_taken:
            during = other.execute("SELECT pg_try_advisory_lock(%s)", (7_310_499,)).fetchone()
        after = other.execute("SELECT pg_try_advisory_lock(%s)", (7_310_499,)).fetchone()
        other.execute("SELECT pg_advisory_unlock(%s)", (7_310_499,))
    finally:
        other.close()
        tested.closed()
    assert is_taken is True
    expected = ((False,), (True,))
    assert (during, after) == expected


@pytest.mark.database
def test_held__a_lock_taken_by_another_connection_is_not_held() -> None:
    """Taken elsewhere: the block runs knowing it, and its end releases
    nothing, so the other holder keeps the lock."""
    tested = helper_scratch()
    other = psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True, connect_timeout=10)
    try:
        other.execute("SELECT pg_advisory_lock(%s)", (7_310_498,))
        with tested.held(7_310_498) as is_taken:
            pass
        still_held = tested.row("SELECT pg_try_advisory_lock(%s) AS taken", (7_310_498,))
        other.execute("SELECT pg_advisory_unlock(%s)", (7_310_498,))
    finally:
        other.close()
        tested.closed()
    assert is_taken is False
    expected = {"taken": False}
    assert still_held == expected


@pytest.mark.database
def test_is_reachable() -> None:
    tested = helper_scratch()
    try:
        result = tested.is_reachable()
    finally:
        tested.closed()
    assert result is True


def test_is_reachable__a_dropped_connection_is_replaced_once() -> None:
    tested = Database("postgresql://u:p@h/d")
    with (
        patch.object(Database, "_is_answering", side_effect=[AppException(503, "x"), True]) as mock_answering,
        patch.object(Database, "_forget_connection", side_effect=[None]) as mock_forget,
    ):
        result = tested.is_reachable()
    assert result is True
    exp_calls = [call(), call()]
    assert mock_answering.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_forget.mock_calls == exp_calls


def test_is_reachable__unreachable() -> None:
    tested = Database("postgresql://u:p@h/d")
    with (
        patch.object(
            Database, "_is_answering", side_effect=[AppException(503, "x"), AppException(503, "x")]
        ) as mock_answering,
        patch.object(Database, "_forget_connection", side_effect=[None]) as mock_forget,
    ):
        result = tested.is_reachable()
    assert result is False
    exp_calls = [call(), call()]
    assert mock_answering.mock_calls == exp_calls
    exp_calls = [call()]
    assert mock_forget.mock_calls == exp_calls


@pytest.mark.database
def test_migrated() -> None:
    """Migration 1 is the first: no previous release exists whose queries
    could break on it. A second run applies nothing."""
    tested = helper_scratch()
    try:
        helper_schema_dropped(tested)
        result = (tested.migrated(), tested.migrated())
        ledger = tested.rows("SELECT version, description FROM schema_migrations ORDER BY version", ())
        tables = tested.rows(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
            (),
        )
    finally:
        tested.closed()
    expected = ((1,), ())
    assert result == expected
    exp_ledger = [{"version": 1, "description": "the owner, the market, the portfolio and the agent's runs"}]
    assert ledger == exp_ledger
    exp_tables = [
        {"tablename": "agent_runs"},
        {"tablename": "agent_steps"},
        {"tablename": "companies"},
        {"tablename": "daily_bars"},
        {"tablename": "history_fetches"},
        {"tablename": "holdings"},
        {"tablename": "llm_connections"},
        {"tablename": "llm_steps"},
        {"tablename": "magic_links"},
        {"tablename": "portfolios"},
        {"tablename": "quotes"},
        {"tablename": "schema_migrations"},
        {"tablename": "sessions"},
        {"tablename": "trades"},
        {"tablename": "universe"},
        {"tablename": "users"},
        {"tablename": "valuations"},
    ]
    assert tables == exp_tables


@pytest.mark.database
def test_closed() -> None:
    tested = helper_scratch()
    connection = tested._connection()
    tested.closed()
    result = (connection.closed, tested._opened)
    expected = (True, [])
    assert result == expected


@pytest.mark.database
def test__is_answering() -> None:
    tested = helper_scratch()
    try:
        result = tested._is_answering()
    finally:
        tested.closed()
    assert result is True


@pytest.mark.database
def test__connection() -> None:
    tested = helper_scratch()
    try:
        first = tested._connection()
        again = tested._connection()
        first.close()
        reopened = tested._connection()
        result = (again is first, reopened is first, reopened.closed, reopened.autocommit, len(tested._opened))
        timeout = tested.row("SHOW statement_timeout", ())
    finally:
        tested.closed()
    expected = (True, False, False, True, 2)
    assert result == expected
    exp_timeout = {"statement_timeout": "15s"}
    assert timeout == exp_timeout


def test__connection__unreachable() -> None:
    tested = Database("postgresql://u:p@h/d")
    with patch.object(psycopg, "connect", side_effect=[psycopg.OperationalError("connection refused")]) as mock_connect:
        with pytest.raises(psycopg.OperationalError) as exc_info:
            tested._connection()
    result = (f"{exc_info.value}", tested._opened)
    expected = ("connection refused", [])
    assert result == expected
    exp_calls = [
        call(
            "postgresql://u:p@h/d",
            autocommit=True,
            row_factory=psycopg.rows.dict_row,
            connect_timeout=5,
            options="-c statement_timeout=15000",
        )
    ]
    assert mock_connect.mock_calls == exp_calls


@pytest.mark.database
def test__forget_connection() -> None:
    tested = helper_scratch()
    tested._forget_connection()
    connection = tested._connection()
    tested._forget_connection()
    result = (connection.closed, tested._opened, tested._local.connection)
    expected = (True, [], None)
    assert result == expected
