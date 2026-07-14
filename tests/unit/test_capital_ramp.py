"""Capital ramp controller tests."""

from __future__ import annotations

from datetime import date, timedelta

from trader.risk.capital_ramp import CapitalRampController, LiveStats


def test_initial_stage_is_10_pct():
    c = CapitalRampController()
    assert c.current_fraction == 0.10


def test_cannot_promote_before_min_days():
    c = CapitalRampController(stage_started=date.today())
    stats = LiveStats(trades=100, win_rate=0.60, max_dd_pct=-2.0, avg_slippage_bps=8.0)
    ok, _ = c.can_promote(stats)
    assert not ok


def test_promote_after_gate_pass():
    c = CapitalRampController(stage_started=date.today() - timedelta(days=10))
    stats = LiveStats(trades=100, win_rate=0.60, max_dd_pct=-2.0, avg_slippage_bps=8.0)
    ok, _ = c.can_promote(stats, today=date.today())
    assert ok
    c.promote()
    assert c.current_fraction == 0.25


def test_pause_blocks_promotion():
    c = CapitalRampController(stage_started=date.today() - timedelta(days=30))
    c.pause("investigating slippage")
    stats = LiveStats(trades=100, win_rate=0.60, max_dd_pct=-2.0, avg_slippage_bps=8.0)
    ok, reason = c.can_promote(stats)
    assert not ok
    assert "investigat" in reason


def test_dd_breach_blocks():
    c = CapitalRampController(stage_started=date.today() - timedelta(days=10))
    stats = LiveStats(trades=100, win_rate=0.60, max_dd_pct=-8.0, avg_slippage_bps=8.0)
    ok, reason = c.can_promote(stats)
    assert not ok
    assert "DD" in reason
