"""Options analytics tests."""

from __future__ import annotations

import math

import pytest

from trader.core.domain import OptionChainSnapshot, OptionQuote
from trader.options import (
    IVRankTracker,
    bs_greeks,
    bs_price,
    expected_move,
    implied_volatility,
    max_pain,
)
from trader.options.chain import ChainAnalyzer
from trader.risk.greeks_overlay import GreekLimits, GreeksOverlay


def test_bs_call_atm_price_positive():
    p = bs_price(spot=100, strike=100, sigma=0.2, t_years=0.25, r=0.06, kind="CE")
    assert p > 0
    # Put-call parity roughly
    c = bs_price(spot=100, strike=100, sigma=0.2, t_years=0.25, r=0.06, kind="CE")
    pu = bs_price(spot=100, strike=100, sigma=0.2, t_years=0.25, r=0.06, kind="PE")
    # c - p = S - Ke^{-rT}
    lhs = c - pu
    rhs = 100 - 100 * math.exp(-0.06 * 0.25)
    assert lhs == pytest.approx(rhs, rel=1e-2)


def test_bs_greeks_signs():
    g = bs_greeks(spot=100, strike=100, sigma=0.2, t_years=0.1, kind="CE")
    assert 0 < g.delta < 1
    assert g.gamma > 0
    assert g.theta < 0
    assert g.vega > 0
    gp = bs_greeks(spot=100, strike=100, sigma=0.2, t_years=0.1, kind="PE")
    assert -1 < gp.delta < 0


def test_implied_vol_recovers():
    price = bs_price(spot=100, strike=105, sigma=0.25, t_years=0.1, kind="CE")
    iv = implied_volatility(price=price, spot=100, strike=105, t_years=0.1, kind="CE")
    assert iv == pytest.approx(0.25, rel=1e-3)


def test_iv_rank_tracker():
    t = IVRankTracker()
    for v in [0.15, 0.18, 0.20, 0.22, 0.30]:
        t.observe("NIFTY", v)
    # last value 0.30 is the max → rank ≈ 1
    assert t.rank("NIFTY") == pytest.approx(1.0)


def test_expected_move_scales_with_dte():
    em1 = expected_move(spot=23000, atm_iv=0.15, days_to_expiry=1)
    em5 = expected_move(spot=23000, atm_iv=0.15, days_to_expiry=5)
    assert em5 > em1


def _quote(strike, otype, ltp=10.0, oi=1000):
    return OptionQuote(strike=strike, option_type=otype, ltp=ltp, oi=oi, volume=100)


def test_max_pain():
    from datetime import date, datetime, timezone
    snap = OptionChainSnapshot(
        underlying="NIFTY",
        spot=23000,
        expiry=date(2025, 1, 30),
        ts=datetime.now(timezone.utc),
        quotes=[
            _quote(22800, "CE", oi=1000),
            _quote(23000, "CE", oi=3000),
            _quote(23200, "CE", oi=500),
            _quote(22800, "PE", oi=500),
            _quote(23000, "PE", oi=3000),
            _quote(23200, "PE", oi=1000),
        ],
    )
    mp = max_pain(snap)
    assert mp == 23000


def test_chain_analyzer_returns_atm_and_max_pain():
    from datetime import date, datetime, timezone
    a = ChainAnalyzer()
    snap = OptionChainSnapshot(
        underlying="X", spot=100,
        expiry=date(2025, 1, 30),
        ts=datetime.now(timezone.utc),
        quotes=[_quote(95, "CE"), _quote(100, "CE"), _quote(105, "CE"),
                _quote(95, "PE"), _quote(100, "PE"), _quote(105, "PE")],
    )
    r = a.analyze(snap)
    assert r["atm_strike"] == 100
    assert r["max_pain"] is not None


def test_greeks_overlay_rejects_over_delta():
    ov = GreeksOverlay(nav=1_000_000, limits=GreekLimits(max_delta_pct=0.05))
    breach = ov.would_breach(delta_delta=60_000, vega_delta=0, theta_delta=0, gamma_delta=0)
    assert breach == "delta_cap"


def test_greeks_overlay_allows_within_limits():
    ov = GreeksOverlay(nav=1_000_000)
    assert ov.would_breach(delta_delta=50_000, vega_delta=100, theta_delta=100, gamma_delta=100) is None
