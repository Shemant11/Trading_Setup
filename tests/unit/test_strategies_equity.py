"""Equity ORB + VWAP-MR strategy tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trader.config.loader import AppConfig
from trader.core.domain import Bar
from trader.strategies.equity_orb import EquityORBStrategy
from trader.strategies.equity_vwap_mr import EquityVWAPMRStrategy


IST = ZoneInfo("Asia/Kolkata")


def _cfg(overrides: dict | None = None) -> AppConfig:
    base = {
        "capital": {"nav": 1_000_000},
        "strategies": {
            "equity_orb": {"enabled": True, **(overrides or {})},
            "equity_vwap_mr": {"enabled": True},
        },
    }
    return AppConfig.model_validate(base)


def _bar(ts_ist: datetime, o: float, h: float, l: float, c: float, v: int = 20000) -> Bar:
    return Bar(
        instrument_id="R",
        ts_open=ts_ist.astimezone(ZoneInfo("UTC")),
        ts_close=(ts_ist + timedelta(minutes=5)).astimezone(ZoneInfo("UTC")),
        timeframe="5m",
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        vwap=(o + h + l + c) / 4,
    )


def test_orb_no_entry_within_or_window():
    strat = EquityORBStrategy(_cfg())
    ts = datetime(2025, 3, 14, 9, 20, tzinfo=IST)
    strat._book_imb["R"] = 0.9
    signals = strat.on_bar(_bar(ts, 100, 101, 99, 100.5))
    assert signals == []


def test_orb_long_breakout_after_or_window():
    strat = EquityORBStrategy(_cfg())
    strat.update_book_imbalance("R", 0.8)
    # Populate OR + volume history with 20 pre-OR bars
    base = datetime(2025, 3, 14, 9, 15, tzinfo=IST)
    for i in range(3):
        b = _bar(base + timedelta(minutes=5 * i), 100, 101, 99, 100)
        strat.on_bar(b)
    # After OR closes, feed vol history bars just below breakout
    for i in range(20):
        b = _bar(base + timedelta(minutes=30 + 5 * i), 100.2, 100.4, 100.0, 100.2, v=10000)
        strat.on_bar(b)
    # Now hit a breakout bar (2x volume + close > OR high * 1.0015)
    bt = _bar(base + timedelta(minutes=130), 100.5, 102.5, 100.5, 102.0, v=30000)
    signals = strat.on_bar(bt)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.side.value == "BUY"
    assert sig.stop_price < sig.entry_price


def test_orb_takes_only_one_break_per_day():
    strat = EquityORBStrategy(_cfg())
    strat.update_book_imbalance("R", 0.9)
    base = datetime(2025, 3, 14, 9, 15, tzinfo=IST)
    for i in range(3):
        strat.on_bar(_bar(base + timedelta(minutes=5 * i), 100, 101, 99, 100))
    for i in range(20):
        strat.on_bar(_bar(base + timedelta(minutes=30 + 5 * i), 100.2, 100.4, 100.0, 100.2, v=10000))
    first = strat.on_bar(_bar(base + timedelta(minutes=130), 100.5, 102.5, 100.5, 102.0, v=30000))
    second = strat.on_bar(_bar(base + timedelta(minutes=135), 102.0, 103.0, 101.5, 102.5, v=30000))
    assert len(first) == 1
    assert second == []


def test_vwap_mr_no_signal_below_z_threshold():
    strat = EquityVWAPMRStrategy(_cfg())
    ts = datetime(2025, 3, 14, 10, 0, tzinfo=IST)
    for i in range(30):
        strat.on_bar(_bar(ts + timedelta(minutes=5 * i), 100, 100.5, 99.5, 100.0))
    # Small deviation — below z_entry
    out = strat.on_bar(_bar(ts + timedelta(minutes=200), 100.2, 100.4, 100.0, 100.2))
    assert out == []
