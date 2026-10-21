from __future__ import annotations

from urllib.parse import urlsplit

from mcp_stock_markets.constants.llm_constants import LlmConstants
from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.llm_gateway import LlmGateway
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.llm_routing import LlmRouting


class LlmConnectionCommand:
    """The language models the agent can use, set up in Settings: connections
    (Claude in the cloud, or any OpenAI-compatible endpoint such as a local
    vLLM), which one trades, and each one's light."""

    def __init__(self, store: LlmConnectionStore, gateway: LlmGateway) -> None:
        self._store = store
        self._gateway = gateway

    def connections(self) -> list[LlmConnection]:
        return self._store.connections()

    def routing(self) -> LlmRouting:
        return self._store.routing()

    def created(self, connection: LlmConnection) -> LlmConnection:
        return self._store.created(self.checked(connection, ""))

    def updated(self, connection: LlmConnection) -> LlmConnection:
        """An empty key keeps the stored one: the page never holds a key."""
        stored = self.existing(connection.connection_id)
        result = self.checked(connection, self.kept_key(stored, connection.kind))
        self._store.updated(result)
        return result

    def deleted(self, connection_id: int) -> None:
        if not self._store.deleted(connection_id):
            raise AppException(404, LlmConstants.connection_not_found)

    def routed(self, routing: LlmRouting) -> None:
        if routing.agent is not None:
            self.existing(routing.agent)
        self._store.routed(routing)

    def health(self, connection_id: int) -> ConnectionHealth:
        return self._gateway.health(self.existing(connection_id))

    def models(self, connection_id: int, kind: LlmKind, base_url: str, api_key: str) -> list[str]:
        """What the endpoint offers, before the connection is saved: a new one
        (id 0) with the key typed, an edited one with its stored key when none
        is typed."""
        stored_key = self.kept_key(self.existing(connection_id), kind) if connection_id else ""
        endpoint = LlmConnection(connection_id, "", kind, base_url, api_key, "", False)
        return self._gateway.models(self.endpoint_checked(endpoint, stored_key))

    def existing(self, connection_id: int) -> LlmConnection:
        if (result := self._store.connection(connection_id)) is None:
            raise AppException(404, LlmConstants.connection_not_found)
        return result

    @classmethod
    def checked(cls, connection: LlmConnection, stored_key: str) -> LlmConnection:
        """Trimmed and complete, or refused: a name, a model, and an endpoint
        that can be called."""
        result = cls.endpoint_checked(connection, stored_key)._replace(
            name=connection.name.strip(), model=connection.model.strip()
        )
        if not result.name or len(result.name) > LlmConstants.max_name_chars:
            raise AppException(400, f"Give the connection a name, of at most {LlmConstants.max_name_chars} characters.")
        if not result.model:
            raise AppException(400, LlmConstants.connection_model)
        return result

    @classmethod
    def endpoint_checked(cls, connection: LlmConnection, stored_key: str) -> LlmConnection:
        """A Claude connection needs a key and no address; an OpenAI-compatible
        one an http(s) address with a host (a local vLLM may need no key)."""
        result = connection._replace(
            base_url=connection.base_url.strip().rstrip("/") if connection.kind is LlmKind.OPENAI else "",
            api_key=connection.api_key.strip() or stored_key,
        )
        if result.kind is LlmKind.CLAUDE and not result.api_key:
            raise AppException(400, LlmConstants.connection_key)
        parts = urlsplit(result.base_url)
        if result.kind is LlmKind.OPENAI and (parts.scheme not in ("http", "https") or not parts.hostname):
            raise AppException(400, LlmConstants.connection_url)
        return result

    @classmethod
    def kept_key(cls, stored: LlmConnection, kind: LlmKind) -> str:
        """The stored key, while the kind is unchanged: a Claude key is never
        sent to an address typed in its place."""
        return stored.api_key if stored.kind is kind else ""
