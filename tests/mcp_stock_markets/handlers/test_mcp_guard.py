from __future__ import annotations

import asyncio
from typing import Any

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_stock_markets.handlers.mcp_guard import McpGuard

REFUSED_BODY = b'{"detail": "This MCP server needs the app\'s bearer token."}'


def helper_app(reached: list[str]) -> ASGIApp:
    """The app behind the guard: it says it was reached, and answers 200."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(scope["type"])
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    return app


def helper_scope(kind: str, headers: list[tuple[bytes, bytes]]) -> Scope:
    return {"type": kind, "method": "POST", "path": "/", "headers": headers}


def helper_called(tested: McpGuard, scope: Scope) -> list[Message]:
    """The messages the guard (or the app behind it) sent for one request."""
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(tested(scope, receive, send))
    return sent


def helper_refusal() -> list[dict[str, Any]]:
    return [
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", b"59"),
            ],
        },
        {"type": "http.response.body", "body": REFUSED_BODY},
    ]


def test___init__() -> None:
    app = helper_app([])
    tested = McpGuard(app, "tok-1")
    result = (tested._app, tested._expected)
    expected = (app, b"Bearer tok-1")
    assert result == expected


def test___call__() -> None:
    reached: list[str] = []
    tested = McpGuard(helper_app(reached), "tok-1")
    result = helper_called(tested, helper_scope("http", [(b"authorization", b"Bearer tok-1")]))
    expected = [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"ok"},
    ]
    assert result == expected
    exp_reached = ["http"]
    assert reached == exp_reached


def test___call____without_the_token_is_refused() -> None:
    reached: list[str] = []
    tested = McpGuard(helper_app(reached), "tok-1")
    result = helper_called(tested, helper_scope("http", [(b"authorization", b"Bearer other")]))
    expected = helper_refusal()
    assert result == expected
    exp_reached: list[str] = []
    assert reached == exp_reached


def test___call____lifespan_passes_without_a_token() -> None:
    """The lifespan carries no headers: the session manager must still start."""
    reached: list[str] = []
    tested = McpGuard(helper_app(reached), "tok-1")
    result = helper_called(tested, {"type": "lifespan"})
    expected: list[Message] = []
    assert result == expected
    exp_reached = ["lifespan"]
    assert reached == exp_reached


@pytest.mark.parametrize(
    "headers, expected",
    [
        pytest.param([(b"authorization", b"Bearer tok-1")], True, id="right_token"),
        pytest.param([(b"Authorization", b"Bearer tok-1")], True, id="header_name_any_case"),
        pytest.param([(b"x-agent-run", b"3"), (b"authorization", b"Bearer tok-1")], True, id="among_other_headers"),
        pytest.param([(b"authorization", b"Bearer tok-2")], False, id="wrong_token"),
        pytest.param([(b"authorization", b"bearer tok-1")], False, id="scheme_case_differs"),
        pytest.param([(b"authorization", b"tok-1")], False, id="no_scheme"),
        pytest.param([(b"authorization", b"Bearer tok-1 ")], False, id="trailing_space"),
        pytest.param([], False, id="no_header"),
        pytest.param(
            [(b"authorization", b"Bearer tok-1"), (b"authorization", b"Bearer tok-2")], False, id="last_header_wins"
        ),
    ],
)
def test_is_allowed(headers: list[tuple[bytes, bytes]], expected: bool) -> None:
    tested = McpGuard(helper_app([]), "tok-1")
    result = tested.is_allowed(helper_scope("http", headers))
    assert result is expected


def test_is_allowed__scope_without_headers() -> None:
    tested = McpGuard(helper_app([]), "tok-1")
    result = tested.is_allowed({"type": "http"})
    assert result is False


def test_refused() -> None:
    tested = McpGuard
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(tested.refused(send))
    expected = helper_refusal()
    assert sent == expected
