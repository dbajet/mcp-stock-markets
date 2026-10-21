from __future__ import annotations

from pydantic import BaseModel

from mcp_stock_markets.constants.llm_kind import LlmKind


class LlmConnectionRequest(BaseModel):
    name: str
    kind: LlmKind
    # The OpenAI-compatible endpoint's base, ".../v1"; ignored for Claude.
    base_url: str = ""
    # Empty on an edit: the stored key is kept.
    api_key: str = ""
    model: str
    disable_thinking: bool = True
