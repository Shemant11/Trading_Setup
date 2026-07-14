"""Broker abstraction.

Every broker implementation must provide the same async interface so the
Execution Gateway, Portfolio Manager, and Market Data client can treat them
interchangeably (with a small `capabilities` object for feature gating).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from trader.core.domain import Instrument, OrderRequest, Tick
from trader.core.enums import OrderStatus, ProductType


@dataclass(slots=True)
class BrokerCapabilities:
    """Advertised feature set for a broker adapter.

    The execution engine uses these to decide routing (options failover is
    disabled when `supports_options=False` on the failover broker).
    """

    name: str
    supports_equity: bool = True
    supports_options: bool = True
    supports_futures: bool = True
    supports_bracket_order: bool = False
    supports_cover_order: bool = False
    supports_iceberg: bool = False
    supports_ws_depth: bool = False
    max_orders_per_sec: float = 10.0


@dataclass(slots=True)
class OrderAck:
    """What a broker returns immediately after `place_order`."""

    broker_order_id: str
    client_order_id: str
    status: OrderStatus
    ts: datetime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderUpdate:
    """A push update about an order (from WS or polling)."""

    broker_order_id: str
    client_order_id: Optional[str]
    status: OrderStatus
    filled_qty: int = 0
    avg_fill_price: Optional[float] = None
    reject_reason: Optional[str] = None
    ts: datetime = field(default_factory=lambda: datetime.utcnow())
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PositionSnapshot:
    """Broker's view of a position — the source of truth for reconciliation."""

    instrument_id: str
    symbol: str
    qty: int
    avg_price: float
    product_type: ProductType
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    last_price: Optional[float] = None


@dataclass(slots=True)
class MarginInfo:
    available: float
    utilized: float
    total: float


@dataclass(slots=True)
class HistoricalBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: Optional[int] = None


TickCallback = Callable[[Tick], Awaitable[None]]


@dataclass(slots=True)
class WSMessage:
    """A raw normalized message from a broker WS."""

    kind: str          # "tick", "depth", "order_update", "position_update", "heartbeat"
    data: dict[str, Any]
    ts: datetime


class Broker(ABC):
    """Broker facade. All methods are async and idempotent-safe where noted."""

    capabilities: BrokerCapabilities

    # ---------- lifecycle -------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    @abstractmethod
    async def healthy(self) -> bool:
        ...

    # ---------- account ---------------------------------------------------

    @abstractmethod
    async def get_margin(self) -> MarginInfo:
        ...

    @abstractmethod
    async def list_positions(self) -> list[PositionSnapshot]:
        ...

    # ---------- orders (must be idempotent by client_order_id) -----------

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderAck:
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    async def modify_order(
        self,
        broker_order_id: str,
        *,
        qty: Optional[int] = None,
        limit_price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> bool:
        ...

    @abstractmethod
    async def get_order(self, broker_order_id: str) -> OrderUpdate:
        ...

    @abstractmethod
    async def list_orders(self) -> list[OrderUpdate]:
        ...

    # ---------- instruments -----------------------------------------------

    @abstractmethod
    async def get_instrument(self, symbol: str, exchange: str) -> Optional[Instrument]:
        ...

    # ---------- market data ----------------------------------------------

    @abstractmethod
    async def historical_ohlc(
        self,
        instrument: Instrument,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalBar]:
        ...

    @abstractmethod
    async def subscribe_ticks(
        self, instruments: list[Instrument], callback: TickCallback
    ) -> None:
        ...

    @abstractmethod
    async def unsubscribe_ticks(self, instruments: list[Instrument]) -> None:
        ...
