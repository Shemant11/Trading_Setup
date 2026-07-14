"""Domain models.

All models are immutable-by-default Pydantic v2 models. Timestamps are
timezone-aware UTC unless labelled otherwise; strategy/report code converts
to IST at the edges.

Money and quantities are `Decimal`-ish `float`s for now (JSON-friendly and
fast); when we move to real ledger we can migrate select fields to `Decimal`.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trader.core.enums import (
    AssetClass,
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Segment,
    StrategyKind,
    Validity,
)


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class Instrument(_Base):
    """Broker-agnostic instrument identifier.

    `security_id` is Dhan's canonical numeric id (also used as the primary key
    in our journal). `symbol` is the human-readable NSE trading symbol.
    """

    security_id: str
    symbol: str
    exchange: Exchange
    segment: Segment
    asset_class: AssetClass
    lot_size: int = 1
    tick_size: float = 0.05
    isin: Optional[str] = None

    # Options-only fields
    underlying_symbol: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[date] = None
    option_type: Optional[Literal["CE", "PE"]] = None

    @model_validator(mode="after")
    def _validate_options(self) -> Instrument:
        if self.asset_class == AssetClass.OPTION:
            missing = [f for f in ("underlying_symbol", "strike", "expiry", "option_type")
                       if getattr(self, f) is None]
            if missing:
                raise ValueError(f"Option instrument missing fields: {missing}")
        return self

    @property
    def is_option(self) -> bool:
        return self.asset_class == AssetClass.OPTION


class Tick(_Base):
    """A single trade or top-of-book update."""

    instrument_id: str
    ts_exchange: datetime
    ts_ingest: datetime
    ltp: float
    ltq: int = 0
    volume: int = 0
    oi: int = 0
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_qty: int = 0
    ask_qty: int = 0

    @property
    def spread_bps(self) -> Optional[float]:
        if self.bid and self.ask and self.bid > 0:
            return (self.ask - self.bid) / ((self.ask + self.bid) / 2) * 10000
        return None

    @property
    def microprice(self) -> Optional[float]:
        """Weighted mid using order sizes on both sides."""
        if self.bid and self.ask and (self.bid_qty + self.ask_qty) > 0:
            return (self.bid * self.ask_qty + self.ask * self.bid_qty) / (
                self.bid_qty + self.ask_qty
            )
        return None


class Quote(_Base):
    """Snapshot quote with 5-level depth."""

    instrument_id: str
    ts: datetime
    ltp: float
    bids: list[tuple[float, int]] = Field(default_factory=list)   # (price, qty)
    asks: list[tuple[float, int]] = Field(default_factory=list)

    @property
    def imbalance(self) -> Optional[float]:
        """Buy-side imbalance in [0, 1]."""
        if not self.bids or not self.asks:
            return None
        b = sum(q for _, q in self.bids)
        a = sum(q for _, q in self.asks)
        total = b + a
        return b / total if total > 0 else None


class Bar(_Base):
    """OHLCV bar for a given timeframe."""

    instrument_id: str
    ts_open: datetime
    ts_close: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    trades: int = 0
    vwap: Optional[float] = None
    oi: Optional[int] = None

    @model_validator(mode="after")
    def _validate_ohlc(self) -> Bar:
        if self.high < self.low:
            raise ValueError(f"Bar high {self.high} < low {self.low}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(f"Open/close outside high/low range")
        if self.volume < 0:
            raise ValueError(f"Negative volume {self.volume}")
        return self


class OptionQuote(_Base):
    """A single leg in an option chain snapshot."""

    strike: float
    option_type: Literal["CE", "PE"]
    ltp: float
    bid: float = 0.0
    ask: float = 0.0
    iv: Optional[float] = None
    oi: int = 0
    oi_change: int = 0
    volume: int = 0
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


class OptionChainSnapshot(_Base):
    """Full option chain for one underlying at one point in time."""

    underlying: str
    spot: float
    expiry: date
    ts: datetime
    atm_iv: Optional[float] = None
    quotes: list[OptionQuote] = Field(default_factory=list)

    def calls(self) -> list[OptionQuote]:
        return [q for q in self.quotes if q.option_type == "CE"]

    def puts(self) -> list[OptionQuote]:
        return [q for q in self.quotes if q.option_type == "PE"]

    @property
    def pcr_oi(self) -> Optional[float]:
        c = sum(q.oi for q in self.calls())
        p = sum(q.oi for q in self.puts())
        return p / c if c > 0 else None

    @property
    def pcr_volume(self) -> Optional[float]:
        c = sum(q.volume for q in self.calls())
        p = sum(q.volume for q in self.puts())
        return p / c if c > 0 else None


class Signal(_Base):
    """A strategy's proposed trade before risk validation."""

    id: str
    strategy: StrategyKind
    instrument_id: str
    side: OrderSide
    intended_qty: int
    entry_price: float                           # planned entry (limit or reference)
    stop_price: float
    take_profit_prices: list[float] = Field(default_factory=list)
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.MIS
    validity: Validity = Validity.DAY
    ts: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.stop_price)


class OrderRequest(_Base):
    """A signal that has passed risk and is ready for execution."""

    client_order_id: str
    strategy: StrategyKind
    instrument_id: str
    side: OrderSide
    qty: int
    order_type: OrderType
    product_type: ProductType
    validity: Validity = Validity.DAY
    limit_price: Optional[float] = None
    trigger_price: Optional[float] = None
    parent_signal_id: Optional[str] = None
    tag: Optional[str] = None
    exchange: Optional[Exchange] = None


class Order(BaseModel):
    """A live order, mutable so state machine transitions can update it."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    client_order_id: str
    broker_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    strategy: StrategyKind
    instrument_id: str
    side: OrderSide
    qty: int
    filled_qty: int = 0
    avg_fill_price: Optional[float] = None
    order_type: OrderType
    product_type: ProductType
    validity: Validity = Validity.DAY
    limit_price: Optional[float] = None
    trigger_price: Optional[float] = None
    status: OrderStatus = OrderStatus.NEW
    reject_reason: Optional[str] = None
    broker: Optional[str] = None
    ts_created: datetime
    ts_updated: datetime
    tag: Optional[str] = None
    parent_signal_id: Optional[str] = None

    @property
    def remaining_qty(self) -> int:
        return max(0, self.qty - self.filled_qty)


class Fill(_Base):
    """A single execution against an order."""

    fill_id: str
    client_order_id: str
    broker_order_id: Optional[str] = None
    instrument_id: str
    side: OrderSide
    qty: int
    price: float
    ts: datetime
    broker: Optional[str] = None
    fees: float = 0.0


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    instrument_id: str
    qty: int = 0                    # positive long, negative short
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: Optional[float] = None
    ts_updated: datetime

    @property
    def is_flat(self) -> bool:
        return self.qty == 0

    def mark(self, last_price: float, ts: datetime) -> None:
        self.last_price = last_price
        self.ts_updated = ts
        self.unrealized_pnl = (last_price - self.avg_price) * self.qty


class Trade(_Base):
    """A completed round-trip trade, for the journal."""

    trade_id: str
    strategy: StrategyKind
    instrument_id: str
    side: OrderSide
    qty: int
    entry_price: float
    exit_price: float
    entry_ts: datetime
    exit_ts: datetime
    gross_pnl: float
    fees: float = 0.0
    net_pnl: float = 0.0
    r_multiple: Optional[float] = None
    tag: Optional[str] = None
