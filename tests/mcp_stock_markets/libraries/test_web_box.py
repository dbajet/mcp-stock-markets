from __future__ import annotations

import logging
import urllib.error

import pytest

from mcp_stock_markets.libraries.web_box import WebBox
from mcp_stock_markets.structures.app_exception import AppException
from tests.support.fake_wikipedia import FakeWikipedia

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def test_text() -> None:
    tested = WebBox()
    fake = FakeWikipedia(["<p>S&amp;P 500 — 503 companies</p>", b"caf\xc3\xa9 \xff"])
    with fake.installed():
        result = (
            tested.text(URL, {"User-Agent": "mcp-stock-markets/0.1"}),
            tested.text("https://www.alphavantage.co/query?function=GLOBAL_QUOTE", {}),
        )
    # Read as UTF-8; a byte that is not UTF-8 is replaced, never fatal.
    expected = ("<p>S&amp;P 500 — 503 companies</p>", "café �")
    assert result == expected
    exp_requests = [
        (URL, "GET", "mcp-stock-markets/0.1", 15.0),
        ("https://www.alphavantage.co/query?function=GLOBAL_QUOTE", "GET", None, 15.0),
    ]
    assert fake.requests == exp_requests


@pytest.mark.parametrize(
    "url, error, exp_message, exp_log",
    [
        pytest.param(
            URL,
            urllib.error.HTTPError(URL, 403, "Forbidden", None, None),  # type: ignore[arg-type]
            "en.wikipedia.org answered HTTP 403.",
            "[WEB] en.wikipedia.org answered HTTP 403",
            id="status",
        ),
        pytest.param(
            URL,
            urllib.error.URLError("no route to host"),
            "en.wikipedia.org did not answer.",
            "[WEB] en.wikipedia.org unreachable: URLError",
            id="unreachable",
        ),
        pytest.param(
            URL,
            TimeoutError("timed out"),
            "en.wikipedia.org did not answer.",
            "[WEB] en.wikipedia.org unreachable: TimeoutError",
            id="timeout",
        ),
        pytest.param(
            URL,
            ConnectionResetError("reset by peer"),
            "en.wikipedia.org did not answer.",
            "[WEB] en.wikipedia.org unreachable: ConnectionResetError",
            id="connection-reset",
        ),
        pytest.param(
            "file:relative/page.html",
            urllib.error.URLError("no host"),
            "file:relative/page.html did not answer.",
            "[WEB] file:relative/page.html unreachable: URLError",
            id="a-url-without-a-host-names-itself",
        ),
    ],
)
def test_text__a_failure_is_a_bad_gateway(
    caplog: pytest.LogCaptureFixture, url: str, error: BaseException, exp_message: str, exp_log: str
) -> None:
    tested = WebBox()
    fake = FakeWikipedia([error])
    with fake.installed(), caplog.at_level(logging.WARNING, logger="mcp_stock_markets"):
        with pytest.raises(AppException) as exc_info:
            tested.text(url, {})
    result = (exc_info.value.status_code, exc_info.value.message)
    expected = (502, exp_message)
    assert result == expected
    exp_logs = [exp_log]
    assert [record.getMessage() for record in caplog.records] == exp_logs
    exp_requests = [(url, "GET", None, 15.0)]
    assert fake.requests == exp_requests
