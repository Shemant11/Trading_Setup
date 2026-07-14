"""Market simulator + simulated broker.

`MarketSimulator` fills orders using bar-level microprice + participation
capping + slippage impact. The `SimulatedBroker` implements the same
`Broker` ABC as Dhan/Groww so live and backtest share code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from trader.backtest.cost_model import CostModel, ImpactModel
from trader.brokers.base import (
    Broker,
    BrokerCapabilities,
    HistoricalBar,
    MarginInfo,
    OrderAck,
    OrderUpdate,
    PositionSnapshot,
    TickCallback,
)
from trader.core.domain import Bar, Fill, Instrument, OrderRequest
from trader.core.enums import (
    AssetClass,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)


@dataclass
class MarketSimulator:
    """Fills orders using the most recent bar."""

    cost_model: CostModel
    impact_model: ImpactModel
    participation_cap: float = 0.10
    _last_bar: dict[str, Bar] = field(default_factory=dict)
    _adv_shares: dict[str, float] = field(default_factory=dict)

    def observe_bar(self, bar: Bar, adv_shares: float | None = None) -> None:
        self._last_bar[bar.instrument_id] = bar
        if adv_shares is not None:
            self._adv_shares[bar.instrument_id] = adv_shares

    def fill(
        self,
        req: OrderRequest,
        instrument: Instrument,
        ts: datetime,
    ) -> tuple[Fill | None, float]:
        """Attempt to fill `req` given the last observed bar.

        Returns (fill_or_none, fees). If the bar volume caps our fill below
        1 share we return None (rejection).
        """
        bar = self._last_bar.get(req.instrument_id)
        if bar is None:
            return None, 0.0

        # Cap fill by participation of the bar volume.
        max_by_vol = int(bar.volume * self.participation_cap)
        target_qty = min(req.qty, max(max_by_vol, 1))

        # Reference price: prefer VWAP when available, else close.
        ref_price = bar.vwap or bar.close
        spread_bps = 5.0  # placeholder; real spread comes from depth in Phase 2

        adv = self._adv_shares.get(req.instrument_id, max(bar.volume * 20, 1))
        impact_bps = self.impact_model.impact_bps(
            size=float(target_qty), adv_shares=adv, spread_bps=spread_bps
        )
        signed_impact = impact_bps / 10000.0
        if req.side == OrderSide.BUY:
            fill_price = ref_price * (1.0 + signed_impact)
        else:
            fill_price = ref_price * (1.0 - signed_impact)

        if req.order_type == OrderType.LIMIT and req.limit_price is not None:
            if req.side == OrderSide.BUY and fill_price > req.limit_price:
                return None, 0.0
            if req.side == OrderSide.SELL and fill_price < req.limit_price:
                return None, 0.0

        notional = fill_price * target_qty
        fees = self.cost_model.fee_for(
            notional=notional,
            side=req.side,
            product=req.product_type,
            asset_class=instrument.asset_class,
        )
        fill = Fill(
            fill_id=str(uuid.uuid4()),
            client_order_id=req.client_order_id,
            broker_order_id=None,
            instrument_id=req.instrument_id,
            side=req.side,
            qty=target_qty,
            price=fill_price,
            ts=ts,
            broker="sim",
            fees=fees,
        )
        return fill, fees


@dataclass
class SimulatedBroker(Broker):
    """A `Broker` façade over `MarketSimulator`.

    Only the methods the backtest engine actually calls are implemented; the
    rest raise NotImplementedError so misuse is caught early.
    """

    simulator: MarketSimulator
    now_fn: callable = field(default=lambda: datetime.now(timezone.utc))
    capabilities: BrokerCapabilities = field(
        default_factory=lambda: BrokerCapabilities(
            name="sim",
            supports_equity=True,
            supports_options=True,
            supports_futures=True,
            supports_ws_depth=True,
            max_orders_per_sec=1e9,
        )
    )

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def healthy(self) -> bool:
        return True

    async def get_margin(self) -> MarginInfo:
        return MarginInfo(available=1e12, utilized=0, total=1e12)

    async def list_positions(self) -> list[PositionSnapshot]:
        return []

    async def place_order(self, req: OrderRequest) -> OrderAck:
        # The simulator does the actual fill; the caller invokes .fill().
        return OrderAck(
            broker_order_id=str(uuid.uuid4()),
            client_order_id=req.client_order_id,
            status=OrderStatus.OPEN,
            ts=self.now_fn(),
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        return True

    async def modify_order(self, *args, **kwargs) -> bool:  # noqa: ARG002
        return True

    async def get_order(self, broker_order_id: str) -> OrderUpdate:
        return OrderUpdate(
            broker_order_id=broker_order_id,
            client_order_id=None,
            status=OrderStatus.FILLED,
            ts=self.now_fn(),
        )

    async def list_orders(self) -> list[OrderUpdate]:
        return []

    async def get_instrument(self, symbol: str, exchange: str) -> Optional[Instrument]:
        return None

    async def historical_ohlc(
        self, instrument, timeframe: str, start: datetime, end: datetime
    ) -> list[HistoricalBar]:
        raise NotImplementedError("SimulatedBroker.historical_ohlc — provide data separately")

    async def subscribe_ticks(self, instruments, callback: TickCallback) -> None:
        raise NotImplementedError("SimulatedBroker.subscribe_ticks — not used in backtest")

    async def unsubscribe_ticks(self, instruments) -> None:
        return None
