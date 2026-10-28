from __future__ import annotations

import io
import json
import socket
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qsl, urlsplit

from mcp_stock_markets.libraries import web_box as web_box_module


class FakeAlpaca:
    """A hand-written stand-in for Alpaca's market data API
    (`https://data.alpaca.markets/v2/stocks/<symbol>/…`), reached the way
    `WebBox` reaches it: `urllib.request.urlopen(request, timeout=...)`.

    It reproduces what `AlpacaBox` depends on: `/trades/latest?feed=iex`
    answers `{"symbol": "AAPL", "trade": {"t": "2026-10-21T14:58:01.123456789Z",
    "x": "V", "p": 343.99, "s": 100, "c": ["@"], "i": 52983525029461, "z":
    "C"}}`, its moment in nanoseconds and its price a number; `/bars`
    answers `{"bars": [{"t": "2026-10-20T04:00:00Z", "o": …, "h": …, "l": …,
    "c": …, "v": …, "n": …, "vw": …}], "symbol": "AAPL", "next_page_token":
    null}`, each day stamped at its New York midnight, and `"bars": null` for
    a symbol it does not know. Its outcomes are given in order: a dict is a
    JSON answer, bytes are a raw body, an exception is raised as urllib
    raises it. Every request is recorded in `requests`: the URL without its
    query, the query's parameters, the method, the timeout and the headers
    (as urllib capitalizes them), so a test sees where the key pair went."""

    def __init__(self, outcomes: list[dict[str, Any] | bytes | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self) -> Iterator[FakeAlpaca]:
        """In place of urlopen as web_box resolves it, for the block."""
        with patch.object(web_box_module.urllib.request, "urlopen", new=self):
            yield self

    def __call__(
        self,
        url: urllib.request.Request | str,
        data: bytes | None = None,
        timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,  # type: ignore[attr-defined]
        **kwargs: Any,
    ) -> io.BytesIO:
        request = url if isinstance(url, urllib.request.Request) else urllib.request.Request(url, data=data)
        parts = urlsplit(request.full_url)
        self.requests.append(
            (
                f"{parts.scheme}://{parts.netloc}{parts.path}",
                dict(parse_qsl(parts.query)),
                request.get_method(),
                timeout,
                dict(request.header_items()),
            )
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, bytes):
            return io.BytesIO(outcome)
        return io.BytesIO(json.dumps(outcome).encode("utf-8"))

    @classmethod
    def latest_trade(cls, symbol: str, price: float, moment: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "trade": {"t": moment, "x": "V", "p": price, "s": 100, "c": ["@"], "i": 52983525029461, "z": "C"},
        }

    @classmethod
    def bars(cls, symbol: str, days: dict[str, tuple[float, float, float, float, int]]) -> dict[str, Any]:
        """The bars by day, (open, high, low, close, volume), oldest first as Alpaca writes them."""
        return {
            "bars": [
                {
                    "t": f"{day}T04:00:00Z",
                    "o": days[day][0],
                    "h": days[day][1],
                    "l": days[day][2],
                    "c": days[day][3],
                    "v": days[day][4],
                    "n": 632426,
                    "vw": days[day][3],
                }
                for day in sorted(days)
            ],
            "symbol": symbol,
            "next_page_token": None,
        }
