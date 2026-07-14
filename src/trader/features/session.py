"""Session-scoped features (VWAP, Opening Range) with clean reset.

Session bounds default to Indian equity intraday: 09:15:00 IST → 15:30:00 IST.
Feeds must be in exchange time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


def _ist_date(ts: datetime) -> tuple[int, int, int]:
    ts_ist = ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(IST)
    return ts_ist.year, ts_ist.month, ts_ist.day


def _in_range_ist(ts: datetime, start: time, end: time) -> bool:
    ts_ist = ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(IST)
    t = ts_ist.time()
    return start <= t <= end


@dataclass
class SessionVWAP:
    """Session-anchored VWAP.

    Auto-resets at first tick of a new IST calendar day.
    """

    _current_day: Optional[tuple[int, int, int]] = None
    _num: float = 0.0
    _den: float = 0.0

    def update(self, ts: datetime, price: float, qty: int) -> None:
        d = _ist_date(ts)
        if self._current_day != d:
            self._current_day = d
            self._num = 0.0
            self._den = 0.0
        self._num += price * qty
        self._den += qty

    @property
    def value(self) -> float:
        return self._num / self._den if self._den > 0 else math.nan


@dataclass
class SessionOR:
    """Opening-range high/low over a configurable window (default 09:15–09:30 IST).

    Freezes at `end` and thereafter `hi`/`lo` are immutable for the day.
    """

    start: time = time(9, 15)
    end: time = time(9, 30)
    _current_day: Optional[tuple[int, int, int]] = None
    _hi: float = math.nan
    _lo: float = math.nan
    _frozen: bool = False

    def update(self, ts: datetime, price: float) -> None:
        d = _ist_date(ts)
        if self._current_day != d:
            self._current_day = d
            self._hi = math.nan
            self._lo = math.nan
            self._frozen = False
        if self._frozen:
            return
        if _in_range_ist(ts, self.start, self.end):
            if math.isnan(self._hi) or price > self._hi:
                self._hi = price
            if math.isnan(self._lo) or price < self._lo:
                self._lo = price
        else:
            # Once we've past `end`, freeze.
            if not math.isnan(self._hi):
                self._frozen = True

    @property
    def high(self) -> float:
        return self._hi

    @property
    def low(self) -> float:
        return self._lo

    @property
    def mid(self) -> float:
        if math.isnan(self._hi) or math.isnan(self._lo):
            return math.nan
        return (self._hi + self._lo) / 2.0

    @property
    def ready(self) -> bool:
        return self._frozen or (not math.isnan(self._hi) and not math.isnan(self._lo))


@dataclass
class SessionRegistry:
    """Holds session features keyed by instrument id.

    Ensures each instrument gets its own SessionVWAP / SessionOR without
    strategies having to book-keep them by hand.
    """

    vwap: dict[str, SessionVWAP] = field(default_factory=dict)
    orr: dict[str, SessionOR] = field(default_factory=dict)

    def get_vwap(self, instrument_id: str) -> SessionVWAP:
        v = self.vwap.get(instrument_id)
        if v is None:
            v = SessionVWAP()
            self.vwap[instrument_id] = v
        return v

    def get_or(self, instrument_id: str) -> SessionOR:
        o = self.orr.get(instrument_id)
        if o is None:
            o = SessionOR()
            self.orr[instrument_id] = o
        return o
