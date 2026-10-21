from __future__ import annotations

from enum import Enum


class QuoteSource(Enum):
    # The page's live regular-session price, with the time of its trade.
    GOOGLE_FINANCE = "google_finance"
    # The fallback: GLOBAL_QUOTE, the latest trading day's price, dated not timed.
    ALPHA_VANTAGE = "alpha_vantage"
