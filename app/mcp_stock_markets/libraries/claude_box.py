from __future__ import annotations

import logging
import time
from typing import Any

import anthropic

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.llm_constants import LlmConstants
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_spec import ToolSpec


class ClaudeBox:
    """Claude, through Anthropic's SDK: one Messages request per round of
    the agent's run, with the MCP servers' tools as Claude's tools.

    Claude thinks before it answers (adaptive thinking, the only mode of
    the current models), so its depth is set by `effort`; the thinking is
    asked for as a summary, which the run's transcript shows. Its answer is
    handed back unchanged in the next request (`AgentReply.raw`): Claude
    reads its own thinking blocks between tool calls, and a block altered
    or dropped breaks that chain.

    A client per call, with the connection's key, the round's timeout and no
    retry: the scheduler runs again later. A declined request (`stop_reason:
    "refusal"`) is re-run on another model inside the same call for the
    models that offer it (`fallbacks: "default"`); one still declined is
    reported as such, never read as an answer."""

    def agent_reply(
        self,
        connection: LlmConnection,
        system: str,
        task: str,
        exchanges: list[AgentExchange],
        tools: list[ToolSpec],
        max_tokens: int,
        effort: str,
        timeout: float,
    ) -> AgentReply:
        client = anthropic.Anthropic(api_key=connection.api_key, timeout=timeout, max_retries=0)
        request: dict[str, Any] = {
            "model": connection.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": self.messages(task, exchanges),
            "tools": [self.tool_of(tool) for tool in tools],
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": effort},
        }
        if connection.model in LlmConstants.claude_fallback_models:
            request |= {"betas": [LlmConstants.claude_fallback_beta], "fallbacks": "default"}
        try:
            response = client.beta.messages.create(**request)
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as error:
            logging.getLogger(Constants.logger_name).warning("[LLM] %s from %s", type(error).__name__, connection.model)
            raise AppException(503, LlmConstants.unavailable) from None
        if response.stop_reason == "refusal":
            raise AppException(422, LlmConstants.refused)
        if response.stop_reason == "max_tokens":
            raise AppException(502, LlmConstants.truncated)
        return AgentReply(
            text="".join(block.text for block in response.content if block.type == "text"),
            reasoning="".join(block.thinking for block in response.content if block.type == "thinking"),
            tool_calls=tuple(
                ToolCall(
                    call_id=block.id,
                    name=block.name,
                    arguments=dict(block.input) if isinstance(block.input, dict) else None,
                )
                for block in response.content
                if block.type == "tool_use"
            ),
            model=response.model,
            raw=tuple(block.to_dict() for block in response.content),
        )

    @classmethod
    def messages(cls, task: str, exchanges: list[AgentExchange]) -> list[dict[str, Any]]:
        """The task, then each round: Claude's answer as it came, and the
        servers' answers as tool results, all of one round in one message."""
        result: list[dict[str, Any]] = [{"role": "user", "content": task}]
        for exchange in exchanges:
            result.append({"role": "assistant", "content": list(exchange.reply.raw)})
            result.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": answer.call_id,
                            "content": answer.content,
                            "is_error": answer.is_error,
                        }
                        for answer in exchange.results
                    ],
                }
            )
        return result

    @classmethod
    def tool_of(cls, tool: ToolSpec) -> dict[str, Any]:
        return {"name": tool.qualified_name(), "description": tool.description, "input_schema": tool.input_schema}

    def health(self, connection: LlmConnection, timeout: float) -> ConnectionHealth:
        """Green when the key is accepted and the model exists."""
        started = time.perf_counter()
        client = anthropic.Anthropic(api_key=connection.api_key, timeout=timeout, max_retries=0)
        detail = LlmConstants.health_ok
        is_ok = True
        try:
            client.models.retrieve(connection.model)
        except anthropic.NotFoundError:
            detail = f"Claude has no model {connection.model}."
            is_ok = False
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            detail = LlmConstants.health_key_refused
            is_ok = False
        except anthropic.APIConnectionError:
            detail = LlmConstants.health_unreachable
            is_ok = False
        except anthropic.APIStatusError as error:
            detail = f"Claude answered HTTP {error.status_code}."
            is_ok = False
        return ConnectionHealth(
            connection_id=connection.connection_id,
            is_ok=is_ok,
            detail=detail,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    def models(self, connection: LlmConnection, timeout: float) -> list[str]:
        """The models the key may use, newest first as Anthropic lists them,
        to choose from in Settings; refused in words a person can act on."""
        client = anthropic.Anthropic(api_key=connection.api_key, timeout=timeout, max_retries=0)
        try:
            # One page: far more than Anthropic lists, so no second request.
            return [model.id for model in client.models.list(limit=LlmConstants.claude_model_page).data]
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            detail = LlmConstants.health_key_refused
        except anthropic.APIConnectionError:
            detail = LlmConstants.health_unreachable
        except anthropic.APIStatusError as error:
            detail = f"Claude answered HTTP {error.status_code}."
        raise AppException(502, detail)
