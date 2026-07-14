"""End-to-end backtest tests with a deterministic synthetic strategy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

import pytest

from trader.backtest import BacktestEngine, DhanCostModel, LinearImpactModel
from trader.core.domain import Bar, Instrument, Signal
from trader.core.enums import (
    AssetClass,
    Exchange,
    OrderSide,
    OrderType,
    ProductType,
    Segment,
    StrategyKind,
    Validity,
)


def _reliance() -> Instrument:
    return Instrument(
        security_id="R",
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        segment=Segment.EQUITY,
        asset_class=AssetClass.EQUITY,
    )


def _bars(n: int, price: float = 100.0, step: float = 1.0) -> list[Bar]:
    out = []
    t = datetime(2025, 3, 14, 3, 45, tzinfo=timezone.utc)
    for i in range(n):
        p = price + i * step
        out.append(
            Bar(
                instrument_id="R",
                ts_open=t + timedelta(minutes=i * 5),
                ts_close=t + timedelta(minutes=(i + 1) * 5),
                timeframe="5m",
                open=p,
                high=p + 0.5,
                low=p - 0.5,
                close=p,
                volume=10000,
                vwap=p,
            )
        )
    return out


def _entry_only_strategy(entry_idx: int, exit_idx: int):
    """Yield a buy on bar `entry_idx`, and a sell on bar `exit_idx`."""
    bar_num = {"n": -1}

    def _fn(bar: Bar):
        bar_num["n"] += 1
        i = bar_num["n"]
        signals = []
        if i == entry_idx:
            signals.append(_sig(bar, side=OrderSide.BUY, qty=100))
        elif i == exit_idx:
            signals.append(_sig(bar, side=OrderSide.SELL, qty=100))
        return signals

    return _fn


def _sig(bar: Bar, side: OrderSide, qty: int) -> Signal:
    return Signal(
        id=f"s-{bar.ts_open.isoformat()}",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id=bar.instrument_id,
        side=side,
        intended_qty=qty,
        entry_price=bar.close,
        stop_price=bar.close * (0.99 if side == OrderSide.BUY else 1.01),
        take_profit_prices=[],
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
        validity=Validity.DAY,
        ts=bar.ts_open,
    )


def test_backtest_profitable_trend():
    engine = BacktestEngine(
        starting_nav=1_000_000,
        instruments={"R": _reliance()},
        cost_model=DhanCostModel(),
        impact_model=LinearImpactModel(k_bps=1.0),
    )
    bars = _bars(20, price=100.0, step=1.0)  # 100 -> 119
    result = engine.run(bars, _entry_only_strategy(entry_idx=1, exit_idx=15))
    assert result.metrics.trades == 1
    assert result.metrics.best_trade > 0
    # Profitable trend should be positive net of costs on 100 share trade.
    assert result.metrics.expectancy > 0


def test_backtest_costs_reduce_pnl():
    high_cost = BacktestEngine(
        starting_nav=1_000_000,
        instruments={"R": _reliance()},
        cost_model=DhanCostModel(equity_intraday_brokerage=200.0, equity_intraday_pct=0.001),
        impact_model=LinearImpactModel(k_bps=50.0),
    )
    low_cost = BacktestEngine(
        starting_nav=1_000_000,
        instruments={"R": _reliance()},
        cost_model=DhanCostModel(equity_intraday_brokerage=1.0, equity_intraday_pct=0.00001),
        impact_model=LinearImpactModel(k_bps=1.0),
    )
    bars = _bars(20, price=100.0, step=1.0)
    r_high = high_cost.run(bars, _entry_only_strategy(1, 15))
    r_low = low_cost.run(bars, _entry_only_strategy(1, 15))
    assert r_low.metrics.expectancy > r_high.metrics.expectancy


def test_backtest_zero_signals_zero_trades():
    engine = BacktestEngine(starting_nav=100_000, instruments={"R": _reliance()})
    bars = _bars(5)
    result = engine.run(bars, lambda _bar: [])
    assert result.metrics.trades == 0
    assert result.metrics.ending_nav == pytest.approx(result.starting_nav)
