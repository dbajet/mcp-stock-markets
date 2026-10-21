from __future__ import annotations

from typing import Any, NamedTuple


class Company(NamedTuple):
    """A member of the S&P 500 as Wikipedia lists it, with the exchange its
    shares trade on, which Google Finance needs to find its quote."""

    symbol: str
    name: str
    sector: str
    sub_industry: str
    headquarters: str
    exchange: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "sub_industry": self.sub_industry,
            "headquarters": self.headquarters,
            "exchange": self.exchange,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Company:
        return cls(
            symbol=str(data["symbol"]),
            name=str(data["name"]),
            sector=str(data["sector"]),
            sub_industry=str(data["sub_industry"]),
            headquarters=str(data["headquarters"]),
            exchange=str(data["exchange"]),
        )
