from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.migration import Migration


class Database:
    """The schema, its migrations, and the connections that run them.

    Raw SQL through psycopg and nothing in between. Each thread of the
    request pool keeps one connection of its own, closed once the thread
    has ended (the pool's threads come and go). Migrations are
    numbered, handwritten and additive: blue and green share this database
    for the length of a deploy, so nothing is renamed or dropped in the
    release that stops using it."""

    _UNAVAILABLE = "The database is unavailable."
    _NOTHING_RETURNED = "The database returned nothing."

    _LEDGER = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""

    def __init__(self, url: str) -> None:
        self._url = url
        # The connection and the open transaction of each thread: requests are
        # served on a pool of threads, and each one's transaction is its own.
        self._local = threading.local()
        # Every connection opened, with the thread it belongs to: a thread
        # that ends leaves its connection behind, closed by the next opening.
        self._opened: list[tuple[threading.Thread, psycopg.Connection[DictRow]]] = []
        self._opened_lock = threading.Lock()

    @classmethod
    def migrations(cls) -> tuple[Migration, ...]:
        """One entry per change, ever, numbered from 1 without a gap. The
        tables arrive with the code that reads them."""
        return (
            Migration(
                version=1,
                description="the owner, the market, the portfolio and the agent's runs",
                statements=(
                    # No password column, not even an empty one. The email
                    # is personal data: sealed, and found through its keyed blind
                    # index, so a dump of this table is not a mailing list.
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id           BIGSERIAL PRIMARY KEY,
                        email_sealed BYTEA NOT NULL,
                        email_hash   TEXT NOT NULL UNIQUE,
                        display_name TEXT NOT NULL,
                        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                        disabled_at  TIMESTAMPTZ NULL
                    )""",
                    # A session is a token the browser holds and a hash the table
                    # holds: signing out deletes the row, and the cookie dies with it.
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        id         BIGSERIAL PRIMARY KEY,
                        user_id    BIGINT NOT NULL REFERENCES users(id),
                        token_hash TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL
                    )""",
                    "CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id)",
                    # A sign-in link: single use, consumed by one atomic UPDATE so
                    # two simultaneous clicks cannot both win.
                    """
                    CREATE TABLE IF NOT EXISTS magic_links (
                        id         BIGSERIAL PRIMARY KEY,
                        user_id    BIGINT NOT NULL REFERENCES users(id),
                        token_hash TEXT NOT NULL UNIQUE,
                        purpose    TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        used_at    TIMESTAMPTZ NULL
                    )""",
                    # Set up in Settings; the key sealed like every secret at rest.
                    """
                    CREATE TABLE IF NOT EXISTS llm_connections (
                        id               BIGSERIAL PRIMARY KEY,
                        name             TEXT NOT NULL,
                        kind             TEXT NOT NULL,
                        base_url         TEXT NOT NULL,
                        api_key_sealed   BYTEA NOT NULL,
                        model            TEXT NOT NULL,
                        disable_thinking BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
                    )""",
                    # Which connection does each step; a deleted connection leaves its step empty.
                    """
                    CREATE TABLE IF NOT EXISTS llm_steps (
                        step          TEXT PRIMARY KEY,
                        connection_id BIGINT NULL REFERENCES llm_connections(id) ON DELETE SET NULL
                    )""",
                    # The S&P 500 as last read. A company that leaves the index is
                    # deleted; a trade keeps its symbol as text, so its history stays.
                    """
                    CREATE TABLE IF NOT EXISTS companies (
                        symbol       TEXT PRIMARY KEY,
                        name         TEXT NOT NULL,
                        sector       TEXT NOT NULL,
                        sub_industry TEXT NOT NULL,
                        headquarters TEXT NOT NULL,
                        exchange     TEXT NOT NULL,
                        refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )""",
                    # The companies the owner lets the agent buy, up to MAX_COMPANIES
                    # (checked by the command: the limit is configuration, not schema).
                    """
                    CREATE TABLE IF NOT EXISTS universe (
                        symbol   TEXT PRIMARY KEY,
                        added_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )""",
                    # Every price read, kept: the latest is the cache, the rest
                    # values the portfolio's past for its chart.
                    """
                    CREATE TABLE IF NOT EXISTS quotes (
                        id         BIGSERIAL PRIMARY KEY,
                        symbol     TEXT NOT NULL,
                        price      NUMERIC(14, 4) NOT NULL CHECK (price > 0),
                        currency   TEXT NOT NULL,
                        as_of      TIMESTAMPTZ NOT NULL,
                        source     TEXT NOT NULL,
                        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )""",
                    "CREATE INDEX IF NOT EXISTS quotes_latest ON quotes (symbol, fetched_at DESC)",
                    # The daily bars (Alpaca's; Alpha Vantage's before 2026-10-28), and
                    # the day each symbol was last fetched: once a day per symbol.
                    """
                    CREATE TABLE IF NOT EXISTS daily_bars (
                        symbol TEXT NOT NULL,
                        day    DATE NOT NULL,
                        open   NUMERIC(14, 4) NOT NULL,
                        high   NUMERIC(14, 4) NOT NULL,
                        low    NUMERIC(14, 4) NOT NULL,
                        close  NUMERIC(14, 4) NOT NULL,
                        volume BIGINT NOT NULL,
                        PRIMARY KEY (symbol, day)
                    )""",
                    """
                    CREATE TABLE IF NOT EXISTS history_fetches (
                        symbol     TEXT PRIMARY KEY,
                        fetched_on DATE NOT NULL
                    )""",
                    # The budget may never be under $0: the database refuses it too,
                    # whatever a bug in the code would write.
                    """
                    CREATE TABLE IF NOT EXISTS portfolios (
                        id              BIGSERIAL PRIMARY KEY,
                        user_id         BIGINT NOT NULL UNIQUE REFERENCES users(id),
                        starting_budget NUMERIC(16, 4) NOT NULL CHECK (starting_budget > 0),
                        cash            NUMERIC(16, 4) NOT NULL CHECK (cash >= 0),
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                    )""",
                    # Whole shares, never short: a holding sold to zero is deleted.
                    """
                    CREATE TABLE IF NOT EXISTS holdings (
                        portfolio_id BIGINT NOT NULL REFERENCES portfolios(id),
                        symbol       TEXT NOT NULL,
                        quantity     INTEGER NOT NULL CHECK (quantity > 0),
                        cost         NUMERIC(16, 4) NOT NULL CHECK (cost >= 0),
                        PRIMARY KEY (portfolio_id, symbol)
                    )""",
                    """
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        id              BIGSERIAL PRIMARY KEY,
                        trigger         TEXT NOT NULL,
                        status          TEXT NOT NULL,
                        started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                        finished_at     TIMESTAMPTZ NULL,
                        connection_name TEXT NOT NULL,
                        model           TEXT NOT NULL,
                        turns           INTEGER NOT NULL DEFAULT 0,
                        summary         TEXT NOT NULL DEFAULT '',
                        error           TEXT NOT NULL DEFAULT ''
                    )""",
                    "CREATE INDEX IF NOT EXISTS agent_runs_started ON agent_runs (started_at DESC)",
                    # The run's transcript: what the model said, each MCP call and its answer.
                    """
                    CREATE TABLE IF NOT EXISTS agent_steps (
                        id         BIGSERIAL PRIMARY KEY,
                        run_id     BIGINT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
                        position   INTEGER NOT NULL,
                        kind       TEXT NOT NULL,
                        server     TEXT NOT NULL,
                        tool       TEXT NOT NULL,
                        arguments  JSONB NULL,
                        content    TEXT NOT NULL,
                        is_error   BOOLEAN NOT NULL,
                        elapsed_ms DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        UNIQUE (run_id, position)
                    )""",
                    # Every virtual transaction, kept forever. The cash after it is
                    # never below zero, as in the portfolio itself.
                    """
                    CREATE TABLE IF NOT EXISTS trades (
                        id           BIGSERIAL PRIMARY KEY,
                        portfolio_id BIGINT NOT NULL REFERENCES portfolios(id),
                        executed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                        symbol       TEXT NOT NULL,
                        side         TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                        quantity     INTEGER NOT NULL CHECK (quantity > 0),
                        price        NUMERIC(14, 4) NOT NULL CHECK (price > 0),
                        amount       NUMERIC(16, 4) NOT NULL CHECK (amount > 0),
                        cash_after   NUMERIC(16, 4) NOT NULL CHECK (cash_after >= 0),
                        quote_source TEXT NOT NULL,
                        quote_as_of  TIMESTAMPTZ NOT NULL,
                        agent_run_id BIGINT NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
                        reason       TEXT NOT NULL
                    )""",
                    "CREATE INDEX IF NOT EXISTS trades_portfolio ON trades (portfolio_id, executed_at DESC)",
                    """
                    CREATE TABLE IF NOT EXISTS valuations (
                        id             BIGSERIAL PRIMARY KEY,
                        portfolio_id   BIGINT NOT NULL REFERENCES portfolios(id),
                        taken_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                        cash           NUMERIC(16, 4) NOT NULL,
                        holdings_value NUMERIC(16, 4) NOT NULL,
                        total_value    NUMERIC(16, 4) NOT NULL
                    )""",
                    "CREATE INDEX IF NOT EXISTS valuations_portfolio ON valuations (portfolio_id, taken_at)",
                ),
            ),
        )

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[DictRow]]:
        """One transaction: committed when the block ends, rolled back when it
        raises. A transaction opened inside another on the same thread is the
        outer one, so a command can make several stores' writes atomic."""
        if (current := getattr(self._local, "transaction", None)) is not None:
            yield current
            return
        try:
            connection = self._connection()
            with connection.transaction():
                self._local.transaction = connection
                try:
                    yield connection
                finally:
                    self._local.transaction = None
        except psycopg.Error as error:
            logging.getLogger(Constants.logger_name).warning("[DATABASE] %s", type(error).__name__)
            raise AppException(503, self._UNAVAILABLE) from error

    def rows(self, sql: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            return [dict(row) for row in connection.execute(sql, parameters).fetchall()]

    def row(self, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        with self.transaction() as connection:
            found = connection.execute(sql, parameters).fetchone()
            return dict(found) if found is not None else None

    def returned(self, sql: str, parameters: tuple[Any, ...]) -> dict[str, Any]:
        """The row an `INSERT … RETURNING` always returns: its absence is a
        broken statement, not a case to handle."""
        result = self.row(sql, parameters)
        if result is None:
            raise AppException(500, self._NOTHING_RETURNED)
        return result

    def executed(self, sql: str, parameters: tuple[Any, ...]) -> int:
        """Rows touched, so a caller can tell an update that found nothing
        from one that worked."""
        with self.transaction() as connection:
            return connection.execute(sql, parameters).rowcount

    @contextmanager
    def held(self, key: int) -> Iterator[bool]:
        """A session-level advisory lock, held for the block, and whether it
        was free: the agent's run and the scheduler's jobs take one so the
        two colors of a deploy never both do the same work. The lock is this
        thread's connection's, so the block stays on one thread."""
        found = self.row("SELECT pg_try_advisory_lock(%s) AS taken", (key,))
        is_taken = found is not None and found["taken"] is True
        try:
            yield is_taken
        finally:
            if is_taken:
                self.row("SELECT pg_advisory_unlock(%s) AS released", (key,))

    def is_reachable(self) -> bool:
        """Whether a `SELECT 1` answers. A connection the server dropped since
        its last use is replaced once: a read is safe to repeat."""
        try:
            return self._is_answering()
        except AppException:
            self._forget_connection()
        try:
            return self._is_answering()
        except AppException:
            return False

    def migrated(self) -> tuple[int, ...]:
        """Bring the schema up to date, and say which versions this call
        applied. Each migration commits with its ledger row, both or neither,
        under an advisory lock so two starting colors never both apply it,
        and under a lock timeout so a busy table fails the start instead of
        queueing every query behind it."""
        result: list[int] = []
        for migration in self.migrations():
            with self.transaction() as connection:
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (Constants.migration_lock_key,))
                connection.execute("SELECT set_config('lock_timeout', %s, true)", (Constants.migration_lock_timeout,))
                connection.execute(self._LEDGER)
                applied = connection.execute(
                    "SELECT version FROM schema_migrations WHERE version = %s", (migration.version,)
                ).fetchone()
                if applied is not None:
                    continue
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (%s, %s)",
                    (migration.version, migration.description),
                )
                result.append(migration.version)
        return tuple(result)

    def closed(self) -> None:
        with self._opened_lock:
            for _, connection in self._opened:
                connection.close()
            self._opened = []

    def _is_answering(self) -> bool:
        found = self.row("SELECT 1 AS one", ())
        return found is not None and found["one"] == 1

    def _connection(self) -> psycopg.Connection[DictRow]:
        """This thread's connection, opened on first use and again after the
        server dropped it. Autocommit, so a transaction is always an explicit
        block that commits or rolls back before the connection is reused."""
        current: psycopg.Connection[DictRow] | None = getattr(self._local, "connection", None)
        if current is not None and not current.closed:
            return current
        result = psycopg.connect(
            self._url,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=Constants.database_connect_timeout_seconds,
            options=f"-c statement_timeout={Constants.database_statement_timeout_ms}",
        )
        self._local.connection = result
        with self._opened_lock:
            self._opened = self._living() + [(threading.current_thread(), result)]
        return result

    def _living(self) -> list[tuple[threading.Thread, psycopg.Connection[DictRow]]]:
        """The connections of the threads still running, once those of the
        threads that ended are closed: nothing else would ever close them.
        Called with the list's lock held."""
        result = [(thread, connection) for thread, connection in self._opened if thread.is_alive()]
        for thread, connection in self._opened:
            if not thread.is_alive():
                connection.close()
        return result

    def _forget_connection(self) -> None:
        current: psycopg.Connection[DictRow] | None = getattr(self._local, "connection", None)
        if current is None:
            return
        current.close()
        with self._opened_lock:
            self._opened = [(thread, connection) for thread, connection in self._opened if connection is not current]
        self._local.connection = None
