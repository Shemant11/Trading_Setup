"""IV Rank / IV Percentile tracker.

Maintains a rolling year (default 252 trading days) of ATM IV observations
per underlying. Feeds strategy regime decisions.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class IVSeries:
    window: int = 252
    values: Deque[float] = field(default_factory=deque)

    def add(self, iv: float) -> None:
        if math.isnan(iv):
            return
        self.values.append(iv)
        while len(self.values) > self.window:
            self.values.popleft()

    def rank(self, iv: float | None = None) -> float:
        """IV Rank = (current - low) / (high - low)."""
        if not self.values:
            return float("nan")
        lo = min(self.values)
        hi = max(self.values)
        v = self.values[-1] if iv is None else iv
        if hi - lo <= 0:
            return float("nan")
        return (v - lo) / (hi - lo)

    def percentile(self, iv: float | None = None) -> float:
        """Fraction of past-year days with IV < current."""
        if not self.values:
            return float("nan")
        v = self.values[-1] if iv is None else iv
        n_below = sum(1 for x in self.values if x < v)
        return n_below / len(self.values)


class IVRankTracker:
    """Per-underlying IV series with rank/percentile helpers."""

    def __init__(self, window: int = 252) -> None:
        self._series: dict[str, IVSeries] = {}
        self._window = window

    def observe(self, underlying: str, atm_iv: float) -> None:
        s = self._series.get(underlying)
        if s is None:
            s = IVSeries(window=self._window)
            self._series[underlying] = s
        s.add(atm_iv)

    def rank(self, underlying: str) -> float:
        s = self._series.get(underlying)
        return s.rank() if s else float("nan")

    def percentile(self, underlying: str) -> float:
        s = self._series.get(underlying)
        return s.percentile() if s else float("nan")


def expected_move(spot: float, atm_iv: float, days_to_expiry: int) -> float:
    """1-sigma expected move: spot * IV * sqrt(dte/365)."""
    if spot <= 0 or atm_iv <= 0 or days_to_expiry <= 0:
        return 0.0
    return spot * atm_iv * math.sqrt(days_to_expiry / 365.0)
