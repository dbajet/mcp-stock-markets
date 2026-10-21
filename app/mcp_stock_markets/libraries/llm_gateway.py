from __future__ import annotations

from mcp_stock_markets.constants.agent_constants import AgentConstants
from mcp_stock_markets.constants.llm_constants import LlmConstants
from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.libraries.llm_connection_store import LlmConnectionStore
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.tool_spec import ToolSpec


class LlmGateway:
    """The agent's model: the connection chosen in Settings, reached through
    the box of its kind, local or cloud. Read at every run, so a change in
    Settings applies to the next one."""

    def __init__(self, store: LlmConnectionStore, openai_box: OpenAiChatBox, claude_box: ClaudeBox) -> None:
        self._store = store
        self._openai_box = openai_box
        self._claude_box = claude_box

    def agent_connection(self) -> LlmConnection:
        """The connection the agent trades with; refused while there is none."""
        connection_id = self._store.routing().agent
        found = None if connection_id is None else self._store.connection(connection_id)
        if found is None:
            raise AppException(503, AgentConstants.no_model)
        return found

    def agent_reply(
        self,
        connection: LlmConnection,
        system: str,
        task: str,
        exchanges: list[AgentExchange],
        tools: list[ToolSpec],
    ) -> AgentReply:
        if connection.kind is LlmKind.CLAUDE:
            return self._claude_box.agent_reply(
                connection,
                system,
                task,
                exchanges,
                tools,
                AgentConstants.claude_max_tokens,
                AgentConstants.claude_effort,
                AgentConstants.turn_timeout_seconds,
            )
        return self._openai_box.agent_reply(
            connection,
            system,
            task,
            exchanges,
            tools,
            AgentConstants.openai_max_tokens,
            AgentConstants.turn_timeout_seconds,
        )

    def health(self, connection: LlmConnection) -> ConnectionHealth:
        if connection.kind is LlmKind.CLAUDE:
            return self._claude_box.health(connection, LlmConstants.health_timeout_seconds)
        return self._openai_box.health(connection, LlmConstants.health_timeout_seconds)

    def models(self, connection: LlmConnection) -> list[str]:
        if connection.kind is LlmKind.CLAUDE:
            return self._claude_box.models(connection, LlmConstants.health_timeout_seconds)
        return self._openai_box.models(connection, LlmConstants.health_timeout_seconds)
