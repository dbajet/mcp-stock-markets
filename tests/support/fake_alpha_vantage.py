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


class FakeAlphaVantage:
    """A hand-written stand-in for Alpha Vantage's API
    (`https://www.alphavantage.co/query?function=…&symbol=…&apikey=…`),
    reached the way `WebBox` reaches it: `urllib.request.urlopen(request,
    timeout=...)`.

    It reproduces what `AlphaVantageBox` depends on: GLOBAL_QUOTE answers
    `{"Global Quote": {"01. symbol": …, "05. price": "343.9900", "07. latest
    trading day": "2026-10-21", …}}` (an empty object for an unknown symbol),
    TIME_SERIES_DAILY answers `{"Meta Data": {…}, "Time Series (Daily)":
    {"2026-10-21": {"1. open": …, "5. volume": …}}}` newest day first, every
    value a string; and a refused request is answered with HTTP 200 and a
    JSON note — "Information" (the daily limit), "Note" (the per-minute
    limit) or "Error Message" (a bad call) — instead of data. Its outcomes are
    given in order: a dict is a JSON answer, bytes are a raw body, an
    exception is raised as urllib raises it. Every request is recorded in
    `requests`: the URL without its query, the query's parameters, and the
    timeout."""

    INFORMATION = (
        "We have detected your API key as demo and our standard API rate limit is 25 requests per day. "
        "Please subscribe to any of the premium plans at https://www.alphavantage.co/premium/ "
        "to instantly remove all daily rate limits."
    )
    NOTE = (
        "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute "
        "and 500 calls per day."
    )
    ERROR_MESSAGE = (
        "Invalid API call. Please retry or visit the documentation (https://www.alphavantage.co/documentation/) "
        "for TIME_SERIES_DAILY."
    )

    def __init__(self, outcomes: list[dict[str, Any] | bytes | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self) -> Iterator[FakeAlphaVantage]:
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
            )
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, bytes):
            return io.BytesIO(outcome)
        return io.BytesIO(json.dumps(outcome).encode("utf-8"))

    @classmethod
    def global_quote(cls, symbol: str, price: str, day: str) -> dict[str, Any]:
        return {
            "Global Quote": {
                "01. symbol": symbol,
                "02. open": "339.3600",
                "03. high": "345.2500",
                "04. low": "338.8300",
                "05. price": price,
                "06. volume": "35586943",
                "07. latest trading day": day,
                "08. previous close": "339.5000",
                "09. change": "4.4900",
                "10. change percent": "1.3225%",
            }
        }

    @classmethod
    def daily_series(cls, symbol: str, bars: dict[str, tuple[str, str, str, str, str]]) -> dict[str, Any]:
        """The bars by day, (open, high, low, close, volume), newest first as Alpha Vantage writes them."""
        days = sorted(bars, reverse=True)
        return {
            "Meta Data": {
                "1. Information": "Daily Prices (open, high, low, close) and Volumes",
                "2. Symbol": symbol,
                "3. Last Refreshed": days[0] if days else "",
                "4. Output Size": "Compact",
                "5. Time Zone": "US/Eastern",
            },
            "Time Series (Daily)": {
                day: {
                    "1. open": bars[day][0],
                    "2. high": bars[day][1],
                    "3. low": bars[day][2],
                    "4. close": bars[day][3],
                    "5. volume": bars[day][4],
                }
                for day in days
            },
        }

    @classmethod
    def refusal(cls, note: str) -> dict[str, Any]:
        """A refused request as Alpha Vantage answers it, with HTTP 200:
        "Information", "Note" or "Error Message"."""
        texts = {"Information": cls.INFORMATION, "Note": cls.NOTE, "Error Message": cls.ERROR_MESSAGE}
        return {note: texts[note]}
