"""Performance metrics.

Standard set: Sharpe / Sortino / Calmar / Max DD / DD duration / CAGR /
Win rate / Profit factor / Expectancy / Ulcer / Tail ratio.

Assumes daily equity samples for CAGR and volatility scaling; intraday
sampling degrades to a plain arithmetic Sharpe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import numpy as np


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    starting_nav: float
    ending_nav: float
    cagr: float
    total_return_pct: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    volatility_annual: float
    win_rate: float
    profit_factor: float
    expectancy: float
    ulcer_index: float
    tail_ratio: float
    trades: int
    avg_trade_pnl: float
    best_trade: float
    worst_trade: float

    def summary(self) -> str:
        lines = [
            "Backtest results",
            f"  starting NAV     : ₹{self.starting_nav:,.0f}",
            f"  ending NAV       : ₹{self.ending_nav:,.0f}",
            f"  total return     : {self.total_return_pct:.2f}%",
            f"  CAGR             : {self.cagr * 100:.2f}%",
            f"  Sharpe (ann.)    : {self.sharpe:.2f}",
            f"  Sortino (ann.)   : {self.sortino:.2f}",
            f"  Calmar           : {self.calmar:.2f}",
            f"  Max drawdown     : {self.max_drawdown_pct:.2f}%  "
            f"({self.max_drawdown_duration_days} days)",
            f"  Ulcer index      : {self.ulcer_index:.2f}",
            f"  Volatility (ann.): {self.volatility_annual * 100:.2f}%",
            f"  Trades           : {self.trades}   win% {self.win_rate*100:.1f}%   "
            f"PF {self.profit_factor:.2f}   E {self.expectancy:,.0f}",
            f"  Tail ratio       : {self.tail_ratio:.2f}",
            f"  Best / Worst     : {self.best_trade:,.0f} / {self.worst_trade:,.0f}",
        ]
        return "\n".join(lines)


def compute_metrics(
    equity_curve: Sequence[tuple[datetime, float]],
    trade_pnls: Sequence[float],
    starting_nav: float,
) -> PerformanceMetrics:
    if not equity_curve:
        return _empty(starting_nav)
    dates = [t for t, _ in equity_curve]
    eq = np.array([v for _, v in equity_curve], dtype=float)
    end_nav = float(eq[-1])
    total_ret = (end_nav / starting_nav - 1.0) * 100.0

    # Downsample to daily last-value for CAGR / vol / Sharpe.
    daily = _downsample_daily(equity_curve)
    daily_arr = np.array([v for _, v in daily], dtype=float)
    if len(daily_arr) >= 2:
        daily_ret = np.diff(daily_arr) / daily_arr[:-1]
        vol_ann = float(np.std(daily_ret, ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
        mean_ann = float(np.mean(daily_ret) * TRADING_DAYS_PER_YEAR)
        sharpe = (mean_ann / vol_ann) if vol_ann > 0 else 0.0
        downside = daily_ret[daily_ret < 0]
        sortino = 0.0
        if downside.size > 0:
            ds_vol = float(np.std(downside, ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
            sortino = (mean_ann / ds_vol) if ds_vol > 0 else 0.0
        years = max((daily[-1][0] - daily[0][0]).days / 365.25, 1e-6)
        cagr = (daily_arr[-1] / daily_arr[0]) ** (1 / years) - 1 if daily_arr[0] > 0 else 0.0
    else:
        vol_ann = 0.0
        sharpe = 0.0
        sortino = 0.0
        cagr = 0.0

    max_dd, max_dd_days = _drawdown(eq, dates)
    calmar = (cagr / abs(max_dd / 100.0)) if max_dd < 0 else 0.0
    ulcer = _ulcer(eq)

    if trade_pnls:
        pnls = np.array(trade_pnls, dtype=float)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = len(wins) / len(pnls)
        pf = (float(wins.sum()) / -float(losses.sum())) if losses.size > 0 and losses.sum() < 0 else float("inf")
        expectancy = float(pnls.mean())
        best = float(pnls.max())
        worst = float(pnls.min())
        avg_trade = expectancy
        n_trades = len(pnls)
        # Tail ratio = |p95| / |p5|
        p95 = float(np.abs(np.percentile(pnls, 95)))
        p5 = float(np.abs(np.percentile(pnls, 5)))
        tail_ratio = p95 / p5 if p5 > 0 else 0.0
    else:
        win_rate = pf = expectancy = best = worst = avg_trade = tail_ratio = 0.0
        n_trades = 0

    return PerformanceMetrics(
        starting_nav=starting_nav,
        ending_nav=end_nav,
        cagr=cagr,
        total_return_pct=total_ret,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_days,
        volatility_annual=vol_ann,
        win_rate=win_rate,
        profit_factor=pf,
        expectancy=expectancy,
        ulcer_index=ulcer,
        tail_ratio=tail_ratio,
        trades=n_trades,
        avg_trade_pnl=avg_trade,
        best_trade=best,
        worst_trade=worst,
    )


def _empty(starting: float) -> PerformanceMetrics:
    return PerformanceMetrics(
        starting_nav=starting, ending_nav=starting,
        cagr=0, total_return_pct=0, sharpe=0, sortino=0, calmar=0,
        max_drawdown_pct=0, max_drawdown_duration_days=0,
        volatility_annual=0, win_rate=0, profit_factor=0, expectancy=0,
        ulcer_index=0, tail_ratio=0, trades=0,
        avg_trade_pnl=0, best_trade=0, worst_trade=0,
    )


def _drawdown(eq: np.ndarray, dates: list[datetime]) -> tuple[float, int]:
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max * 100.0
    worst_idx = int(np.argmin(dd))
    peak_idx = int(np.argmax(eq[: worst_idx + 1])) if worst_idx > 0 else 0
    days = (dates[worst_idx] - dates[peak_idx]).days
    return float(dd.min()), int(days)


def _ulcer(eq: np.ndarray) -> float:
    running_max = np.maximum.accumulate(eq)
    dd_pct = (eq - running_max) / running_max * 100.0
    return float(math.sqrt((dd_pct**2).mean()))


def _downsample_daily(
    curve: Sequence[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    if not curve:
        return []
    by_day: dict[str, tuple[datetime, float]] = {}
    for t, v in curve:
        key = t.date().isoformat()
        by_day[key] = (t, v)
    return sorted(by_day.values(), key=lambda x: x[0])
