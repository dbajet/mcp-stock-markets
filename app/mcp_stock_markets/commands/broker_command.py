from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from mcp_stock_markets.commands.quote_command import QuoteCommand
from mcp_stock_markets.constants.broker_constants import BrokerConstants
from mcp_stock_markets.constants.market_constants import MarketConstants
from mcp_stock_markets.constants.trade_side import TradeSide
from mcp_stock_markets.libraries.company_store import CompanyStore
from mcp_stock_markets.libraries.database import Database
from mcp_stock_markets.libraries.portfolio_store import PortfolioStore
from mcp_stock_markets.structures.app_exception import AppException
from mcp_stock_markets.structures.holding import Holding
from mcp_stock_markets.structures.portfolio import Portfolio
from mcp_stock_markets.structures.portfolio_view import PortfolioView
from mcp_stock_markets.structures.position import Position
from mcp_stock_markets.structures.quote import Quote
from mcp_stock_markets.structures.settings import Settings
from mcp_stock_markets.structures.trade import Trade
from mcp_stock_markets.structures.user_account import UserAccount
from mcp_stock_markets.structures.valuation import Valuation


class BrokerCommand:
    """The virtual broker: the portfolio, and the orders that change it.

    Every rule is enforced here, whoever asks — the agent through the MCP
    broker server, or anything else: whole shares; buy only in the agent's
    market, sell only what is held; only while the market is open, at a
    price from a trade at most 15 minutes old, fetched by the broker itself
    (an order names no price); and the cash never below zero, which the
    database refuses too. The order's writes are one transaction, under a
    lock on the portfolio's row, so two orders never spend the same cash."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        store: PortfolioStore,
        companies: CompanyStore,
        quotes: QuoteCommand,
    ) -> None:
        self._starting_budget = settings.starting_budget
        self._database = database
        self._store = store
        self._companies = companies
        self._quotes = quotes

    def opened(self, owner: UserAccount) -> Portfolio:
        """The owner's portfolio, made with the starting budget at the first start."""
        return self._store.opened(owner.user_id, self._starting_budget)

    def portfolio_for(self, user_id: int) -> Portfolio:
        """The portfolio of the signed-in user, never another's."""
        if (result := self._store.for_user(user_id)) is None:
            raise AppException(404, BrokerConstants.no_portfolio)
        return result

    def owner_portfolio(self) -> Portfolio:
        """The portfolio the broker serves the agent: the one owner's."""
        if (result := self._store.of_owner()) is None:
            raise AppException(404, BrokerConstants.no_portfolio)
        return result

    def view(self, portfolio: Portfolio, now: datetime) -> PortfolioView:
        holdings = self._store.holdings(portfolio.portfolio_id)
        positions = self.positions(holdings, now)
        holdings_value = sum((position.value for position in positions), Decimal(0)).quantize(
            Decimal(MarketConstants.price_places)
        )
        return PortfolioView(
            portfolio=portfolio,
            positions=positions,
            holdings_value=holdings_value,
            total_value=portfolio.cash + holdings_value,
            universe=tuple(self._companies.universe()),
        )

    def positions(self, holdings: list[Holding], now: datetime) -> tuple[Position, ...]:
        """Every holding priced at once, in the holdings' order: a slow Google
        costs one lookup's wait, not one per stock."""
        if not holdings:
            return ()
        with ThreadPoolExecutor(min(len(holdings), BrokerConstants.pricing_threads)) as pool:
            return tuple(pool.map(lambda holding: self.position(holding, now), holdings))

    def position(self, holding: Holding, now: datetime) -> Position:
        """At the latest price: read now, or the last one read when reading
        fails; at its cost when there has never been one."""
        try:
            quote: Quote | None = self._quotes.quote(holding.symbol, now)
        except AppException:
            quote = self._quotes.latest(holding.symbol)
        value = holding.cost if quote is None else quote.price * holding.quantity
        return Position(holding=holding, quote=quote, value=value)

    def bought(self, symbol: str, quantity: int, reason: str, run_id: int | None, now: datetime) -> Trade:
        return self.ordered(TradeSide.BUY, symbol, quantity, reason, run_id, now)

    def sold(self, symbol: str, quantity: int, reason: str, run_id: int | None, now: datetime) -> Trade:
        return self.ordered(TradeSide.SELL, symbol, quantity, reason, run_id, now)

    def ordered(
        self,
        side: TradeSide,
        symbol: str,
        quantity: int,
        reason: str,
        run_id: int | None,
        now: datetime,
    ) -> Trade:
        wanted = symbol.strip().upper()
        self.checked_order(quantity, reason, now)
        portfolio = self.owner_portfolio()
        if side is TradeSide.BUY and wanted not in (universe := self._companies.universe()):
            listed = ", ".join(universe) or "none"
            raise AppException(403, f"{wanted} is not in the agent's market: only {listed} may be bought.")
        if side is TradeSide.SELL:
            self.held(self._store.holding(portfolio.portfolio_id, wanted), wanted, quantity)
        # The price is read before the transaction: no lock waits on Google.
        quote = self._quotes.quote(wanted, now)
        if quote.age_seconds(now) > MarketConstants.quote_max_age_seconds:
            raise AppException(
                409, f"The latest trade of {wanted} is from {quote.as_of.isoformat()}: too old to price an order."
            )
        amount = (quote.price * quantity).quantize(Decimal(MarketConstants.price_places))
        with self._database.transaction():
            locked = self._store.locked(portfolio.portfolio_id)
            holding = self._store.holding(portfolio.portfolio_id, wanted)
            after: Holding | None
            if side is TradeSide.BUY:
                if amount > locked.cash:
                    raise AppException(
                        409,
                        f"{quantity} {wanted} at {quote.price} costs {amount}, more than the {locked.cash} of cash.",
                    )
                after = self.bought_holding(holding, wanted, quantity, amount)
            else:
                after = self.sold_holding(self.held(holding, wanted, quantity), quantity)
            return self._store.recorded(locked, side, quantity, quote, amount, after, run_id, reason.strip())

    def checked_order(self, quantity: int, reason: str, now: datetime) -> None:
        if not 1 <= quantity <= BrokerConstants.max_order_quantity:
            raise AppException(400, f"Order a whole number of shares, from 1 to {BrokerConstants.max_order_quantity}.")
        if len(reason.strip()) > BrokerConstants.max_reason_chars:
            raise AppException(400, f"Give a reason of at most {BrokerConstants.max_reason_chars} characters.")
        if not (status := self._quotes.market(now)).is_open:
            raise AppException(
                409, f"The US market is closed: orders are taken again from {status.next_open.isoformat()}."
            )

    @classmethod
    def held(cls, holding: Holding | None, symbol: str, quantity: int) -> Holding:
        if holding is None:
            raise AppException(409, f"The portfolio holds no {symbol}.")
        if holding.quantity < quantity:
            raise AppException(
                409, f"The portfolio holds {holding.quantity} {symbol}, fewer than the {quantity} to sell."
            )
        return holding

    @classmethod
    def bought_holding(cls, holding: Holding | None, symbol: str, quantity: int, amount: Decimal) -> Holding:
        if holding is None:
            return Holding(symbol=symbol, quantity=quantity, cost=amount)
        return Holding(symbol=symbol, quantity=holding.quantity + quantity, cost=holding.cost + amount)

    @classmethod
    def sold_holding(cls, holding: Holding, quantity: int) -> Holding | None:
        """What is left, carrying its share of the cost; None when nothing is."""
        remaining = holding.quantity - quantity
        if remaining == 0:
            return None
        cost = (holding.cost * remaining / holding.quantity).quantize(
            Decimal(MarketConstants.price_places), rounding=ROUND_HALF_EVEN
        )
        return Holding(symbol=holding.symbol, quantity=remaining, cost=cost)

    def trades(self, portfolio: Portfolio, limit: int) -> list[Trade]:
        return self._store.trades(portfolio.portfolio_id, max(1, min(limit, BrokerConstants.max_transactions_page)))

    def valuations(self, portfolio: Portfolio) -> list[Valuation]:
        return self._store.valuations(portfolio.portfolio_id, BrokerConstants.valuations_page)

    def valued(self, now: datetime) -> Valuation:
        """The owner's portfolio at the latest prices, recorded as a point of its chart."""
        view = self.view(self.owner_portfolio(), now)
        result = Valuation(
            taken_at=now,
            cash=view.portfolio.cash,
            holdings_value=view.holdings_value,
            total_value=view.total_value,
        )
        self._store.valued(view.portfolio.portfolio_id, result)
        return result

    def last_valued_at(self) -> datetime | None:
        return self._store.last_valued_at(self.owner_portfolio().portfolio_id)
