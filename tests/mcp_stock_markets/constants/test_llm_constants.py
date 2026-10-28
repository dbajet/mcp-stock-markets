from __future__ import annotations

import dataclasses

from mcp_stock_markets.constants.llm_constants import LlmConstants
from tests.conftest import is_dataclass


def test_class() -> None:
    tested = LlmConstants
    fields = {
        "chat_path": "str",
        "models_path": "str",
        "health_timeout_seconds": "float",
        "claude_fallback_beta": "str",
        "claude_fallback_models": "tuple[str, ...]",
        "max_name_chars": "int",
        "key_hint_chars": "int",
        "key_hint_min_length": "int",
        "claude_model_page": "int",
        "unavailable": "str",
        "refused": "str",
        "truncated": "str",
        "connection_not_found": "str",
        "connection_url": "str",
        "connection_model": "str",
        "connection_key": "str",
        "health_ok": "str",
        "health_key_refused": "str",
        "health_unreachable": "str",
        "not_a_model_list": "str",
    }
    assert is_dataclass(tested, fields)


def test_values() -> None:
    tested = LlmConstants
    result = dataclasses.asdict(tested)
    expected = {
        "chat_path": "/chat/completions",
        "models_path": "/models",
        "health_timeout_seconds": 8.0,
        "claude_fallback_beta": "server-side-fallback-2026-07-01",
        "claude_fallback_models": ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"),
        "max_name_chars": 80,
        "key_hint_chars": 4,
        "key_hint_min_length": 20,
        "claude_model_page": 1000,
        "unavailable": "The language model did not answer.",
        "refused": "The language model declined this request.",
        "truncated": "The language model's answer was cut at its length limit.",
        "connection_not_found": "This connection does not exist.",
        "connection_url": "An OpenAI-compatible connection needs an http:// or https:// address with a host.",
        "connection_model": "Name the model that trades.",
        "connection_key": "A Claude connection needs an API key.",
        "health_ok": "Connected: the key is accepted and the model is there.",
        "health_key_refused": "The API key was refused.",
        "health_unreachable": "Unreachable: no answer from the address.",
        "not_a_model_list": "The endpoint's answer is not an OpenAI-compatible model list.",
    }
    assert result == expected
