from __future__ import annotations

from typing import Any

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.secret_sealer import SecretSealer
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting


class LlmConnectionStore:
    """The language models set up in Settings, their keys sealed like every
    other secret at rest, and which connection the agent trades with.
    Deleting that connection leaves the agent without one."""

    _COLUMNS = "id, name, kind, base_url, api_key_sealed, model, disable_thinking"
    # The one step of `llm_steps`: the agent's.
    _AGENT = "agent"

    def __init__(self, database: Database, sealer: SecretSealer) -> None:
        self._database = database
        self._sealer = sealer

    def connections(self) -> list[LlmConnection]:
        rows = self._database.rows(f"SELECT {self._COLUMNS} FROM llm_connections ORDER BY id", ())
        return [self.connection_of(row) for row in rows]

    def connection(self, connection_id: int) -> LlmConnection | None:
        row = self._database.row(f"SELECT {self._COLUMNS} FROM llm_connections WHERE id = %s", (connection_id,))
        return None if row is None else self.connection_of(row)

    def created(self, connection: LlmConnection) -> LlmConnection:
        row = self._database.returned(
            f"""INSERT INTO llm_connections (name, kind, base_url, api_key_sealed, model, disable_thinking)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {self._COLUMNS}""",
            (
                connection.name,
                connection.kind.value,
                connection.base_url,
                self._sealer.sealed(connection.api_key),
                connection.model,
                connection.disable_thinking,
            ),
        )
        return self.connection_of(row)

    def updated(self, connection: LlmConnection) -> bool:
        """Whether it existed. The key is replaced as given: the caller keeps
        the stored one by passing it back."""
        return (
            self._database.executed(
                """UPDATE llm_connections SET name = %s, kind = %s, base_url = %s, api_key_sealed = %s,
                       model = %s, disable_thinking = %s
                   WHERE id = %s""",
                (
                    connection.name,
                    connection.kind.value,
                    connection.base_url,
                    self._sealer.sealed(connection.api_key),
                    connection.model,
                    connection.disable_thinking,
                    connection.connection_id,
                ),
            )
            == 1
        )

    def deleted(self, connection_id: int) -> bool:
        return self._database.executed("DELETE FROM llm_connections WHERE id = %s", (connection_id,)) == 1

    def routing(self) -> LlmRouting:
        row = self._database.row("SELECT connection_id FROM llm_steps WHERE step = %s", (self._AGENT,))
        return LlmRouting(agent=None if row is None else row["connection_id"])

    def routed(self, routing: LlmRouting) -> None:
        self._database.executed(
            """INSERT INTO llm_steps (step, connection_id) VALUES (%s, %s)
               ON CONFLICT (step) DO UPDATE SET connection_id = EXCLUDED.connection_id""",
            (self._AGENT, routing.agent),
        )

    def connection_of(self, row: dict[str, Any]) -> LlmConnection:
        return LlmConnection(
            connection_id=int(row["id"]),
            name=str(row["name"]),
            kind=LlmKind(row["kind"]),
            base_url=str(row["base_url"]),
            api_key=self._sealer.opened(bytes(row["api_key_sealed"])),
            model=str(row["model"]),
            disable_thinking=bool(row["disable_thinking"]),
        )
