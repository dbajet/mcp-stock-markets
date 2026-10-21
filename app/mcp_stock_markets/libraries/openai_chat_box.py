from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.llm_constants import LlmConstants
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_spec import ToolSpec


class OpenAiChatBox:
    """A chat-completions endpoint in the OpenAI format, which vLLM (a local
    machine) and many hosted providers speak, with the MCP servers' tools as
    its functions: one POST per round of the agent's run, a timeout on each.
    Hand-rolled with urllib: one request shape needs no SDK.

    What leaves the server: the agent's instructions, the portfolio and the
    market data the tools return. Nothing is logged but the failure's kind
    and the model."""

    def agent_reply(
        self,
        connection: LlmConnection,
        system: str,
        task: str,
        exchanges: list[AgentExchange],
        tools: list[ToolSpec],
        max_tokens: int,
        timeout: float,
    ) -> AgentReply:
        request = urllib.request.Request(
            f"{connection.base_url}{LlmConstants.chat_path}",
            data=json.dumps(self.body(connection, system, task, exchanges, tools, max_tokens)).encode(
                Constants.text_encoding
            ),
            headers=self.headers(connection) | {"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read())
            choice = data["choices"][0]
            message = dict(choice["message"])
            calls = tuple(self.call_of(call) for call in message.get("tool_calls") or [])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
            # The provider's detail stays in the log; the run records that it failed.
            logging.getLogger(Constants.logger_name).warning("[LLM] %s from %s", type(error).__name__, connection.model)
            raise AppException(503, LlmConstants.unavailable) from None
        if choice.get("finish_reason") == "length":
            raise AppException(502, LlmConstants.truncated)
        return AgentReply(
            text=str(message.get("content") or ""),
            # vLLM's reasoning parsers return a reasoning model's thinking beside the answer.
            reasoning=str(message.get("reasoning_content") or message.get("reasoning") or ""),
            tool_calls=calls,
            model=str(data.get("model") or connection.model),
            raw=(message,),
        )

    @classmethod
    def call_of(cls, call: dict[str, Any]) -> ToolCall:
        """A function call; arguments that are not a JSON object are kept as
        None, and the agent tells the model so instead of calling the tool."""
        try:
            arguments = json.loads(call["function"]["arguments"] or "{}")
        except ValueError:
            arguments = None
        return ToolCall(
            call_id=str(call["id"]),
            name=str(call["function"]["name"]),
            arguments=arguments if isinstance(arguments, dict) else None,
        )

    def health(self, connection: LlmConnection, timeout: float) -> ConnectionHealth:
        """Green when the endpoint lists the connection's model."""
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{connection.base_url}{LlmConstants.models_path}", headers=self.headers(connection), method="GET"
        )
        is_ok = False
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                listed = {str(model["id"]) for model in json.loads(response.read())["data"]}
            is_ok = connection.model in listed
            detail = LlmConstants.health_ok if is_ok else f"The endpoint does not serve {connection.model}."
        except urllib.error.HTTPError as error:
            refused = error.code in (401, 403)
            detail = LlmConstants.health_key_refused if refused else f"The endpoint answered HTTP {error.code}."
        except (urllib.error.URLError, TimeoutError, OSError):
            detail = LlmConstants.health_unreachable
        except (ValueError, KeyError, TypeError):
            detail = LlmConstants.not_a_model_list
        return ConnectionHealth(
            connection_id=connection.connection_id,
            is_ok=is_ok,
            detail=detail,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    def models(self, connection: LlmConnection, timeout: float) -> list[str]:
        """The models the endpoint serves, by name, to choose from in
        Settings; refused in words a person can act on."""
        request = urllib.request.Request(
            f"{connection.base_url}{LlmConstants.models_path}", headers=self.headers(connection), method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return sorted({str(model["id"]) for model in json.loads(response.read())["data"]})
        except urllib.error.HTTPError as error:
            refused = error.code in (401, 403)
            detail = LlmConstants.health_key_refused if refused else f"The endpoint answered HTTP {error.code}."
        except (urllib.error.URLError, TimeoutError, OSError):
            detail = LlmConstants.health_unreachable
        except (ValueError, KeyError, TypeError):
            detail = LlmConstants.not_a_model_list
        raise AppException(502, detail)

    @classmethod
    def headers(cls, connection: LlmConnection) -> dict[str, str]:
        """A local endpoint may need no key: then no Authorization is sent."""
        return {"Authorization": f"Bearer {connection.api_key}"} if connection.api_key else {}

    @classmethod
    def body(
        cls,
        connection: LlmConnection,
        system: str,
        task: str,
        exchanges: list[AgentExchange],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> dict[str, Any]:
        """Temperature 0: the same portfolio and prices give the same orders,
        so a run can be compared with the next."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": task}]
        for exchange in exchanges:
            messages.extend(exchange.reply.raw)
            messages.extend(
                {"role": "tool", "tool_call_id": answer.call_id, "content": answer.content}
                for answer in exchange.results
            )
        result: dict[str, Any] = {
            "model": connection.model,
            "messages": messages,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool.qualified_name(),
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if connection.disable_thinking:
            result["chat_template_kwargs"] = {"enable_thinking": False}
        return result
