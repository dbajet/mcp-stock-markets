from __future__ import annotations

from enum import Enum


class LlmKind(Enum):
    # Anthropic's API, through its SDK: a cloud connection.
    CLAUDE = "claude"
    # Any OpenAI-compatible chat-completions endpoint: vLLM on a local machine,
    # or a hosted provider.
    OPENAI = "openai"
