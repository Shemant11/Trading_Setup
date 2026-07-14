"""Bull-call / bear-put debit spreads for trending, low-IVR regime."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from trader.config.loader import AppConfig
from trader.core.domain import Bar, OptionChainSnapshot, OptionQuote, Signal
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.options.iv_rank import IVRankTracker
from trader.strategies.base import Strategy


class DebitSpreadStrategy(Strategy):
    kind = StrategyKind.OPTIONS_DEBIT_SPREAD

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.ivr_max: float = float(p.get("ivr_max", 30)) / 100.0
        self.strike_offset_pct: float = float(p.get("strike_offset_pct", 0.005))
        self.risk_pct_per_trade: float = float(p.get("risk_pct_per_trade", 0.004))
        self.iv_tracker = IVRankTracker()

    def on_bar(self, bar: Bar) -> list[Signal]:
        return []

    def evaluate(
        self,
        snap: OptionChainSnapshot,
        *,
        bias: str,             # "bull" or "bear"
    ) -> list[Signal]:
        if not self._enabled:
            return []
        if snap.atm_iv:
            self.iv_tracker.observe(snap.underlying, snap.atm_iv)
        ivr = self.iv_tracker.rank(snap.underlying)
        if ivr != ivr or ivr > self.ivr_max:
            return []
        if bias == "bull":
            long_leg = self._nearest_strike(snap.calls(), snap.spot)
            short_leg = self._nearest_strike(
                snap.calls(), snap.spot * (1.0 + self.strike_offset_pct)
            )
            side_long, side_short = OrderSide.BUY, OrderSide.SELL
        elif bias == "bear":
            long_leg = self._nearest_strike(snap.puts(), snap.spot)
            short_leg = self._nearest_strike(
                snap.puts(), snap.spot * (1.0 - self.strike_offset_pct)
            )
            side_long, side_short = OrderSide.BUY, OrderSide.SELL
        else:
            return []
        if long_leg is None or short_leg is None or long_leg.strike == short_leg.strike:
            return []
        debit = max(long_leg.ltp - short_leg.ltp, 1e-6)
        max_rupees = self._nav * self.risk_pct_per_trade
        lots = int(max_rupees // debit)
        if lots <= 0:
            return []
        parent = str(uuid.uuid4())
        return [
            _signal(parent, side_long, long_leg, lots, self.kind, snap.underlying),
            _signal(parent, side_short, short_leg, lots, self.kind, snap.underlying),
        ]

    def _nearest_strike(self, quotes, target: float) -> Optional[OptionQuote]:
        qs = list(quotes)
        if not qs:
            return None
        return min(qs, key=lambda q: abs(q.strike - target))


def _signal(parent: str, side: OrderSide, q: OptionQuote, lots: int, kind, underlying: str) -> Signal:
    return Signal(
        id=f"{parent}:{q.strike}:{q.option_type}",
        strategy=kind,
        instrument_id=f"{underlying}:{q.option_type}:{q.strike}",
        side=side,
        intended_qty=lots,
        entry_price=q.ltp,
        stop_price=q.ltp * (0.5 if side == OrderSide.BUY else 1.5),
        take_profit_prices=[],
        order_type=OrderType.LIMIT,
        product_type=ProductType.NRML,
        validity=Validity.DAY,
        ts=datetime.now(timezone.utc),
        metadata={"parent": parent},
    )
