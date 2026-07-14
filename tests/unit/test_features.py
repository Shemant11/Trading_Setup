"""Tests for streaming features + bar builder."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from trader.core.domain import Tick
from trader.features import (
    BarBuilder,
    RollingATR,
    RollingBar,
    RollingVolatility,
    SessionOR,
    SessionVWAP,
)


IST = ZoneInfo("Asia/Kolkata")


def _tick(ts: datetime, ltp: float, qty: int = 100) -> Tick:
    return Tick(
        instrument_id="X",
        ts_exchange=ts,
        ts_ingest=ts,
        ltp=ltp,
        ltq=qty,
        volume=qty,
    )


def test_rolling_bar_mean_std():
    r = RollingBar(window=3)
    for v in [1.0, 2.0, 3.0]:
        r.update(v)
    assert r.mean() == pytest.approx(2.0)
    assert r.std() == pytest.approx(1.0)
    r.update(4.0)
    # window trims the oldest
    assert r.mean() == pytest.approx(3.0)


def test_rolling_atr_seeds_and_updates():
    atr = RollingATR(window=3)
    # First update seeds prev_close only.
    atr.update(high=11, low=10, close=10.5)
    assert math.isnan(atr.value)
    atr.update(high=12, low=10.5, close=11.5)
    assert atr.value > 0


def test_rolling_volatility_positive():
    v = RollingVolatility(window=10)
    for i in range(20):
        v.update(100 + i)
    assert v.value > 0


def test_session_vwap_resets_across_days():
    v = SessionVWAP()
    d1 = datetime(2025, 3, 14, 9, 15, tzinfo=IST)
    v.update(d1, 100.0, 100)
    v.update(d1 + timedelta(minutes=1), 101.0, 100)
    assert v.value == pytest.approx(100.5)
    d2 = datetime(2025, 3, 15, 9, 15, tzinfo=IST)
    v.update(d2, 200.0, 100)
    assert v.value == pytest.approx(200.0)


def test_session_or_freezes_after_end():
    o = SessionOR()
    d = datetime(2025, 3, 14, 9, 15, tzinfo=IST)
    o.update(d, 100.0)
    o.update(d + timedelta(minutes=5), 105.0)
    o.update(d + timedelta(minutes=10), 98.0)
    # Now cross the 09:30 threshold; a tick at 09:35 should freeze bounds.
    o.update(datetime(2025, 3, 14, 9, 35, tzinfo=IST), 110.0)
    assert o.high == pytest.approx(105.0)
    assert o.low == pytest.approx(98.0)
    assert o.ready


def test_bar_builder_emits_on_boundary():
    bb = BarBuilder(instrument_id="X", timeframe="1m")
    t0 = datetime(2025, 3, 14, 3, 45, 0, tzinfo=timezone.utc)
    emitted = bb.on_tick(_tick(t0, 100.0))
    assert emitted is None
    # A tick still within the first minute
    emitted = bb.on_tick(_tick(t0 + timedelta(seconds=15), 101.0))
    assert emitted is None
    # Crossing into the next minute closes the previous bar
    emitted = bb.on_tick(_tick(t0 + timedelta(seconds=61), 102.0))
    assert emitted is not None
    assert emitted.open == 100.0
    assert emitted.high == 101.0
    assert emitted.low == 100.0
