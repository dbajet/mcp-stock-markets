from __future__ import annotations

from pydantic import BaseModel


class UniverseRequest(BaseModel):
    # The ticker symbol of an S&P 500 company, as the list writes it (BRK.B).
    symbol: str
