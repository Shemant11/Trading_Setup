"""VWAP mean-reversion strategy for CHOP regime.

Entry: price > 1.5σ from session VWAP.
Stop:  2σ.
Target: VWAP.
Time stop: 45 minutes.

σ = rolling stddev of (price - VWAP) with window 20 bars (~100 min at 5m).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from trader.config.loader import AppConfig
from trader.core.domain import Bar, Signal
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.features import SessionVWAP
from trader.features.streaming import RollingBar
from trader.strategies.base import Strategy


IST = ZoneInfo("Asia/Kolkata")


@dataclass
class _State:
    vwap: SessionVWAP = field(default_factory=SessionVWAP)
    dev: RollingBar = field(default_factory=lambda: RollingBar(window=20))
    signals_today: int = 0


class EquityVWAPMRStrategy(Strategy):
    kind = StrategyKind.EQUITY_VWAP_MR

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.risk_pct: float = float(p.get("risk_pct_per_trade", 0.0025))
        self.z_entry: float = float(p.get("z_entry", 1.5))
        self.z_stop: float = float(p.get("z_stop", 2.0))
        self.max_hold_minutes: int = int(p.get("max_hold_minutes", 45))
        self.max_signals_per_day: int = int(p.get("max_signals_per_day", 3))
        self.no_entry_after: time = _parse_time(p.get("no_entry_after", "14:30"))
        self._states: dict[str, _State] = {}

    def on_bar(self, bar: Bar) -> list[Signal]:
        if not self._enabled:
            return []
        st = self._states.setdefault(bar.instrument_id, _State())
        st.vwap.update(bar.ts_close, bar.close, bar.volume)
        v = st.vwap.value
        if math.isnan(v):
            return []
        dev = bar.close - v
        st.dev.update(dev)
        if not st.dev.ready():
            return []
        bar_ist = bar.ts_close.astimezone(IST).time()
        if bar_ist >= self.no_entry_after:
            return []
        if st.signals_today >= self.max_signals_per_day:
            return []

        sd = st.dev.std()
        if math.isnan(sd) or sd <= 0:
            return []
        z = dev / sd
        if abs(z) < self.z_entry:
            return []

        # Fade extreme deviation
        side = OrderSide.SELL if z > 0 else OrderSide.BUY
        stop_dev = self.z_stop * sd * (1 if z > 0 else -1)
        stop_price = v + stop_dev
        target_price = v

        risk_per_share = abs(bar.close - stop_price)
        if risk_per_share <= 0:
            return []
        qty = int((self._nav * self.risk_pct) // risk_per_share)
        if qty <= 0:
            return []
        st.signals_today += 1
        return [
            Signal(
                id=str(uuid.uuid4()),
                strategy=self.kind,
                instrument_id=bar.instrument_id,
                side=side,
                intended_qty=qty,
                entry_price=bar.close,
                stop_price=stop_price,
                take_profit_prices=[target_price],
                order_type=OrderType.LIMIT,
                product_type=ProductType.MIS,
                validity=Validity.DAY,
                ts=bar.ts_close,
                metadata={"z": z, "sigma": sd, "vwap": v,
                          "expiry_ts": (bar.ts_close + timedelta(minutes=self.max_hold_minutes)).isoformat()},
            )
        ]


def _parse_time(s: Any) -> time:
    if isinstance(s, time):
        return s
    h, m = str(s).split(":")[:2]
    return time(int(h), int(m))
