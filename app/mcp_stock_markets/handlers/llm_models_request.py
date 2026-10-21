from __future__ import annotations

from pydantic import BaseModel

from mcp_stock_markets.constants.llm_kind import LlmKind


class LlmModelsRequest(BaseModel):
    # 0 for a connection not saved yet; an edited one's id lets its stored key be used.
    connection_id: int = 0
    kind: LlmKind
    # The OpenAI-compatible endpoint's base, ".../v1"; ignored for Claude.
    base_url: str = ""
    api_key: str = ""
