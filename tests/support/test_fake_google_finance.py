from __future__ import annotations

import hashlib
import socket
import urllib.error
import urllib.request

import pytest

from mcp_stock_markets.libraries import web_box as web_box_module
from tests.support.fake_google_finance import FakeGoogleFinance

URL = "https://www.google.com/finance/quote/AAPL:NASDAQ?hl=en"


def helper_request() -> urllib.request.Request:
    return urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.8"}, method="GET"
    )


def helper_entry() -> list[object]:
    return FakeGoogleFinance.quote_entry("AAPL", "NASDAQ", "Apple Inc", 343.99, 1792612801)


def test___init__() -> None:
    tested = FakeGoogleFinance(["<html></html>"])
    result = (tested.outcomes, tested.requests)
    expected = (["<html></html>"], [])
    assert result == expected


def test_installed() -> None:
    tested = FakeGoogleFinance([])
    original = web_box_module.urllib.request.urlopen
    with tested.installed() as installed:
        result = (installed is tested, web_box_module.urllib.request.urlopen is tested)
    expected = (True, True)
    assert result == expected
    exp_restored = original
    assert web_box_module.urllib.request.urlopen is exp_restored


def test___call__() -> None:
    entry = helper_entry()
    tested = FakeGoogleFinance([entry, "<html>consent</html>"])
    with tested(helper_request(), timeout=15.0) as first, tested(helper_request(), timeout=5.0) as second:
        result = (first.read().decode("utf-8"), second.read())
    expected = (FakeGoogleFinance.page(entry), b"<html>consent</html>")
    assert result == expected
    exp_requests = [
        (URL, "GET", "Mozilla/5.0", "en-US,en;q=0.8", 15.0),
        (URL, "GET", "Mozilla/5.0", "en-US,en;q=0.8", 5.0),
    ]
    assert tested.requests == exp_requests
    exp_left: list[object] = []
    assert tested.outcomes == exp_left


def test___call____a_url() -> None:
    tested = FakeGoogleFinance(["ok"])
    result = tested(URL).read()
    expected = b"ok"
    assert result == expected
    exp_requests = [(URL, "GET", None, None, socket._GLOBAL_DEFAULT_TIMEOUT)]  # type: ignore[attr-defined]
    assert tested.requests == exp_requests


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(urllib.error.HTTPError(URL, 429, "Too Many Requests", None, None), id="status"),  # type: ignore[arg-type]
        pytest.param(urllib.error.URLError("unreachable"), id="unreachable"),
        pytest.param(TimeoutError("timed out"), id="timeout"),
    ],
)
def test___call____fails_as_urllib_does(error: BaseException) -> None:
    tested = FakeGoogleFinance([error])
    with pytest.raises(type(error)) as exc_info:
        tested(helper_request(), timeout=15.0)
    assert exc_info.value is error
    expected = [(URL, "GET", "Mozilla/5.0", "en-US,en;q=0.8", 15.0)]
    assert tested.requests == expected


@pytest.mark.parametrize(
    "traded, exp_traded",
    [
        pytest.param(1792612801, [1792612801], id="traded"),
        pytest.param(None, None, id="not-traded-yet"),
    ],
)
def test_quote_entry(traded: int | None, exp_traded: list[int] | None) -> None:
    tested = FakeGoogleFinance
    result = tested.quote_entry("AAPL", "NASDAQ", "Apple Inc", 343.99, traded)
    expected = [
        "/m/aapl",
        ["AAPL", "NASDAQ"],
        "Apple Inc",
        0,
        "USD",
        [343.99, 4.48999, 1.3225303, 2, 2, 2],
        None,
        339.5,
        "#666666",
        "US",
        "/m/0k8z",
        [1792623128],
        "America/New_York",
        -14400,
        "/m/aapl",
        None,
        [343.91, -0.07998657, -0.023252588, 2, 3, 3],
        exp_traded,
        [1792622676],
    ]
    assert result == expected


def test_page() -> None:
    tested = FakeGoogleFinance
    result = tested.page(helper_entry())
    expected = "171a122be09ccdab190f232cf70d048f"
    assert hashlib.md5(result.encode()).hexdigest() == expected, result
    # The quote array three levels down in its data block.
    exp_block = (
        'AF_initDataCallback({key: \'ds:2\', hash: \'8\', data:[[[["/m/aapl",["AAPL","NASDAQ"],"Apple Inc",0,'
        '"USD",[343.99,4.48999,1.3225303,2,2,2],null,339.5,"#666666","US","/m/0k8z",[1792623128],'
        '"America/New_York",-14400,"/m/aapl",null,[343.91,-0.07998657,-0.023252588,2,3,3],[1792612801],'
        "[1792622676]]]]], sideChannel: {}});"
    )
    assert exp_block in result
