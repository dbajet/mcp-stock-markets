from __future__ import annotations

import pytest

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting
from tests.conftest import helper_database

KEY = "Zm9yLXRlc3RzLW9ubHktZm9yLXRlc3RzLW9ubHktMzI="


def helper_local() -> LlmConnection:
    return LlmConnection(0, "Local", LlmKind.OPENAI, "https://llm.example.com/v1", "local-key", "local-model", True)


def helper_claude() -> LlmConnection:
    return LlmConnection(0, "Claude", LlmKind.CLAUDE, "", "sk-ant", "claude-opus-5-5", False)


def helper_store() -> tuple[Database, LlmConnectionStore]:
    database = helper_database()
    return database, LlmConnectionStore(database, SecretSealer(KEY))


def test___init__() -> None:
    database = Database("postgresql://u:p@h/d")
    sealer = SecretSealer(KEY)
    tested = LlmConnectionStore(database, sealer)
    result = (tested._database is database, tested._sealer is sealer)
    expected = (True, True)
    assert result == expected


@pytest.mark.database
def test_connections() -> None:
    _, tested = helper_store()
    before = tested.connections()
    tested.created(helper_local())
    tested.created(helper_claude())
    result = (before, tested.connections())
    expected = ([], [helper_local()._replace(connection_id=1), helper_claude()._replace(connection_id=2)])
    assert result == expected


@pytest.mark.database
def test_connection() -> None:
    _, tested = helper_store()
    tested.created(helper_local())
    result = (tested.connection(1), tested.connection(2))
    expected = (helper_local()._replace(connection_id=1), None)
    assert result == expected


@pytest.mark.database
def test_created() -> None:
    """The key is sealed at rest: only the data key opens it."""
    database, tested = helper_store()
    result = tested.created(helper_claude())
    expected = helper_claude()._replace(connection_id=1)
    assert result == expected
    stored = database.row("SELECT api_key_sealed, model FROM llm_connections WHERE id = 1", ())
    assert stored is not None
    exp_stored = ("sk-ant", "claude-opus-5-5")
    opened = (SecretSealer(KEY).opened(bytes(stored["api_key_sealed"])), stored["model"])
    assert opened == exp_stored


@pytest.mark.database
def test_updated() -> None:
    _, tested = helper_store()
    tested.created(helper_local())
    changed = helper_local()._replace(
        connection_id=1, name="Local GPU", api_key="new-key", model="bigger-model", disable_thinking=False
    )
    result = (tested.updated(changed), tested.updated(changed._replace(connection_id=7)), tested.connection(1))
    expected = (True, False, changed)
    assert result == expected


@pytest.mark.database
def test_deleted() -> None:
    """Deleting the agent's connection leaves the agent without one."""
    _, tested = helper_store()
    tested.created(helper_local())
    tested.created(helper_claude())
    tested.routed(LlmRouting(agent=2))
    result = (tested.deleted(2), tested.deleted(2), tested.routing())
    expected = (True, False, LlmRouting(agent=None))
    assert result == expected


@pytest.mark.database
def test_routing() -> None:
    _, tested = helper_store()
    tested.created(helper_local())
    before = tested.routing()
    tested.routed(LlmRouting(agent=1))
    result = (before, tested.routing())
    expected = (LlmRouting(None), LlmRouting(1))
    assert result == expected


@pytest.mark.database
def test_routed() -> None:
    """Set again, the choice is replaced, not added."""
    database, tested = helper_store()
    tested.created(helper_local())
    tested.created(helper_claude())
    tested.routed(LlmRouting(agent=1))
    tested.routed(LlmRouting(agent=2))
    result = database.rows("SELECT step, connection_id FROM llm_steps ORDER BY step", ())
    expected = [{"step": "agent", "connection_id": 2}]
    assert result == expected


def test_connection_of() -> None:
    sealer = SecretSealer(KEY)
    tested = LlmConnectionStore(Database("postgresql://u:p@h/d"), sealer)
    result = tested.connection_of(
        {
            "id": "5",
            "name": "Claude",
            "kind": "claude",
            "base_url": "",
            "api_key_sealed": memoryview(sealer.sealed("sk-ant")),
            "model": "claude-opus-5-5",
            "disable_thinking": False,
        }
    )
    expected = helper_claude()._replace(connection_id=5)
    assert result == expected
