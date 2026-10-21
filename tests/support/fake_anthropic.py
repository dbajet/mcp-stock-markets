from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import anthropic
import httpx2

from mcp_stock_markets.libraries import claude_box as claude_box_module


class FakeAnthropic:
    """A hand-written stand-in for Anthropic's Python SDK client, as
    `ClaudeBox` uses it: `anthropic.Anthropic(api_key=..., timeout=...,
    max_retries=...)`, then `client.beta.messages.create(**request)`,
    `client.models.retrieve(model)` and `client.models.list(limit=...)`.

    It reproduces the shapes ClaudeBox depends on: a message with a
    `stop_reason` ("end_turn", "tool_use", "refusal", "max_tokens"), the
    `model` that wrote it, and `content` blocks of `type` "thinking" (with
    its `signature`), "text" or "tool_use" (`id`, `name`, `input`), each
    with the SDK model's `to_dict()`, which is what goes back in the next
    request; a thinking block comes before the text and the tool calls, as
    adaptive thinking returns them; a refusal is `stop_reason: "refusal"`
    (HTTP 200, not an error); a model object from `models.retrieve`, or
    `NotFoundError` for an unknown model; a page whose `data` holds model
    objects from `models.list`. Failures are the SDK's own typed errors,
    built by `status_error` and `connection_error`. Outcomes are given in
    order, one per call; every call is recorded in `calls`."""

    _URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[Any, ...]] = []
        # The SDK's namespaces, as attributes of the same object.
        self.beta = self
        self.messages = self
        self.models = self

    @contextmanager
    def installed(self) -> Iterator[FakeAnthropic]:
        """In place of the client class as claude_box resolves it, for the block."""
        with patch.object(claude_box_module.anthropic, "Anthropic", new=self):
            yield self

    def __call__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        **kwargs: Any,
    ) -> FakeAnthropic:
        self.calls.append(("client", api_key, timeout, max_retries))
        return self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(("messages.create", kwargs))
        return self.next()

    def retrieve(self, model_id: str, **kwargs: Any) -> Any:
        self.calls.append(("models.retrieve", model_id))
        return self.next()

    def list(self, **kwargs: Any) -> Any:
        self.calls.append(("models.list", kwargs))
        return self.next()

    def next(self) -> Any:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @classmethod
    def message(cls, stop_reason: str, blocks: list[SimpleNamespace], model: str) -> SimpleNamespace:
        return SimpleNamespace(stop_reason=stop_reason, content=blocks, model=model)

    @classmethod
    def thinking(cls, thinking: str) -> SimpleNamespace:
        """A thinking block; its signature is opaque, and only Claude checks it."""
        return cls._block({"signature": "fake-signature", "thinking": thinking, "type": "thinking"})

    @classmethod
    def text(cls, text: str) -> SimpleNamespace:
        return cls._block({"type": "text", "text": text})

    @classmethod
    def tool_use(cls, call_id: str, name: str, tool_input: Any) -> SimpleNamespace:
        return cls._block({"id": call_id, "input": tool_input, "name": name, "type": "tool_use"})

    @classmethod
    def _block(cls, fields: dict[str, Any]) -> SimpleNamespace:
        """The fields as attributes, and `to_dict()` returning them anew on
        every call, as the SDK's models do."""
        return SimpleNamespace(**fields, to_dict=lambda: dict(fields))

    @classmethod
    def model(cls, model_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=model_id, type="model")

    @classmethod
    def model_page(cls, model_ids: list[str]) -> SimpleNamespace:
        return SimpleNamespace(data=[cls.model(model_id) for model_id in model_ids], has_more=False)

    @classmethod
    def status_error(cls, error_type: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
        response = httpx2.Response(status, request=httpx2.Request("POST", cls._URL))
        return error_type(f"Error code: {status}", response=response, body=None)

    @classmethod
    def connection_error(cls, error_type: type[anthropic.APIConnectionError]) -> anthropic.APIConnectionError:
        return error_type(request=httpx2.Request("POST", cls._URL))
