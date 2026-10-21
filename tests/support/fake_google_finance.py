from __future__ import annotations

import io
import json
import socket
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from mcp_stock_markets.libraries import web_box as web_box_module


class FakeGoogleFinance:
    """A hand-written stand-in for Google Finance's quote page
    (`https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en`), reached the
    way `WebBox` reaches it: `urllib.request.urlopen(request, timeout=...)`.

    It reproduces what `GoogleFinanceBox` depends on: an HTML page whose data
    is carried in several `AF_initDataCallback({key: 'ds:N', hash: 'H',
    data:[...], sideChannel: {}});` calls, one of which holds the quote array
    three levels down in `data` — `[id, [symbol, exchange], name, 0, currency,
    [price, change, change %, …], null, previous close, colour, country, id,
    [updated], zone, offset, id, null, [after-hours price, …],
    [regular-session trade], [after-hours trade]]` — beside blocks that name
    the same [symbol, exchange] in other shapes (the company's ratios, its
    earnings), as the captured page of 2026-10-21 does. Its outcomes are given
    in order: a list is a quote array, served inside such a page; a string is
    a raw page (a page that changed shape); an exception is raised as urllib
    raises it (`HTTPError` for a status, `URLError` for an unreachable host,
    `TimeoutError`). Every request is recorded in `requests`: URL, method,
    the User-Agent and Accept-Language headers, and the timeout."""

    def __init__(self, outcomes: list[list[Any] | str | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self) -> Iterator[FakeGoogleFinance]:
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
        self.requests.append(
            (
                request.full_url,
                request.get_method(),
                request.get_header("User-agent"),
                request.get_header("Accept-language"),
                timeout,
            )
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, str):
            return io.BytesIO(outcome.encode("utf-8"))
        return io.BytesIO(self.page(outcome).encode("utf-8"))

    @classmethod
    def quote_entry(cls, symbol: str, exchange: str, name: str, price: float, traded: int | None) -> list[Any]:
        """A quote array as the page writes it; `traded` is the regular
        session's last trade (Unix seconds), null before a stock first trades."""
        return [
            f"/m/{symbol.lower()}",
            [symbol, exchange],
            name,
            0,
            "USD",
            [price, 4.48999, 1.3225303, 2, 2, 2],
            None,
            339.5,
            "#666666",
            "US",
            "/m/0k8z",
            [1792623128],
            "America/New_York",
            -14400,
            f"/m/{symbol.lower()}",
            None,
            [343.91, -0.07998657, -0.023252588, 2, 3, 3],
            None if traded is None else [traded],
            [1792622676],
        ]

    @classmethod
    def page(cls, entry: list[Any]) -> str:
        """The quote page around a quote array: the blocks before it name the
        same pair in shapes that are not a quote."""
        pair = entry[1]
        ratios = [None, None, [pair, 0.2619, 0.6321, 0.1061, 15.58, 0.408, 0.4836, 0.1084, 29.97, 218, 300, 1.36]]
        earnings = [
            [[entry[0], pair, entry[2], 2026, 4, None, None, None, None, [{"9": 113357085200}], 1, [1793656800]]]
        ]
        blocks = [("ds:4", "1", ratios), ("ds:7", "2", earnings), ("ds:17", "4", []), ("ds:2", "8", [[[entry]]])]
        scripts = "".join(
            f"<script class=\"{key}\" nonce=\"n0nce\">AF_initDataCallback({{key: '{key}', hash: '{digest}', "
            f"data:{json.dumps(data, separators=(',', ':'))}, sideChannel: {{}}}});</script>"
            for key, digest, data in blocks
        )
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f"<title>{entry[2]} ({pair[0]}) Stock Price &amp; News - Google Finance</title></head>"
            f'<body><div class="YMlKec fxKbKc">${entry[5][0]}</div>{scripts}</body></html>'
        )
