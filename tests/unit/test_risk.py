"""Risk engine tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader.config.loader import AppConfig
from trader.core.domain import Signal
from trader.core.enums import (
    OrderSide,
    OrderType,
    ProductType,
    StrategyKind,
    Validity,
)
from trader.risk import (
    KillSwitch,
    RiskEngine,
    fractional_kelly_size,
    kelly_fraction,
    vol_normalized_size,
)


def _cfg() -> AppConfig:
    return AppConfig.model_validate({
        "capital": {"nav": 1_000_000},
        "risk": {},
    })


def _sig(qty: int = 100, entry: float = 100.0, stop: float = 99.0) -> Signal:
    return Signal(
        id="s1",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="R",
        side=OrderSide.BUY,
        intended_qty=qty,
        entry_price=entry,
        stop_price=stop,
        take_profit_prices=[],
        order_type=OrderType.LIMIT,
        product_type=ProductType.MIS,
        validity=Validity.DAY,
        ts=datetime.now(timezone.utc),
    )


def test_kelly_math():
    assert kelly_fraction(0.6, 1.5) == pytest.approx((1.5 * 0.6 - 0.4) / 1.5)
    assert kelly_fraction(0.0, 1.5) == 0.0
    assert kelly_fraction(1.0, 1.5) == 1.0


def test_fractional_kelly_size_scales_with_nav():
    q1 = fractional_kelly_size(nav=100_000, win_rate=0.6, win_loss_ratio=2.0,
                                fraction=0.25, risk_per_unit=1.0)
    q2 = fractional_kelly_size(nav=1_000_000, win_rate=0.6, win_loss_ratio=2.0,
                                fraction=0.25, risk_per_unit=1.0)
    assert q2 == 10 * q1


def test_vol_normalized_size():
    q = vol_normalized_size(nav=1_000_000, price=100.0,
                            daily_vol_pct=0.02, target_daily_vol_pct=0.005)
    # daily_vol_rupees = 2, target = 5000 → 2500 shares
    assert q == 2500


async def test_engine_approves_normal_signal():
    e = RiskEngine.from_config(_cfg())
    d = await e.check(_sig())
    assert d.approved
    assert d.approved_qty == 100


async def test_engine_rejects_when_kill_switch(tmp_path: Path):
    ks = KillSwitch(halt_file=tmp_path / "halt.lock")
    ks.activate()
    e = RiskEngine.from_config(_cfg(), kill_switch=ks)
    d = await e.check(_sig())
    assert not d.approved
    assert "kill switch" in d.reason.lower()


async def test_engine_rejects_when_daily_loss():
    e = RiskEngine.from_config(_cfg())
    # Trigger daily loss limit
    e.state.loss.daily_pnl = -20_000       # 2% of 1M > 1.5% threshold
    d = await e.check(_sig())
    assert not d.approved


async def test_engine_softbrake_reduces_size():
    e = RiskEngine.from_config(_cfg())
    # 3 consecutive losses should trigger soft brake
    for _ in range(3):
        e.on_trade_closed(StrategyKind.EQUITY_ORB.value, -100)
    d = await e.check(_sig(qty=100))
    assert d.approved
    # size multiplier 0.5 -> 50 approved
    assert d.approved_qty <= 50


async def test_engine_pauses_after_hardpause():
    e = RiskEngine.from_config(_cfg())
    for _ in range(5):
        e.on_trade_closed(StrategyKind.EQUITY_ORB.value, -100)
    d = await e.check(_sig())
    assert not d.approved


async def test_engine_caps_by_single_stock_pct():
    cfg = _cfg()
    e = RiskEngine.from_config(cfg)
    # Very cheap stock, huge qty request should be capped to max_single_stock_pct.
    d = await e.check(_sig(qty=1_000_000, entry=1.0, stop=0.9))
    # 10% of 1M NAV / ₹1 = 100,000 max
    assert d.approved_qty <= 100_000
