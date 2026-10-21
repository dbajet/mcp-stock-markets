from __future__ import annotations

from types import SimpleNamespace

import anthropic
import pytest

from mcp_stock_markets.libraries import claude_box as claude_box_module
from tests.support.fake_anthropic import FakeAnthropic


def test___init__() -> None:
    tested = FakeAnthropic(["a"])
    result = (tested.outcomes, tested.calls, tested.beta is tested, tested.messages is tested, tested.models is tested)
    expected = (["a"], [], True, True, True)
    assert result == expected


def test_installed() -> None:
    tested = FakeAnthropic([])
    original = claude_box_module.anthropic.Anthropic
    with tested.installed() as installed:
        result = (installed is tested, claude_box_module.anthropic.Anthropic is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert claude_box_module.anthropic.Anthropic is exp_restored


def test___call__() -> None:
    tested = FakeAnthropic([])
    result = tested(api_key="k", timeout=5.0, max_retries=0)
    assert result is tested
    expected = [("client", "k", 5.0, 0)]
    assert tested.calls == expected


def test_create() -> None:
    message = FakeAnthropic.message("end_turn", [FakeAnthropic.text("Hi")], "claude-opus-5-5")
    tested = FakeAnthropic([message])
    result = tested.beta.messages.create(model="m", max_tokens=10)
    assert result is message
    exp_calls = [("messages.create", {"model": "m", "max_tokens": 10})]
    assert tested.calls == exp_calls


def test_retrieve() -> None:
    error = FakeAnthropic.status_error(anthropic.NotFoundError, 404)
    tested = FakeAnthropic([FakeAnthropic.model("claude-opus-5-5"), error])
    result = tested.models.retrieve("claude-opus-5-5")
    expected = SimpleNamespace(id="claude-opus-5-5", type="model")
    assert result == expected
    with pytest.raises(anthropic.NotFoundError) as exc_info:
        tested.models.retrieve("claude-nope")
    assert exc_info.value is error
    exp_calls = [("models.retrieve", "claude-opus-5-5"), ("models.retrieve", "claude-nope")]
    assert tested.calls == exp_calls


def test_list() -> None:
    tested = FakeAnthropic([FakeAnthropic.model_page(["claude-opus-5-5"])])
    result = tested.models.list(limit=1000)
    expected = SimpleNamespace(data=[SimpleNamespace(id="claude-opus-5-5", type="model")], has_more=False)
    assert result == expected
    exp_calls = [("models.list", {"limit": 1000})]
    assert tested.calls == exp_calls


def test_next() -> None:
    tested = FakeAnthropic(["first", "second"])
    result = (tested.next(), tested.next())
    expected = ("first", "second")
    assert result == expected


def test_message() -> None:
    tested = FakeAnthropic
    message = tested.message(
        "tool_use",
        [tested.thinking("Check the price."), tested.tool_use("toolu_1", "quotes__quote", {"symbol": "AAPL"})],
        "claude-opus-5-5",
    )
    result = (message.stop_reason, message.model, [block.to_dict() for block in message.content])
    expected = (
        "tool_use",
        "claude-opus-5-5",
        [
            {"signature": "fake-signature", "thinking": "Check the price.", "type": "thinking"},
            {"id": "toolu_1", "input": {"symbol": "AAPL"}, "name": "quotes__quote", "type": "tool_use"},
        ],
    )
    assert result == expected


def test_thinking() -> None:
    tested = FakeAnthropic
    block = tested.thinking("Hmm.")
    result = (block.type, block.thinking, block.signature, block.to_dict())
    expected = (
        "thinking",
        "Hmm.",
        "fake-signature",
        {"signature": "fake-signature", "thinking": "Hmm.", "type": "thinking"},
    )
    assert result == expected


def test_text() -> None:
    tested = FakeAnthropic
    block = tested.text("Done.")
    result = (block.type, block.text, block.to_dict())
    expected = ("text", "Done.", {"type": "text", "text": "Done."})
    assert result == expected


@pytest.mark.parametrize(
    "tool_input",
    [
        pytest.param({"symbol": "AAPL"}, id="an-object"),
        pytest.param("not an object", id="not-an-object"),
    ],
)
def test_tool_use(tool_input: object) -> None:
    tested = FakeAnthropic
    block = tested.tool_use("toolu_1", "broker__buy", tool_input)
    result = (block.type, block.id, block.name, block.input, block.to_dict())
    expected = (
        "tool_use",
        "toolu_1",
        "broker__buy",
        tool_input,
        {"id": "toolu_1", "input": tool_input, "name": "broker__buy", "type": "tool_use"},
    )
    assert result == expected


def test__block() -> None:
    """`to_dict()` answers a new dictionary every time: a caller changing one
    changes neither the block nor the next answer."""
    tested = FakeAnthropic
    block = tested._block({"type": "text", "text": "a"})
    first = block.to_dict()
    first["text"] = "changed"
    result = (block.type, block.text, block.to_dict())
    expected = ("text", "a", {"type": "text", "text": "a"})
    assert result == expected


def test_model() -> None:
    tested = FakeAnthropic
    result = tested.model("claude-haiku-5-5")
    expected = SimpleNamespace(id="claude-haiku-5-5", type="model")
    assert result == expected


def test_model_page() -> None:
    tested = FakeAnthropic
    result = tested.model_page(["claude-opus-5-5", "claude-haiku-5-5"])
    expected = SimpleNamespace(
        data=[
            SimpleNamespace(id="claude-opus-5-5", type="model"),
            SimpleNamespace(id="claude-haiku-5-5", type="model"),
        ],
        has_more=False,
    )
    assert result == expected


@pytest.mark.parametrize(
    "error_type, status",
    [
        pytest.param(anthropic.AuthenticationError, 401, id="authentication"),
        pytest.param(anthropic.NotFoundError, 404, id="not-found"),
        pytest.param(anthropic.InternalServerError, 500, id="server"),
    ],
)
def test_status_error(error_type: type[anthropic.APIStatusError], status: int) -> None:
    tested = FakeAnthropic
    error = tested.status_error(error_type, status)
    result = (type(error), error.status_code, error.message)
    expected = (error_type, status, f"Error code: {status}")
    assert result == expected


@pytest.mark.parametrize(
    "error_type, exp_message",
    [
        pytest.param(anthropic.APIConnectionError, "Connection error.", id="connection"),
        pytest.param(
            anthropic.APITimeoutError,
            "Request timed out or interrupted. This could be due to a network timeout, dropped connection, or "
            "request cancellation. See https://docs.anthropic.com/en/api/errors#long-requests for more details.",
            id="timeout",
        ),
    ],
)
def test_connection_error(error_type: type[anthropic.APIConnectionError], exp_message: str) -> None:
    tested = FakeAnthropic
    error = tested.connection_error(error_type)
    result = (type(error), error.message)
    expected = (error_type, exp_message)
    assert result == expected
