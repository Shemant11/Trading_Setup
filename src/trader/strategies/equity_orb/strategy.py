"""Equity ORB with auction confirmation.

Simplified live implementation of the spec. Filters that require external
data (sector index confirmation, event calendar) are wired as optional and
default to a permissive `True` — the risk engine still gates final size.

Entry (long side; short is symmetric):

* Bar is 5-minute (config: `timeframe`).
* Bar is after `or_end` (default 09:30 IST).
* `bar.close > OR_high * (1 + break_threshold_pct)` (default 0.0015).
* `bar.volume >= 2 * avg_volume_5m` (rolling 20-bar mean).
* `bar.close > session VWAP`.
* `book_imbalance >= 0.55` (if available; else pass-through).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import time
from typing import Any, Optional
from zoneinfo import ZoneInfo

from trader.config.loader import AppConfig
from trader.core.domain import Bar, Signal, Tick
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.features import SessionOR, SessionVWAP
from trader.features.streaming import RollingATR, RollingBar
from trader.strategies.base import Strategy


IST = ZoneInfo("Asia/Kolkata")


@dataclass
class _State:
    session_or: SessionOR = field(default_factory=SessionOR)
    session_vwap: SessionVWAP = field(default_factory=SessionVWAP)
    atr_15m: RollingATR = field(default_factory=lambda: RollingATR(window=15))
    vol_bar: RollingBar = field(default_factory=lambda: RollingBar(window=20))
    or_break_taken_today: str | None = None  # "long", "short", or None


class EquityORBStrategy(Strategy):
    kind = StrategyKind.EQUITY_ORB

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.risk_pct: float = float(p.get("risk_pct_per_trade", 0.004))
        self.max_positions: int = int(p.get("max_positions", 5))
        self.break_threshold_pct: float = float(p.get("break_threshold_pct", 0.0015))
        self.vol_multiplier: float = float(p.get("vol_multiplier", 2.0))
        self.or_start: time = _parse_time(p.get("or_start", "09:15"))
        self.or_end: time = _parse_time(p.get("or_end", "09:30"))
        self.time_stop: time = _parse_time(p.get("time_stop", "14:45"))
        self.auto_sq: time = _parse_time(p.get("auto_square_off", "15:15"))
        self.book_imbalance_min: float = float(p.get("book_imbalance_min", 0.55))
        # Per-instrument state
        self._states: dict[str, _State] = {}
        # Per-instrument book imbalance feed (fed externally from depth stream).
        self._book_imb: dict[str, float] = {}

    def update_book_imbalance(self, instrument_id: str, imbalance: float) -> None:
        self._book_imb[instrument_id] = imbalance

    def on_tick(self, tick: Tick) -> list[Signal]:
        st = self._get_state(tick.instrument_id)
        st.session_or.update(tick.ts_exchange, tick.ltp)
        st.session_vwap.update(tick.ts_exchange, tick.ltp, tick.ltq)
        return []

    def on_bar(self, bar: Bar) -> list[Signal]:
        if not self._enabled:
            return []
        st = self._get_state(bar.instrument_id)
        st.session_or.update(bar.ts_close, bar.high)
        st.session_or.update(bar.ts_close, bar.low)
        st.session_vwap.update(bar.ts_close, bar.close, bar.volume)
        st.atr_15m.update(bar.high, bar.low, bar.close)
        st.vol_bar.update(bar.volume)

        # Only trade after OR window ends and before time_stop.
        bar_ist = bar.ts_close.astimezone(IST).time()
        if bar_ist < self.or_end or bar_ist >= self.time_stop:
            return []
        if not st.session_or.ready:
            return []
        if st.or_break_taken_today is not None:
            return []
        or_hi = st.session_or.high
        or_lo = st.session_or.low
        if not (or_hi and or_lo):
            return []

        vwap = st.session_vwap.value
        avg_vol = st.vol_bar.mean() or 0.0
        vol_ok = bar.volume >= (self.vol_multiplier * avg_vol) if avg_vol > 0 else False

        # Book imbalance is fed externally by the live L2 depth stream. In
        # backtests (and any bar-only environment) no depth data ever arrives,
        # so treat "never seen" as pass-through rather than the neutral 0.5
        # value that would fail both long and short gates when the threshold
        # is above 0.5. Users who genuinely want to force the check off can
        # still set ``book_imbalance_min: 0.0`` in config.
        has_imb = bar.instrument_id in self._book_imb
        imb = self._book_imb.get(bar.instrument_id, 0.5)

        # ---- long breakout ----
        long_break = bar.close > or_hi * (1 + self.break_threshold_pct)
        vwap_ok_long = bar.close > vwap if not _isnan(vwap) else True
        imb_ok_long = (not has_imb) or (imb >= self.book_imbalance_min)

        if long_break and vol_ok and vwap_ok_long and imb_ok_long:
            st.or_break_taken_today = "long"
            return [self._build_signal(bar, OrderSide.BUY, or_hi, or_lo, st)]

        # ---- short breakout ----
        short_break = bar.close < or_lo * (1 - self.break_threshold_pct)
        vwap_ok_short = bar.close < vwap if not _isnan(vwap) else True
        imb_ok_short = (not has_imb) or ((1.0 - imb) >= self.book_imbalance_min)

        if short_break and vol_ok and vwap_ok_short and imb_ok_short:
            st.or_break_taken_today = "short"
            return [self._build_signal(bar, OrderSide.SELL, or_hi, or_lo, st)]

        return []

    # ---- helpers ---------------------------------------------------------

    def _build_signal(
        self,
        bar: Bar,
        side: OrderSide,
        or_hi: float,
        or_lo: float,
        st: _State,
    ) -> Signal:
        import math
        or_mid = (or_hi + or_lo) / 2.0
        atr_raw = st.atr_15m.value
        atr = 0.0 if math.isnan(atr_raw) else atr_raw
        # Stop = min(distance to OR mid, 1 * ATR-15m) on the loss side.
        if side == OrderSide.BUY:
            stop_atr = bar.close - max(atr, 1e-6)
            stop = min(or_mid, stop_atr)
        else:
            stop_atr = bar.close + max(atr, 1e-6)
            stop = max(or_mid, stop_atr)
        # Position sizing: risk_pct of NAV / (entry - stop)
        risk_per_share = abs(bar.close - stop)
        if risk_per_share <= 0:
            return Signal(
                id=str(uuid.uuid4()),
                strategy=self.kind,
                instrument_id=bar.instrument_id,
                side=side,
                intended_qty=0,
                entry_price=bar.close,
                stop_price=stop,
                take_profit_prices=[],
                order_type=OrderType.LIMIT,
                product_type=ProductType.MIS,
                validity=Validity.DAY,
                ts=bar.ts_close,
            )
        qty = int((self._nav * self.risk_pct) // risk_per_share)
        r = risk_per_share
        tp = [bar.close + r if side == OrderSide.BUY else bar.close - r,
              bar.close + 2 * r if side == OrderSide.BUY else bar.close - 2 * r]
        return Signal(
            id=str(uuid.uuid4()),
            strategy=self.kind,
            instrument_id=bar.instrument_id,
            side=side,
            intended_qty=max(qty, 1),
            entry_price=bar.close,
            stop_price=stop,
            take_profit_prices=tp,
            order_type=OrderType.LIMIT,
            product_type=ProductType.MIS,
            validity=Validity.DAY,
            ts=bar.ts_close,
            metadata={"or_hi": or_hi, "or_lo": or_lo, "atr15": st.atr_15m.value},
        )

    def _get_state(self, instrument_id: str) -> _State:
        st = self._states.get(instrument_id)
        if st is None:
            st = _State()
            self._states[instrument_id] = st
        return st


def _parse_time(s: Any) -> time:
    if isinstance(s, time):
        return s
    h, m = str(s).split(":")[:2]
    return time(int(h), int(m))


def _isnan(x: float) -> bool:
    return x != x  # noqa: PLR0124 - NaN check
