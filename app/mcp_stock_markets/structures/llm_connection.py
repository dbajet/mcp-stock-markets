from __future__ import annotations

from typing import Any, NamedTuple

from mcp_stock_markets.constants.llm_kind import LlmKind


class LlmConnection(NamedTuple):
    """A language model the app can call: Claude through Anthropic's API, or
    any OpenAI-compatible endpoint (a local vLLM, a hosted provider). The key
    is opened here and never leaves the server: `public_dict` says only
    whether there is one."""

    connection_id: int
    name: str
    kind: LlmKind
    # The OpenAI-compatible endpoint's base, ".../v1"; empty for Claude.
    base_url: str
    api_key: str
    model: str
    # vLLM's `chat_template_kwargs.enable_thinking=false`: a reasoning model
    # answers in seconds instead of minutes. Unused by Claude.
    disable_thinking: bool

    def public_dict(self) -> dict[str, Any]:
        """What the browser is shown: everything but the key."""
        return {
            "connection_id": self.connection_id,
            "name": self.name,
            "kind": self.kind.value,
            "base_url": self.base_url,
            "has_key": self.api_key != "",
            "model": self.model,
            "disable_thinking": self.disable_thinking,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "name": self.name,
            "kind": self.kind.value,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "disable_thinking": self.disable_thinking,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LlmConnection:
        return cls(
            connection_id=int(data["connection_id"]),
            name=str(data["name"]),
            kind=LlmKind(data["kind"]),
            base_url=str(data["base_url"]),
            api_key=str(data["api_key"]),
            model=str(data["model"]),
            disable_thinking=bool(data["disable_thinking"]),
        )
