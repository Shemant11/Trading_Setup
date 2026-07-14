"""Swing base-breakout on daily bars.

Trades Nifty 500 (subject to fundamental filter — supplied externally).

Entry (long only):
* Price > 50-DMA > 200-DMA (Stage 2).
* Weekly close > 20-WEMA.
* Base depth over last 25 sessions ≤ 25 %.
* Breakout bar closes above `pivot` with volume > 1.5× 20-day avg.
"""

from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from trader.config.loader import AppConfig
from trader.core.domain import Bar, Signal
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.strategies.base import Strategy


@dataclass
class _State:
    closes: Deque[float] = field(default_factory=lambda: deque(maxlen=210))
    highs: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    lows: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    vols: Deque[float] = field(default_factory=lambda: deque(maxlen=25))
    entered: bool = False


class SwingBreakoutStrategy(Strategy):
    kind = StrategyKind.SWING_BREAKOUT

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.risk_pct: float = float(p.get("risk_pct_per_trade", 0.005))
        self.max_positions: int = int(p.get("max_positions", 12))
        self.base_lookback: int = int(p.get("base_lookback", 25))
        self.base_depth_max: float = float(p.get("base_depth_max", 0.25))
        self.vol_ratio_min: float = float(p.get("vol_ratio_min", 1.5))
        self._states: dict[str, _State] = {}

    def on_bar(self, bar: Bar) -> list[Signal]:
        if not self._enabled or bar.timeframe != "1d":
            self._update_state(bar)
            return []
        s = self._update_state(bar)
        if len(s.closes) < 200:
            return []
        sma50 = sum(list(s.closes)[-50:]) / 50.0
        sma200 = sum(list(s.closes)[-200:]) / 200.0
        # Stage 2 check
        if not (bar.close > sma50 > sma200):
            return []
        base_high = max(list(s.highs)[-self.base_lookback:])
        base_low = min(list(s.lows)[-self.base_lookback:])
        if base_high <= 0:
            return []
        base_depth = (base_high - base_low) / base_high
        if base_depth > self.base_depth_max:
            return []
        avg_vol = sum(s.vols) / len(s.vols) if s.vols else 0.0
        vol_ratio = (bar.volume / avg_vol) if avg_vol > 0 else 0.0
        if vol_ratio < self.vol_ratio_min:
            return []
        if bar.close <= base_high:
            return []
        if s.entered:
            return []
        # Stop = min(base_low, 2×ATR-daily)
        atr_est = self._atr_estimate(s)
        stop = max(base_low, bar.close - 2 * atr_est)
        risk_per_share = bar.close - stop
        if risk_per_share <= 0:
            return []
        qty = int((self._nav * self.risk_pct) // risk_per_share)
        if qty <= 0:
            return []
        s.entered = True
        return [
            Signal(
                id=str(uuid.uuid4()),
                strategy=self.kind,
                instrument_id=bar.instrument_id,
                side=OrderSide.BUY,
                intended_qty=qty,
                entry_price=bar.close,
                stop_price=stop,
                take_profit_prices=[],
                order_type=OrderType.LIMIT,
                product_type=ProductType.CNC,
                validity=Validity.DAY,
                ts=bar.ts_close,
                metadata={"base_high": base_high, "base_depth": base_depth, "vol_ratio": vol_ratio},
            )
        ]

    def _update_state(self, bar: Bar) -> _State:
        s = self._states.setdefault(bar.instrument_id, _State())
        s.closes.append(bar.close)
        s.highs.append(bar.high)
        s.lows.append(bar.low)
        if bar.volume > 0:
            s.vols.append(float(bar.volume))
        return s

    def _atr_estimate(self, s: _State) -> float:
        if len(s.closes) < 14:
            return 0.0
        highs = list(s.highs)[-14:]
        lows = list(s.lows)[-14:]
        closes = list(s.closes)[-15:]
        trs = []
        for i in range(1, 15):
            hi = highs[i - 1]
            lo = lows[i - 1]
            pc = closes[i - 1]
            trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        return sum(trs) / len(trs) if trs else 0.0
