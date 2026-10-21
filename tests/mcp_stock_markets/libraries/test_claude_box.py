from __future__ import annotations

import logging
from typing import Any
from unittest.mock import call, patch

import anthropic
import pytest

from mcp_stock_markets.constants.llm_kind import LlmKind
from mcp_stock_markets.constants.mcp_server_name import McpServerName
from mcp_stock_markets.libraries.claude_box import ClaudeBox
from mcp_stock_markets.structures.agent_exchange import AgentExchange
from mcp_stock_markets.structures.agent_reply import AgentReply
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.connection_health import ConnectionHealth
from mcp_stock_markets.structures.llm_connection import LlmConnection
from mcp_stock_markets.structures.tool_call import ToolCall
from mcp_stock_markets.structures.tool_result import ToolResult
from mcp_stock_markets.structures.tool_spec import ToolSpec
from tests.support.fake_anthropic import FakeAnthropic


def helper_connection(model: str) -> LlmConnection:
    return LlmConnection(
        connection_id=4,
        name="Claude",
        kind=LlmKind.CLAUDE,
        base_url="",
        api_key="sk-ant-key",
        model=model,
        disable_thinking=True,
    )


def helper_tool() -> ToolSpec:
    return ToolSpec(
        server=McpServerName.QUOTES,
        name="quote",
        description="The latest price of a stock.",
        input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    )


def helper_exchange() -> AgentExchange:
    """A previous round: Claude's answer as it came, and two tool results."""
    return AgentExchange(
        reply=AgentReply(
            text="",
            reasoning="Look first.",
            tool_calls=(ToolCall("toolu_1", "quotes__quote", {"symbol": "AAPL"}),),
            model="claude-opus-5-5",
            raw=(
                {"signature": "s1", "thinking": "Look first.", "type": "thinking"},
                {"id": "toolu_1", "input": {"symbol": "AAPL"}, "name": "quotes__quote", "type": "tool_use"},
                {"id": "toolu_2", "input": {"symbol": "ZZZZ"}, "name": "quotes__quote", "type": "tool_use"},
            ),
        ),
        results=(
            ToolResult(call_id="toolu_1", content="AAPL 230.10 USD", is_error=False),
            ToolResult(call_id="toolu_2", content="Unknown symbol ZZZZ.", is_error=True),
        ),
    )


def helper_request(model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 16000,
        "system": "Trade.",
        "messages": messages,
        "tools": tools,
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "medium"},
    }


def helper_messages() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "Run."},
        {
            "role": "assistant",
            "content": [
                {"signature": "s1", "thinking": "Look first.", "type": "thinking"},
                {"id": "toolu_1", "input": {"symbol": "AAPL"}, "name": "quotes__quote", "type": "tool_use"},
                {"id": "toolu_2", "input": {"symbol": "ZZZZ"}, "name": "quotes__quote", "type": "tool_use"},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "AAPL 230.10 USD", "is_error": False},
                {"type": "tool_result", "tool_use_id": "toolu_2", "content": "Unknown symbol ZZZZ.", "is_error": True},
            ],
        },
    ]


def helper_tool_dict() -> dict[str, Any]:
    return {
        "name": "quotes__quote",
        "description": "The latest price of a stock.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    }


def test_agent_reply() -> None:
    """A model with a server-side fallback gets it; the history goes out as
    Claude wrote it; the thinking summary, the text and the tool calls come
    back apart, and the blocks as they came for the next round."""
    tested = ClaudeBox()
    message = FakeAnthropic.message(
        "tool_use",
        [
            FakeAnthropic.thinking("Prices "),
            FakeAnthropic.thinking("are up."),
            FakeAnthropic.text("Buying "),
            FakeAnthropic.text("two."),
            FakeAnthropic.tool_use("toolu_3", "broker__buy", {"symbol": "AAPL", "quantity": 2}),
            FakeAnthropic.tool_use("toolu_4", "quotes__quote", {"symbol": "MSFT"}),
        ],
        "claude-opus-5-5",
    )
    fake = FakeAnthropic([message])
    with fake.installed():
        result = tested.agent_reply(
            helper_connection("claude-opus-5-5"),
            "Trade.",
            "Run.",
            [helper_exchange()],
            [helper_tool()],
            16000,
            "medium",
            180.0,
        )
    expected = AgentReply(
        text="Buying two.",
        reasoning="Prices are up.",
        tool_calls=(
            ToolCall("toolu_3", "broker__buy", {"symbol": "AAPL", "quantity": 2}),
            ToolCall("toolu_4", "quotes__quote", {"symbol": "MSFT"}),
        ),
        model="claude-opus-5-5",
        raw=(
            {"signature": "fake-signature", "thinking": "Prices ", "type": "thinking"},
            {"signature": "fake-signature", "thinking": "are up.", "type": "thinking"},
            {"type": "text", "text": "Buying "},
            {"type": "text", "text": "two."},
            {"id": "toolu_3", "input": {"symbol": "AAPL", "quantity": 2}, "name": "broker__buy", "type": "tool_use"},
            {"id": "toolu_4", "input": {"symbol": "MSFT"}, "name": "quotes__quote", "type": "tool_use"},
        ),
    )
    assert result == expected
    exp_calls = [
        ("client", "sk-ant-key", 180.0, 0),
        (
            "messages.create",
            helper_request("claude-opus-5-5", helper_messages(), [helper_tool_dict()])
            | {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"},
        ),
    ]
    assert fake.calls == exp_calls


def test_agent_reply__a_model_without_fallback() -> None:
    """The first round: the task alone. The model named is the one that
    answered, which a fallback may have changed."""
    tested = ClaudeBox()
    message = FakeAnthropic.message(
        "end_turn", [FakeAnthropic.thinking(""), FakeAnthropic.text("Nothing to do.")], "claude-haiku-5-5-20261001"
    )
    fake = FakeAnthropic([message])
    with fake.installed():
        result = tested.agent_reply(
            helper_connection("claude-haiku-5-5"), "Trade.", "Run.", [], [helper_tool()], 16000, "medium", 30.0
        )
    expected = AgentReply(
        text="Nothing to do.",
        reasoning="",
        tool_calls=(),
        model="claude-haiku-5-5-20261001",
        raw=(
            {"signature": "fake-signature", "thinking": "", "type": "thinking"},
            {"type": "text", "text": "Nothing to do."},
        ),
    )
    assert result == expected
    exp_calls = [
        ("client", "sk-ant-key", 30.0, 0),
        (
            "messages.create",
            helper_request("claude-haiku-5-5", [{"role": "user", "content": "Run."}], [helper_tool_dict()]),
        ),
    ]
    assert fake.calls == exp_calls


def test_agent_reply__tool_input_that_is_not_an_object() -> None:
    tested = ClaudeBox()
    message = FakeAnthropic.message("tool_use", [FakeAnthropic.tool_use("toolu_5", "broker__buy", "AAPL")], "m")
    fake = FakeAnthropic([message])
    with fake.installed():
        result = tested.agent_reply(helper_connection("m"), "Trade.", "Run.", [], [], 16000, "medium", 30.0)
    expected = AgentReply(
        text="",
        reasoning="",
        tool_calls=(ToolCall("toolu_5", "broker__buy", None),),
        model="m",
        raw=({"id": "toolu_5", "input": "AAPL", "name": "broker__buy", "type": "tool_use"},),
    )
    assert result == expected
    exp_calls = [
        ("client", "sk-ant-key", 30.0, 0),
        ("messages.create", helper_request("m", [{"role": "user", "content": "Run."}], [])),
    ]
    assert fake.calls == exp_calls


@pytest.mark.parametrize(
    "stop_reason, expected",
    [
        pytest.param("refusal", (422, "The language model declined this request."), id="refusal"),
        pytest.param("max_tokens", (502, "The language model's answer was cut at its length limit."), id="max-tokens"),
    ],
)
def test_agent_reply__a_refused_or_cut_answer_is_not_an_answer(stop_reason: str, expected: tuple[int, str]) -> None:
    tested = ClaudeBox()
    fake = FakeAnthropic([FakeAnthropic.message(stop_reason, [FakeAnthropic.text("Partial")], "m")])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.agent_reply(helper_connection("m"), "Trade.", "Run.", [], [], 16000, "medium", 30.0)
    result = (exc_info.value.status_code, exc_info.value.message)
    assert result == expected
    exp_calls = [
        ("client", "sk-ant-key", 30.0, 0),
        ("messages.create", helper_request("m", [{"role": "user", "content": "Run."}], [])),
    ]
    assert fake.calls == exp_calls


@pytest.mark.parametrize(
    "error, exp_kind",
    [
        pytest.param(FakeAnthropic.status_error(anthropic.AuthenticationError, 401), "AuthenticationError", id="key"),
        pytest.param(FakeAnthropic.status_error(anthropic.RateLimitError, 429), "RateLimitError", id="rate-limit"),
        pytest.param(
            FakeAnthropic.status_error(anthropic.InternalServerError, 500), "InternalServerError", id="server"
        ),
        pytest.param(
            FakeAnthropic.connection_error(anthropic.APIConnectionError), "APIConnectionError", id="unreachable"
        ),
        pytest.param(FakeAnthropic.connection_error(anthropic.APITimeoutError), "APITimeoutError", id="timeout"),
    ],
)
def test_agent_reply__a_failure_is_unavailable(
    caplog: pytest.LogCaptureFixture, error: BaseException, exp_kind: str
) -> None:
    tested = ClaudeBox()
    fake = FakeAnthropic([error])
    with fake.installed(), caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        with pytest.raises(AppException) as exc_info:
            tested.agent_reply(helper_connection("claude-haiku-5-5"), "Trade.", "Run.", [], [], 16000, "medium", 30.0)
    result = (exc_info.value.status_code, exc_info.value.message, exc_info.value.__cause__)
    expected = (503, "The language model did not answer.", None)
    assert result == expected
    exp_messages = [f"[LLM] {exp_kind} from claude-haiku-5-5"]
    assert [record.getMessage() for record in caplog.records] == exp_messages
    exp_calls = [
        ("client", "sk-ant-key", 30.0, 0),
        ("messages.create", helper_request("claude-haiku-5-5", [{"role": "user", "content": "Run."}], [])),
    ]
    assert fake.calls == exp_calls


@pytest.mark.parametrize(
    "exchanges, expected",
    [
        pytest.param([], [{"role": "user", "content": "Run."}], id="first-round"),
        pytest.param([helper_exchange()], helper_messages(), id="after-a-round"),
    ],
)
def test_messages(exchanges: list[AgentExchange], expected: list[dict[str, Any]]) -> None:
    tested = ClaudeBox
    result = tested.messages("Run.", exchanges)
    assert result == expected


def test_tool_of() -> None:
    tested = ClaudeBox
    result = tested.tool_of(helper_tool())
    expected = helper_tool_dict()
    assert result == expected


@pytest.mark.parametrize(
    "model, outcomes, expected, exp_retrieved",
    [
        pytest.param(
            "claude-opus-5-5",
            [FakeAnthropic.model("claude-opus-5-5")],
            (True, "Connected: the key is accepted and the model is there."),
            ["claude-opus-5-5"],
            id="model-found",
        ),
        pytest.param(
            "claude-nope",
            [FakeAnthropic.status_error(anthropic.NotFoundError, 404)],
            (False, "Claude has no model claude-nope."),
            ["claude-nope"],
            id="unknown-model",
        ),
        pytest.param(
            "claude-haiku-5-5",
            [FakeAnthropic.status_error(anthropic.AuthenticationError, 401)],
            (False, "The API key was refused."),
            ["claude-haiku-5-5"],
            id="key-refused",
        ),
        pytest.param(
            "claude-haiku-5-5",
            [FakeAnthropic.status_error(anthropic.PermissionDeniedError, 403)],
            (False, "The API key was refused."),
            ["claude-haiku-5-5"],
            id="key-not-allowed",
        ),
        pytest.param(
            "claude-haiku-5-5",
            [FakeAnthropic.connection_error(anthropic.APITimeoutError)],
            (False, "Unreachable: no answer from the address."),
            ["claude-haiku-5-5"],
            id="unreachable",
        ),
        pytest.param(
            "claude-haiku-5-5",
            [FakeAnthropic.status_error(anthropic.InternalServerError, 503)],
            (False, "Claude answered HTTP 503."),
            ["claude-haiku-5-5"],
            id="server-error",
        ),
    ],
)
def test_health(model: str, outcomes: list[Any], expected: tuple[bool, str], exp_retrieved: list[str]) -> None:
    tested = ClaudeBox()
    fake = FakeAnthropic(outcomes)
    with fake.installed(), patch("mcp_stock_markets.libraries.claude_box.time") as mock_time:
        mock_time.perf_counter.side_effect = [10.0, 10.25]
        health = tested.health(helper_connection(model), 8.0)
    result = (health.is_ok, health.detail)
    assert result == expected
    exp_health = ConnectionHealth(4, expected[0], expected[1], 250.0)
    assert health == exp_health
    exp_calls = [("client", "sk-ant-key", 8.0, 0), *[("models.retrieve", model) for model in exp_retrieved]]
    assert fake.calls == exp_calls
    exp_time = [call.perf_counter(), call.perf_counter()]
    assert mock_time.mock_calls == exp_time


def test_models() -> None:
    tested = ClaudeBox()
    fake = FakeAnthropic([FakeAnthropic.model_page(["claude-opus-5-5", "claude-haiku-5-5"])])
    with fake.installed():
        result = tested.models(helper_connection(""), 8.0)
    expected = ["claude-opus-5-5", "claude-haiku-5-5"]
    assert result == expected
    exp_calls = [("client", "sk-ant-key", 8.0, 0), ("models.list", {"limit": 1000})]
    assert fake.calls == exp_calls


@pytest.mark.parametrize(
    "error, exp_message",
    [
        pytest.param(
            FakeAnthropic.status_error(anthropic.AuthenticationError, 401), "The API key was refused.", id="key-refused"
        ),
        pytest.param(
            FakeAnthropic.status_error(anthropic.PermissionDeniedError, 403),
            "The API key was refused.",
            id="key-not-allowed",
        ),
        pytest.param(
            FakeAnthropic.connection_error(anthropic.APITimeoutError),
            "Unreachable: no answer from the address.",
            id="unreachable",
        ),
        pytest.param(
            FakeAnthropic.status_error(anthropic.InternalServerError, 503),
            "Claude answered HTTP 503.",
            id="server-error",
        ),
    ],
)
def test_models__refused(error: BaseException, exp_message: str) -> None:
    tested = ClaudeBox()
    fake = FakeAnthropic([error])
    with fake.installed(), pytest.raises(AppException) as exc_info:
        tested.models(helper_connection(""), 8.0)
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, exp_message)
    assert result == expected
    exp_calls = [("client", "sk-ant-key", 8.0, 0), ("models.list", {"limit": 1000})]
    assert fake.calls == exp_calls
