from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from mcp_stock_markets.constants.constants import Constants
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.structures.app_exception import AppException


class WebBox:
    """A page or an API answer read over HTTPS, with a timeout, as text: the
    one road to Google Finance, Wikipedia and Alpha Vantage. Hand-rolled
    with urllib: three GET requests need no HTTP library."""

    def text(self, url: str, headers: dict[str, str]) -> str:
        request = urllib.request.Request(url, headers=headers, method="GET")
        host = urlsplit(url).hostname or url
        try:
            with urllib.request.urlopen(request, timeout=MarketConstants.http_timeout_seconds) as response:
                return bytes(response.read()).decode(Constants.text_encoding, errors="replace")
        except urllib.error.HTTPError as error:
            logging.getLogger(Constants.logger_name).warning("[WEB] %s answered HTTP %s", host, error.code)
            raise AppException(502, f"{host} answered HTTP {error.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logging.getLogger(Constants.logger_name).warning("[WEB] %s unreachable: %s", host, type(error).__name__)
            raise AppException(502, f"{host} did not answer.") from None
