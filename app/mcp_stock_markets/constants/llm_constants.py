from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _LlmConstants:
    # --- OpenAI-compatible endpoints (vLLM, hosted providers) --------------------------
    chat_path: str = "/chat/completions"
    models_path: str = "/models"

    # --- calls ----------------------------------------------------------------------
    # A connection's light: an answer within this, or red.
    health_timeout_seconds: float = 8.0
    # A declined request is re-run on a model that accepts it, inside the same
    # call, for the models that offer it; others simply report the refusal.
    claude_fallback_beta: str = "server-side-fallback-2026-07-01"
    claude_fallback_models: tuple[str, ...] = (
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    )

    # --- connections ---------------------------------------------------------------------
    max_name_chars: int = 80
    # A key is told apart, when it is rotated, by its last characters ("…AbCd"),
    # as the providers' consoles show it; a key shorter than the minimum (a local
    # endpoint's placeholder) shows none, since four would be much of it.
    key_hint_chars: int = 4
    key_hint_min_length: int = 20
    # Anthropic's largest page: every model in one request.
    claude_model_page: int = 1000

    # --- messages ---------------------------------------------------------------------
    unavailable: str = "The language model did not answer."
    refused: str = "The language model declined this request."
    truncated: str = "The language model's answer was cut at its length limit."
    connection_not_found: str = "This connection does not exist."
    connection_url: str = "An OpenAI-compatible connection needs an http:// or https:// address with a host."
    connection_model: str = "Name the model that trades."
    connection_key: str = "A Claude connection needs an API key."
    health_ok: str = "Connected: the key is accepted and the model is there."
    health_key_refused: str = "The API key was refused."
    health_unreachable: str = "Unreachable: no answer from the address."
    not_a_model_list: str = "The endpoint's answer is not an OpenAI-compatible model list."


LlmConstants = _LlmConstants()
