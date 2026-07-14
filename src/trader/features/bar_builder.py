"""Time-based bar builder.

Emits an OHLCV bar when the current wall-clock bar window closes, tracking
open/high/low/close/volume/trades from ticks. Session-aware — an explicit
`reset()` should be called at 09:15 IST or the caller can call
`start_session(session_open)` to align to the next bar boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from trader.core.domain import Bar, Tick


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


def _seconds(tf: str) -> int:
    if tf not in _TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return _TIMEFRAME_SECONDS[tf]


def _floor_ts(ts: datetime, seconds: int) -> datetime:
    epoch = ts.timestamp()
    floored = int(epoch // seconds) * seconds
    return datetime.fromtimestamp(floored, tz=ts.tzinfo or timezone.utc)


@dataclass
class BarBuilder:
    """Builds bars for one instrument at one timeframe."""

    instrument_id: str
    timeframe: str
    _bar_start: Optional[datetime] = None
    _open: float = 0.0
    _high: float = 0.0
    _low: float = 0.0
    _close: float = 0.0
    _volume: int = 0
    _trades: int = 0
    _vwap_num: float = 0.0
    _vwap_den: float = 0.0

    def reset(self) -> None:
        self._bar_start = None
        self._volume = 0
        self._trades = 0
        self._vwap_num = 0.0
        self._vwap_den = 0.0

    def on_tick(self, tick: Tick) -> Optional[Bar]:
        """Feed a tick. Returns a closed Bar iff the previous bar just ended."""
        secs = _seconds(self.timeframe)
        boundary = _floor_ts(tick.ts_exchange, secs)
        emitted: Optional[Bar] = None
        if self._bar_start is None:
            self._start_new(tick, boundary)
        elif boundary > self._bar_start:
            emitted = self._close_current()
            self._start_new(tick, boundary)
        else:
            self._update_current(tick)
        return emitted

    def force_close(self) -> Optional[Bar]:
        if self._bar_start is None:
            return None
        return self._close_current()

    def _start_new(self, tick: Tick, boundary: datetime) -> None:
        self._bar_start = boundary
        p = tick.ltp
        self._open = p
        self._high = p
        self._low = p
        self._close = p
        self._volume = tick.ltq
        self._trades = 1
        self._vwap_num = p * tick.ltq
        self._vwap_den = tick.ltq

    def _update_current(self, tick: Tick) -> None:
        p = tick.ltp
        if p > self._high:
            self._high = p
        if p < self._low:
            self._low = p
        self._close = p
        self._volume += tick.ltq
        self._trades += 1
        self._vwap_num += p * tick.ltq
        self._vwap_den += tick.ltq

    def _close_current(self) -> Bar:
        assert self._bar_start is not None
        secs = _seconds(self.timeframe)
        vwap = (self._vwap_num / self._vwap_den) if self._vwap_den > 0 else self._close
        bar = Bar(
            instrument_id=self.instrument_id,
            ts_open=self._bar_start,
            ts_close=self._bar_start + timedelta(seconds=secs),
            timeframe=self.timeframe,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=int(self._volume),
            trades=int(self._trades),
            vwap=vwap,
        )
        return bar


@dataclass
class TimeframeBarStream:
    """Fan-out helper: keeps a BarBuilder per (instrument, timeframe)."""

    timeframes: tuple[str, ...] = ("1m", "5m")
    _builders: dict[tuple[str, str], BarBuilder] = field(default_factory=dict)
    on_bar: Optional[Callable[[Bar], None]] = None

    def on_tick(self, tick: Tick) -> list[Bar]:
        out: list[Bar] = []
        for tf in self.timeframes:
            key = (tick.instrument_id, tf)
            b = self._builders.get(key)
            if b is None:
                b = BarBuilder(instrument_id=tick.instrument_id, timeframe=tf)
                self._builders[key] = b
            closed = b.on_tick(tick)
            if closed is not None:
                out.append(closed)
                if self.on_bar:
                    self.on_bar(closed)
        return out

    def force_close_all(self) -> Iterable[Bar]:
        out: list[Bar] = []
        for b in self._builders.values():
            closed = b.force_close()
            if closed is not None:
                out.append(closed)
        return out
