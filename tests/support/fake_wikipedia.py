from __future__ import annotations

import io
import socket
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from mcp_stock_markets.libraries import web_box as web_box_module


class FakeWikipedia:
    """A hand-written stand-in for Wikipedia's "List of S&P 500 companies"
    page (`https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`),
    reached the way `WebBox` reaches it: `urllib.request.urlopen(request,
    timeout=...)`.

    It reproduces what `WikipediaBox` depends on, as the page of 2026-10-21
    has it: a `<table id="constituents">` whose header row is Symbol,
    Security, GICS Sector, GICS Sub-Industry, Headquarters Location, Date
    added, CIK, Founded (with links inside some header cells), whose rows'
    first cell links to the stock's page on nyse.com or nasdaq.com, and whose
    cells hold links and text mixed; followed by a second table (the index's
    changes) that is not the list. Its outcomes are given in order: a string
    is a page, bytes are a raw body, an exception is raised as urllib raises
    it. Every request is recorded in `requests`: URL, method, the User-Agent
    header and the timeout."""

    _FIRST = (
        ("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul, Minnesota", "NYSE"),
        ("AOS", "A. O. Smith", "Industrials", "Building Products", "Milwaukee, Wisconsin", "NYSE"),
        ("ABT", "Abbott Laboratories", "Health Care", "Health Care Equipment", "North Chicago, Illinois", "NYSE"),
        ("ADBE", "Adobe Inc.", "Information Technology", "Application Software", "San Jose, California", "NASDAQ"),
        ("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha, Nebraska", "NYSE"),
    )

    def __init__(self, outcomes: list[str | bytes | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[Any, ...]] = []

    @contextmanager
    def installed(self) -> Iterator[FakeWikipedia]:
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
        self.requests.append((request.full_url, request.get_method(), request.get_header("User-agent"), timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, bytes):
            return io.BytesIO(outcome)
        return io.BytesIO(outcome.encode("utf-8"))

    @classmethod
    def members(cls, count: int) -> list[tuple[str, str, str, str, str, str]]:
        """`count` companies (symbol, name, sector, sub-industry,
        headquarters, exchange): five real ones first, then generated ones,
        every third of them on Nasdaq."""
        generated = [
            (
                f"Z{index:03d}",
                f"Company {index}",
                "Utilities",
                "Electric Utilities",
                f"City {index}, Ohio",
                "NASDAQ" if index % 3 == 0 else "NYSE",
            )
            for index in range(max(count - len(cls._FIRST), 0))
        ]
        return [*cls._FIRST, *generated][:count]

    @classmethod
    def page(cls, members: list[tuple[str, str, str, str, str, str]]) -> str:
        """The list's page: the constituents table of these members, then the changes table."""
        rows = "".join(cls._row(index, member) for index, member in enumerate(members))
        return (
            '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>List of S&amp;P 500 companies - Wikipedia</title>'
            '</head><body><p>The <a href="https://en.wikipedia.org/wiki/S%26P_500">S&amp;P 500</a> is a stock '
            "market index.</p>"
            '<table class="wikitable sortable mw-collapsible sticky-header" id="constituents">\n<tbody><tr>\n'
            '<th><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/Ticker_symbol">Symbol</a></th>\n'
            '<th>Security</th><th><a rel="mw:WikiLink" '
            'href="https://en.wikipedia.org/wiki/Global_Industry_Classification_Standard">GICS</a> Sector</th>'
            "<th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date added</th>"
            '<th><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/Central_Index_Key">CIK</a></th>'
            f"<th>Founded</th></tr>\n{rows}</tbody></table>\n"
            '<h2 id="Selected_changes">Selected changes to the list of S&amp;P 500 components</h2>'
            '<table class="wikitable sortable" id="changes"><tbody>'
            "<tr><th>Effective Date</th><th>Added</th><th>Removed</th><th>Reason</th></tr>"
            '<tr><td>2026-09-22</td><td><a href="https://www.nasdaq.com/market-activity/stocks/new">NEW</a></td>'
            "<td>OLD</td><td>Market capitalization change.</td></tr>"
            "</tbody></table></body></html>"
        )

    @classmethod
    def _row(cls, index: int, member: tuple[str, str, str, str, str, str]) -> str:
        symbol, name, sector, sub_industry, headquarters, exchange = member
        link = (
            f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}"
            if exchange == "NASDAQ"
            else f"https://www.nyse.com/quote/XNYS:{symbol}"
        )
        city, _, state = headquarters.partition(", ")
        return (
            f'<tr>\n<td><a rel="mw:ExtLink nofollow" href="{link}" class="external text">{symbol}</a></td>\n'
            f'<td><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/{name.replace(" ", "_")}">{name}</a></td>\n'
            f"<td>{sector}</td>\n<td>{sub_industry}</td>\n"
            f'<td><a rel="mw:WikiLink" href="https://en.wikipedia.org/wiki/{city.replace(" ", "_")}">{city}</a>, '
            f"{state}</td>\n<td>2001-08-07</td>\n<td>{1000000 + index:010d}</td>\n<td>1927</td></tr>\n"
        )
