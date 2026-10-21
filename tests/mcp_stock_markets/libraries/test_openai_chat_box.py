from __future__ import annotations

import logging
import urllib.error
from typing import Any
from unittest.mock import call, patch

import pytest

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.libraries.openai_chat_box import OpenAiChatBox
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec
from tests.support.fake_openai_chat import FakeOpenAiChat

URL = "https://llm.example.com/v1/chat/completions"
MODELS = "https://llm.example.com/v1/models"


def helper_connection(api_key: str, disable_thinking: bool) -> LlmConnection:
    return LlmConnection(
        connection_id=3,
        name="Local",
        kind=LlmKind.OPENAI,
        base_url="https://llm.example.com/v1",
        api_key=api_key,
        model="good",
        disable_thinking=disable_thinking,
    )


def helper_tool() -> ToolSpec:
    return ToolSpec(
        server=McpServerName.BROKER,
        name="buy",
        description="Buy whole shares.",
        input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
    )


def helper_tool_dict() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "broker__buy",
            "description": "Buy whole shares.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
        },
    }


def helper_exchange() -> AgentExchange:
    """A previous round: the assistant's message as it came, and two tool results."""
    return AgentExchange(
        reply=AgentReply(
            text="",
            reasoning="",
            tool_calls=(ToolCall("call_1", "broker__buy", {"symbol": "AAPL"}),),
            model="good",
            raw=(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "broker__buy", "arguments": '{"symbol": "AAPL"}'},
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "broker__buy", "arguments": '{"symbol": "ZZZZ"}'},
                        },
                    ],
                },
            ),
        ),
        results=(
            ToolResult(call_id="call_1", content="Bought 1 AAPL.", is_error=False),
            ToolResult(call_id="call_2", content="Unknown symbol ZZZZ.", is_error=True),
        ),
    )


def helper_history() -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "Trade."},
        {"role": "user", "content": "Run."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "broker__buy", "arguments": '{"symbol": "AAPL"}'},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "broker__buy", "arguments": '{"symbol": "ZZZZ"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "Bought 1 AAPL."},
        {"role": "tool", "tool_call_id": "call_2", "content": "Unknown symbol ZZZZ."},
    ]


def helper_body(messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int) -> dict[str, Any]:
    return {
        "model": "good",
        "messages": messages,
        "tools": tools,
        "max_tokens": max_tokens,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def helper_first_round() -> list[dict[str, Any]]:
    return [{"role": "system", "content": "Trade."}, {"role": "user", "content": "Run."}]


def test_agent_reply() -> None:
    """The history goes out in the OpenAI format; the tool calls come back
    parsed, the model's reasoning beside its text, and the message as it
    came for the next round."""
    tested = OpenAiChatBox()
    message = FakeOpenAiChat.assistant(
        "Buying.",
        [
            FakeOpenAiChat.tool_call("call_3", "broker__buy", '{"symbol": "MSFT", "quantity": 1}'),
            FakeOpenAiChat.tool_call("call_4", "quotes__quote", ""),
        ],
    ) | {"reasoning_content": "MSFT is cheap."}
    fake = FakeOpenAiChat([FakeOpenAiChat.completion(message, "tool_calls", "good-2026")])
    with fake.installed():
        result = tested.agent_reply(
            helper_connection("the-key", True), "Trade.", "Run.", [helper_exchange()], [helper_tool()], 4000, 180.0
        )
    expected = AgentReply(
        text="Buying.",
        reasoning="MSFT is cheap.",
        tool_calls=(
            ToolCall("call_3", "broker__buy", {"symbol": "MSFT", "quantity": 1}),
            # No arguments at all: an empty object, as a tool without parameters is called.
            ToolCall("call_4", "quotes__quote", {}),
        ),
        model="good-2026",
        raw=(
            {
                "role": "assistant",
                "content": "Buying.",
                "tool_calls": [
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {"name": "broker__buy", "arguments": '{"symbol": "MSFT", "quantity": 1}'},
                    },
                    {"id": "call_4", "type": "function", "function": {"name": "quotes__quote", "arguments": ""}},
                ],
                "reasoning_content": "MSFT is cheap.",
            },
        ),
    )
    assert result == expected
    exp_requests = [(URL, "POST", "Bearer the-key", helper_body(helper_history(), [helper_tool_dict()], 4000), 180.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "answer, expected",
    [
        pytest.param(
            FakeOpenAiChat.completion(FakeOpenAiChat.assistant(None, []), "stop", "good"),
            AgentReply(
                text="", reasoning="", tool_calls=(), model="good", raw=({"role": "assistant", "content": None},)
            ),
            id="null-content",
        ),
        pytest.param(
            FakeOpenAiChat.completion(
                FakeOpenAiChat.assistant("Done.", []) | {"reasoning": "Nothing to buy."}, "stop", "good"
            ),
            AgentReply(
                text="Done.",
                reasoning="Nothing to buy.",
                tool_calls=(),
                model="good",
                raw=({"role": "assistant", "content": "Done.", "reasoning": "Nothing to buy."},),
            ),
            id="vllm-reasoning-field",
        ),
        pytest.param(
            {"choices": [{"message": {"role": "assistant", "content": "Done.", "tool_calls": None}}]},
            AgentReply(
                text="Done.",
                reasoning="",
                tool_calls=(),
                model="good",
                raw=({"role": "assistant", "content": "Done.", "tool_calls": None},),
            ),
            id="no-model-no-finish-reason",
        ),
    ],
)
def test_agent_reply__a_reply_without_tool_calls(answer: dict[str, Any], expected: AgentReply) -> None:
    """A null content reads as empty; a reply that does not name its model
    is the connection's; a local endpoint without a key gets no
    Authorization header."""
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([answer])
    with fake.installed():
        result = tested.agent_reply(helper_connection("", True), "Trade.", "Run.", [], [], 10, 2.0)
    assert result == expected
    exp_requests = [(URL, "POST", None, helper_body(helper_first_round(), [], 10), 2.0)]
    assert fake.requests == exp_requests


def test_agent_reply__a_reply_cut_at_its_length_is_not_an_answer() -> None:
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([FakeOpenAiChat.completion(FakeOpenAiChat.assistant("Buy", []), "length", "good")])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.agent_reply(helper_connection("the-key", True), "Trade.", "Run.", [], [], 10, 2.0)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, "The language model's answer was cut at its length limit.")
    assert result == expected
    exp_requests = [(URL, "POST", "Bearer the-key", helper_body(helper_first_round(), [], 10), 2.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "outcome, exp_kind",
    [
        pytest.param(
            urllib.error.HTTPError(URL, 500, "Server Error", None, None),  # type: ignore[arg-type]
            "HTTPError",
            id="server-error",
        ),
        pytest.param(urllib.error.URLError("no route to host"), "URLError", id="unreachable"),
        pytest.param(TimeoutError("timed out"), "TimeoutError", id="timeout"),
        pytest.param(b"<html>Bad gateway</html>", "JSONDecodeError", id="not-json"),
        pytest.param({"error": "overloaded"}, "KeyError", id="no-choices"),
        pytest.param({"choices": []}, "IndexError", id="empty-choices"),
        pytest.param({"choices": [{"message": None}]}, "TypeError", id="null-message"),
        pytest.param(
            {"choices": [{"message": {"content": "", "tool_calls": [{"id": "c1"}]}}]},
            "KeyError",
            id="call-without-function",
        ),
    ],
)
def test_agent_reply__a_failure_is_unavailable(
    caplog: pytest.LogCaptureFixture,
    outcome: dict[str, Any] | bytes | BaseException,
    exp_kind: str,
) -> None:
    """The run records that the model did not answer; the log says how,
    never with the provider's text."""
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([outcome])
    with fake.installed(), caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        with pytest.raises(AppException) as exc_info:
            tested.agent_reply(helper_connection("the-key", True), "Trade.", "Run.", [], [], 10, 2.0)
    result = (exc_info.value.status_code, exc_info.value.message, exc_info.value.__cause__)
    expected = (503, "The language model did not answer.", None)
    assert result == expected
    exp_messages = [f"[LLM] {exp_kind} from good"]
    assert [record.getMessage() for record in caplog.records] == exp_messages
    exp_requests = [(URL, "POST", "Bearer the-key", helper_body(helper_first_round(), [], 10), 2.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "arguments, expected",
    [
        pytest.param('{"symbol": "AAPL"}', ToolCall("call_1", "broker__buy", {"symbol": "AAPL"}), id="an-object"),
        pytest.param("", ToolCall("call_1", "broker__buy", {}), id="empty"),
        pytest.param(None, ToolCall("call_1", "broker__buy", {}), id="null"),
        pytest.param('{"symbol": "AAPL"', ToolCall("call_1", "broker__buy", None), id="not-json"),
        pytest.param('["AAPL"]', ToolCall("call_1", "broker__buy", None), id="not-an-object"),
    ],
)
def test_call_of(arguments: str | None, expected: ToolCall) -> None:
    tested = OpenAiChatBox
    result = tested.call_of(
        {"id": "call_1", "type": "function", "function": {"name": "broker__buy", "arguments": arguments}}
    )
    assert result == expected


@pytest.mark.parametrize(
    "outcome, expected",
    [
        pytest.param(
            b'{"data": [{"id": "fast"}, {"id": "good"}, {"id": "other"}]}',
            (True, "Connected: the key is accepted and the model is there."),
            id="model-served",
        ),
        pytest.param(b'{"data": [{"id": "fast"}]}', (False, "The endpoint does not serve good."), id="model-missing"),
        pytest.param(
            urllib.error.HTTPError(MODELS, 401, "Unauthorized", None, None),  # type: ignore[arg-type]
            (False, "The API key was refused."),
            id="key-refused",
        ),
        pytest.param(
            urllib.error.HTTPError(MODELS, 502, "Bad Gateway", None, None),  # type: ignore[arg-type]
            (False, "The endpoint answered HTTP 502."),
            id="server-error",
        ),
        pytest.param(
            urllib.error.URLError("timed out"), (False, "Unreachable: no answer from the address."), id="unreachable"
        ),
        pytest.param(TimeoutError("timed out"), (False, "Unreachable: no answer from the address."), id="timeout"),
        pytest.param(
            b"<html>Welcome</html>",
            (False, "The endpoint's answer is not an OpenAI-compatible model list."),
            id="not-a-model-list",
        ),
    ],
)
def test_health(outcome: bytes | BaseException, expected: tuple[bool, str]) -> None:
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([outcome])
    with fake.installed(), patch("mcp_stock_markets.libraries.openai_chat_box.time") as mock_time:
        mock_time.perf_counter.side_effect = [3.0, 3.125]
        health = tested.health(helper_connection("the-key", True), 8.0)
    result = (health.is_ok, health.detail)
    assert result == expected
    exp_health = ConnectionHealth(3, expected[0], expected[1], 125.0)
    assert health == exp_health
    exp_requests = [(MODELS, "GET", "Bearer the-key", {}, 8.0)]
    assert fake.requests == exp_requests
    exp_time = [call.perf_counter(), call.perf_counter()]
    assert mock_time.mock_calls == exp_time


def test_models() -> None:
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([b'{"data": [{"id": "good"}, {"id": "fast"}, {"id": "good"}]}'])
    with fake.installed():
        result = tested.models(helper_connection("", True), 8.0)
    expected = ["fast", "good"]
    assert result == expected
    exp_requests = [(MODELS, "GET", None, {}, 8.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "outcome, exp_message",
    [
        pytest.param(
            urllib.error.HTTPError(MODELS, 403, "Forbidden", None, None),  # type: ignore[arg-type]
            "The API key was refused.",
            id="key-refused",
        ),
        pytest.param(
            urllib.error.HTTPError(MODELS, 404, "Not Found", None, None),  # type: ignore[arg-type]
            "The endpoint answered HTTP 404.",
            id="wrong-address",
        ),
        pytest.param(urllib.error.URLError("refused"), "Unreachable: no answer from the address.", id="unreachable"),
        pytest.param(
            b'{"models": []}', "The endpoint's answer is not an OpenAI-compatible model list.", id="not-a-model-list"
        ),
    ],
)
def test_models__refused(outcome: bytes | BaseException, exp_message: str) -> None:
    tested = OpenAiChatBox()
    fake = FakeOpenAiChat([outcome])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.models(helper_connection("the-key", True), 8.0)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, exp_message)
    assert result == expected
    exp_requests = [(MODELS, "GET", "Bearer the-key", {}, 8.0)]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "api_key, expected",
    [
        pytest.param("k", {"Authorization": "Bearer k"}, id="key"),
        pytest.param("", {}, id="no-key"),
    ],
)
def test_headers(api_key: str, expected: dict[str, str]) -> None:
    tested = OpenAiChatBox
    result = tested.headers(helper_connection(api_key, True))
    assert result == expected


@pytest.mark.parametrize(
    "disable_thinking, expected",
    [
        pytest.param(True, helper_body(helper_history(), [helper_tool_dict()], 10), id="thinking-off"),
        pytest.param(
            False,
            {
                "model": "good",
                "messages": helper_history(),
                "tools": [helper_tool_dict()],
                "max_tokens": 10,
                "temperature": 0,
            },
            id="provider-default",
        ),
    ],
)
def test_body(disable_thinking: bool, expected: dict[str, object]) -> None:
    tested = OpenAiChatBox
    result = tested.body(
        helper_connection("k", disable_thinking), "Trade.", "Run.", [helper_exchange()], [helper_tool()], 10
    )
    assert result == expected
