"""Expiry-day butterfly.

Enter a call butterfly centered at the predicted pin (default = max pain).
Standard long-butterfly: buy 1 lower strike, sell 2 body strikes, buy 1
upper strike.

Time window: 10:30 IST entry, 14:30 IST hard exit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from trader.config.loader import AppConfig
from trader.core.domain import Bar, OptionChainSnapshot, OptionQuote, Signal
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.options.chain import max_pain
from trader.strategies.base import Strategy


IST = ZoneInfo("Asia/Kolkata")


class ExpiryButterflyStrategy(Strategy):
    kind = StrategyKind.OPTIONS_EXPIRY_BUTTERFLY

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.wing_width: float = float(p.get("wing_width", 100))
        self.max_debit_pct: float = float(p.get("max_debit_pct", 0.002))
        self.entry_time: time = _parse(p.get("entry_time", "10:30"))
        self.exit_time: time = _parse(p.get("exit_time", "14:30"))
        self._entered_today: set[str] = set()

    def on_bar(self, bar: Bar) -> list[Signal]:
        return []

    def evaluate(self, snap: OptionChainSnapshot) -> list[Signal]:
        if not self._enabled:
            return []
        now_ist = snap.ts.astimezone(IST).time()
        if now_ist < self.entry_time or now_ist > self.exit_time:
            return []
        key = f"{snap.underlying}:{snap.expiry.isoformat()}"
        if key in self._entered_today:
            return []
        center = max_pain(snap) or snap.spot
        low_k = center - self.wing_width
        high_k = center + self.wing_width

        low = self._closest(snap.calls(), low_k)
        body = self._closest(snap.calls(), center)
        high = self._closest(snap.calls(), high_k)
        if not all([low, body, high]) or low.strike == body.strike or body.strike == high.strike:
            return []
        debit = low.ltp - 2 * body.ltp + high.ltp
        if debit <= 0:
            return []
        max_rupees = self._nav * self.max_debit_pct
        lots = int(max_rupees // max(debit, 1e-6))
        if lots <= 0:
            return []
        parent = str(uuid.uuid4())
        self._entered_today.add(key)
        return [
            _leg(parent, OrderSide.BUY, low, lots, self.kind, snap.underlying),
            _leg(parent, OrderSide.SELL, body, lots * 2, self.kind, snap.underlying),
            _leg(parent, OrderSide.BUY, high, lots, self.kind, snap.underlying),
        ]

    def _closest(self, quotes, target: float) -> Optional[OptionQuote]:
        qs = list(quotes)
        return min(qs, key=lambda q: abs(q.strike - target)) if qs else None


def _leg(parent: str, side: OrderSide, q: OptionQuote, lots: int, kind, underlying: str) -> Signal:
    return Signal(
        id=f"{parent}:{q.strike}",
        strategy=kind,
        instrument_id=f"{underlying}:{q.option_type}:{q.strike}",
        side=side,
        intended_qty=lots,
        entry_price=q.ltp,
        stop_price=q.ltp * (0.1 if side == OrderSide.BUY else 3.0),
        take_profit_prices=[],
        order_type=OrderType.LIMIT,
        product_type=ProductType.NRML,
        validity=Validity.DAY,
        ts=datetime.now(timezone.utc),
        metadata={"parent": parent, "leg": "butterfly"},
    )


def _parse(s):
    if isinstance(s, time):
        return s
    h, m = str(s).split(":")[:2]
    return time(int(h), int(m))
