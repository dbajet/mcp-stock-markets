from __future__ import annotations

import dataclasses
import os
import typing
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

# The app's schema owner: `Database(url)` and `.migrated()`.
from mcp_stock_markets.libraries.database import Database


def _worker_database_url(url: str, worker: str) -> str:
    """Under pytest-xdist, each worker's own database beside the scratch one,
    made on first use: every database test empties the tables,
    and two workers sharing them would empty each other's."""
    if not url or not worker:
        return url
    parts = urlsplit(url)
    name = f"{parts.path.lstrip('/')}_{worker}"
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as connection:
        if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return urlunsplit(parts._replace(path=f"/{name}"))


# Read once per process, before anything else reads it: a worker's every test,
# helper and application then sees only its own database.
os.environ["TEST_DATABASE_URL"] = _worker_database_url(
    os.environ.get("TEST_DATABASE_URL", ""), os.environ.get("PYTEST_XDIST_WORKER", "")
)
# The module-level `app` is built when its module is imported,
# and its settings read DATABASE_URL: under test, the worker's own database.
# Assigned, never defaulted: xdist's controller loads this file too and its
# workers inherit what it set, so a default would leave every worker on the
# shared database, migrating it at once.
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

# Opened once per process: the app's database, and a plain connection of the
# tests' own to empty and fingerprint it.
_DATABASE: list[Database] = []
_CONNECTION: list[psycopg.Connection[dict[str, Any]]] = []
# The fingerprint of the schema as a fresh migration leaves it.
_PRISTINE: list[str] = []

# Everything a test could have changed about the schema, as one digest: the
# tables and their columns, indexes, constraints and sequences, and which
# migrations are recorded. Rows are not in it; they are emptied regardless.
_SCHEMA_FINGERPRINT = (
    "SELECT md5(concat_ws('|', "
    "(SELECT string_agg(concat_ws(',', table_name, column_name, data_type, is_nullable, column_default), ';' "
    "ORDER BY table_name, column_name) FROM information_schema.columns WHERE table_schema = 'public'), "
    "(SELECT string_agg(indexdef, ';' ORDER BY indexdef) FROM pg_indexes WHERE schemaname = 'public'), "
    "(SELECT string_agg(concat_ws(',', conrelid::regclass::text, conname, pg_get_constraintdef(oid)), ';' "
    "ORDER BY conrelid::regclass::text, conname) FROM pg_constraint WHERE connamespace = 'public'::regnamespace), "
    "(SELECT string_agg(sequencename, ';' ORDER BY sequencename) FROM pg_sequences WHERE schemaname = 'public'), "
    "(SELECT string_agg(version::text, ';' ORDER BY version) FROM schema_migrations)"
    ")) AS digest"
)


def _annotations(tested: Any) -> dict[str, str]:
    """Annotation source text: under `from __future__ import annotations` the
    annotations are strings or forward references, not types."""
    result: dict[str, str] = {}
    for name, value in getattr(tested, "__annotations__", {}).items():
        if isinstance(value, typing.ForwardRef):
            result[name] = value.__forward_arg__
        elif isinstance(value, str):
            result[name] = value
        else:
            result[name] = getattr(value, "__name__", repr(value))
    return result


def is_namedtuple(tested: Any, fields: dict[str, str]) -> bool:
    return issubclass(tested, tuple) and hasattr(tested, "_fields") and _annotations(tested) == fields


def is_dataclass(tested: Any, fields: dict[str, str]) -> bool:
    kind = tested if isinstance(tested, type) else type(tested)
    return dataclasses.is_dataclass(kind) and _annotations(kind) == fields


def _schema_fingerprint(connection: psycopg.Connection[dict[str, Any]]) -> str:
    try:
        row = connection.execute(_SCHEMA_FINGERPRINT).fetchone()
    except psycopg.errors.UndefinedTable:
        # No schema_migrations at all: nothing like the migrated schema.
        return ""
    return "" if row is None else str(row["digest"])


def _rebuilt(connection: psycopg.Connection[dict[str, Any]], database: Database) -> None:
    """Every table, sequence and recorded migration gone, then the migrations
    run as the application runs them at startup."""
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    database.migrated()


def _emptied(connection: psycopg.Connection[dict[str, Any]]) -> None:
    """Every row gone and every sequence back at 1, the recorded migrations
    kept: what a fresh migration leaves, in milliseconds where dropping and
    migrating takes most of a second per database test.
    Replica mode skips the foreign keys' triggers, so no deletion order is
    needed; it needs a superuser, which the scratch container's and CI's
    POSTGRES_USER are."""
    with connection.transaction():
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'schema_migrations'"
        ).fetchall()
        sequences = connection.execute("SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'").fetchall()
        connection.execute("SET LOCAL session_replication_role = replica")
        for table in tables:
            connection.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table["tablename"])))
        for sequence in sequences:
            connection.execute(sql.SQL("ALTER SEQUENCE {} RESTART").format(sql.Identifier(sequence["sequencename"])))


def helper_database() -> Database:
    """The scratch Postgres as a fresh migration leaves it, so every test
    starts from the schema and nothing else: emptied while its schema is the
    migrated one, rebuilt when a test changed it. Fails rather than skips
    without one: a suite green on the machines where it proved
    nothing once cost a rolled-back deploy."""
    if not _DATABASE:
        url = os.environ.get("TEST_DATABASE_URL", "")
        if not url:
            pytest.fail("TEST_DATABASE_URL is not set: the database tests need a real Postgres")
        _DATABASE.append(Database(url))
        _CONNECTION.append(psycopg.connect(url, autocommit=True, connect_timeout=10, row_factory=dict_row))
    result = _DATABASE[0]
    connection = _CONNECTION[0]
    if _PRISTINE and _schema_fingerprint(connection) == _PRISTINE[0]:
        _emptied(connection)
        return result
    _rebuilt(connection, result)
    _PRISTINE[:] = [_schema_fingerprint(connection)]
    return result
