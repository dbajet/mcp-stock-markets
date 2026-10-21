from __future__ import annotations

from pydantic import BaseModel


class LlmRoutingRequest(BaseModel):
    # The connection the agent trades with; null leaves the agent without one.
    agent: int | None = None
