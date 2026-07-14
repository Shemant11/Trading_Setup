"""On-line rolling features used by strategies.

Every class exposes:

* `update(x: float) -> None` — feed a new observation.
* `.value` property — current output (may be NaN before warm-up).

Kept algorithmically simple (bounded-memory deques) because at our tick rate
Python is more than fast enough.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class RollingBar:
    """Fixed-size rolling window of floats with mean/std helpers."""

    window: int
    buffer: Deque[float] = field(default_factory=deque)

    def update(self, x: float) -> None:
        self.buffer.append(x)
        if len(self.buffer) > self.window:
            self.buffer.popleft()

    def ready(self) -> bool:
        return len(self.buffer) >= self.window

    def mean(self) -> float:
        if not self.buffer:
            return math.nan
        return sum(self.buffer) / len(self.buffer)

    def std(self, ddof: int = 1) -> float:
        n = len(self.buffer)
        if n <= ddof:
            return math.nan
        m = self.mean()
        var = sum((v - m) ** 2 for v in self.buffer) / (n - ddof)
        return math.sqrt(var)

    def max(self) -> float:
        return max(self.buffer) if self.buffer else math.nan

    def min(self) -> float:
        return min(self.buffer) if self.buffer else math.nan


@dataclass
class RollingATR:
    """Wilder-style rolling ATR (EMA of True Range)."""

    window: int = 14
    _prev_close: Optional[float] = None
    _atr: Optional[float] = None
    _n_seen: int = 0

    @property
    def value(self) -> float:
        return self._atr if self._atr is not None else math.nan

    def update(self, high: float, low: float, close: float) -> None:
        if self._prev_close is None:
            self._prev_close = close
            return
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )
        self._n_seen += 1
        if self._atr is None:
            # Seed with simple average up to first `window` bars.
            self._atr = tr
        else:
            alpha = 1.0 / self.window
            self._atr = (1.0 - alpha) * self._atr + alpha * tr
        self._prev_close = close


@dataclass
class RollingVolatility:
    """Rolling stddev of returns."""

    window: int
    _last_price: Optional[float] = None
    _rets: RollingBar = field(init=False)

    def __post_init__(self) -> None:
        self._rets = RollingBar(window=self.window)

    def update(self, price: float) -> None:
        if self._last_price is not None and self._last_price > 0:
            r = math.log(price / self._last_price)
            self._rets.update(r)
        self._last_price = price

    @property
    def value(self) -> float:
        return self._rets.std()


@dataclass
class RollingZScore:
    """Rolling z-score based on the last `window` observations."""

    window: int
    _buf: RollingBar = field(init=False)

    def __post_init__(self) -> None:
        self._buf = RollingBar(window=self.window)

    def update(self, x: float) -> None:
        self._buf.update(x)

    def zscore(self, x: float) -> float:
        s = self._buf.std()
        if math.isnan(s) or s == 0:
            return math.nan
        return (x - self._buf.mean()) / s


@dataclass
class RollingBookImbalance:
    """5-level book imbalance kept in a short rolling window for stability."""

    window: int = 20
    _buf: RollingBar = field(init=False)

    def __post_init__(self) -> None:
        self._buf = RollingBar(window=self.window)

    def update(self, bid_size: float, ask_size: float) -> None:
        total = bid_size + ask_size
        if total > 0:
            self._buf.update(bid_size / total)

    @property
    def value(self) -> float:
        return self._buf.mean()
