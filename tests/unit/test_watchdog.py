"""Watchdog tests."""

from __future__ import annotations

import time

from trader.ops.watchdog import WatchdogState, watchdog_check


def test_healthy_state_returns_none():
    s = WatchdogState()
    for _ in range(30):
        s.record_latency(50.0)
    assert watchdog_check(s) is None


def test_bad_latency_triggers_halt():
    s = WatchdogState()
    for _ in range(30):
        s.record_latency(2000.0)
    reason = watchdog_check(s, latency_p95_halt_ms=1000)
    assert reason and "latency" in reason


def test_ws_gap_triggers_halt():
    s = WatchdogState()
    s.record_ws_disconnect()
    s.last_ws_disconnect_ts = time.monotonic() - 30.0
    reason = watchdog_check(s, ws_gap_halt_seconds=10)
    assert reason and "WS" in reason


def test_clock_drift_triggers_halt():
    s = WatchdogState()
    s.clock_drift_ms = 900
    reason = watchdog_check(s, clock_drift_halt_ms=500)
    assert reason and "clock" in reason
