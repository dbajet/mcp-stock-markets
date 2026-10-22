from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _MarketConstants:
    # --- the US equity market (NYSE and Nasdaq keep the same hours) --------------
    timezone: str = "America/New_York"
    open_time: str = "09:30"
    close_time: str = "16:00"
    early_close_time: str = "13:00"
    # NYSE holidays, as the exchange publishes them a year or more ahead.
    # TODO 2027-10-01 add the 2028 calendar. Until then a 2028 holiday reads as
    # a trading day, and the broker still refuses: its quote is a day old.
    holidays: tuple[str, ...] = (
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-12-25",
        "2027-01-01",
        "2027-01-18",
        "2027-02-15",
        "2027-03-26",
        "2027-05-31",
        "2027-06-18",
        "2027-07-05",
        "2027-09-06",
        "2027-11-25",
        "2027-12-24",
    )
    # The days the market closes at 13:00.
    early_closes: tuple[str, ...] = (
        "2026-11-27",
        "2026-12-24",
        "2027-11-26",
    )

    # --- quotes -------------------------------------------------------------------
    # A quote fetched this recently is served again rather than fetched anew:
    # the agent asks for the same price several times in one run.
    quote_cache_seconds: int = 60
    # An order is priced on a trade no older than this. Google Finance's
    # regular-session price is minutes fresh while the market is open; an
    # older one means the market did not trade (a holiday the calendar above
    # does not know, a halted stock), and no order is placed on it.
    quote_max_age_seconds: int = 900
    # Prices are kept to four decimals, as the exchanges quote sub-dollar stocks.
    price_places: str = "0.0001"
    money_places: str = "0.01"
    currency: str = "USD"

    # --- Google Finance: the live price ------------------------------------------
    # Followed by "<symbol>:<exchange>"; hl=en keeps the page in the language the parser reads.
    google_finance_url: str = "https://www.google.com/finance/quote/"
    google_finance_query: str = "?hl=en"
    # The page carries its data as JSON in AF_initDataCallback({key, hash, data: …}) calls.
    google_data_marker: str = "AF_initDataCallback({key: '"
    google_data_start: str = "data:"
    # Positions in the quote's array: [id, [symbol, exchange], name, kind,
    # currency, [price, change, change %, …], …, [updated], …, [regular-session time]].
    google_pair_index: int = 1
    google_currency_index: int = 4
    google_price_index: int = 5
    google_updated_index: int = 11
    google_trade_time_index: int = 17
    google_entry_min_length: int = 18
    # Google answers a scripted client without a browser's agent with a consent page.
    browser_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )

    # --- Alpha Vantage: the fallback price, and the daily history -----------------
    alpha_vantage_url: str = "https://www.alphavantage.co/query"
    alpha_vantage_quote_function: str = "GLOBAL_QUOTE"
    alpha_vantage_daily_function: str = "TIME_SERIES_DAILY"
    # Free keys allow one request a second (and 25 a day): requests are spaced.
    alpha_vantage_spacing_seconds: float = 1.2
    # A day's bars are fetched once per symbol per day: ten companies, ten
    # requests, well inside a free key's daily 25.
    history_max_days: int = 100
    history_default_days: int = 20
    # An Alpha Vantage quote carries a date, not a time: it is read as that
    # day's close, so the broker's freshness rule refuses it while the market
    # is open — it informs the agent, it never prices an order.

    # --- the S&P 500 list ------------------------------------------------------------
    sp500_url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    sp500_table_id: str = "constituents"
    # Wikipedia asks scripted clients to say who they are.
    wikipedia_user_agent: str = "mcp-stock-markets/0.1 (a demo of MCP; https://github.com/dbajet/mcp-stock-markets)"
    # The list is read again when the copy stored is older than this.
    sp500_refresh_hours: int = 24
    # Fewer rows than this is a page that changed shape, not an index that shrank.
    sp500_min_companies: int = 450
    # The exchange each symbol's quote link names (nyse.com or nasdaq.com).
    exchange_nyse: str = "NYSE"
    exchange_nasdaq: str = "NASDAQ"
    nasdaq_link_marker: str = "nasdaq.com"
    search_max_results: int = 25

    # --- calls ---------------------------------------------------------------------
    http_timeout_seconds: float = 15.0

    # --- messages --------------------------------------------------------------------
    history_needs_key: str = "Daily history needs an Alpha Vantage key (ALPHA_VANTAGE_API_KEY)."
    sp500_unavailable: str = "The S&P 500 list could not be read."


MarketConstants = _MarketConstants()
