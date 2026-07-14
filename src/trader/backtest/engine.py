"""Event-driven backtest engine.

Iterates bars in chronological order, feeds them to a Strategy, and executes
the resulting Signals via the MarketSimulator. Emits a `BacktestResult` with
equity curve, trade list, and metrics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional, Sequence

from trader.backtest.cost_model import CostModel, DhanCostModel, ImpactModel, LinearImpactModel
from trader.backtest.metrics import PerformanceMetrics, compute_metrics
from trader.backtest.portfolio import PortfolioTracker
from trader.backtest.simulator import MarketSimulator
from trader.core.domain import Bar, Instrument, OrderRequest, Signal
from trader.core.enums import OrderType, ProductType, Validity, OrderSide
from trader.observability.logging import get_logger

logger = get_logger("trader.backtest.engine")


@dataclass
class BacktestResult:
    starting_nav: float
    metrics: PerformanceMetrics
    equity_curve: list[tuple[datetime, float]]
    trade_pnls: list[float]
    per_strategy_pnl: dict[str, float]

    def summary(self) -> str:
        lines = [self.metrics.summary()]
        if self.per_strategy_pnl:
            lines.append("\nPer-strategy PnL:")
            for k, v in sorted(self.per_strategy_pnl.items(), key=lambda x: -x[1]):
                lines.append(f"  {k:<28} ₹{v:,.0f}")
        return "\n".join(lines)


SignalHandler = Callable[[Bar], list[Signal]]


@dataclass
class BacktestEngine:
    """Minimal engine: takes a bar iterator and a strategy callback."""

    starting_nav: float
    instruments: dict[str, Instrument]
    cost_model: CostModel = field(default_factory=DhanCostModel)
    impact_model: ImpactModel = field(default_factory=LinearImpactModel)
    participation_cap: float = 0.10

    def run(
        self,
        bars: Iterable[Bar],
        strategy: SignalHandler,
        *,
        risk_check: Optional[Callable[[Signal], bool]] = None,
        on_bar: Optional[Callable[[Bar], None]] = None,
    ) -> BacktestResult:
        sim = MarketSimulator(
            cost_model=self.cost_model,
            impact_model=self.impact_model,
            participation_cap=self.participation_cap,
        )
        book = PortfolioTracker(starting_nav=self.starting_nav)

        bars_seen = 0
        bars_skipped_no_instrument = 0
        signals_emitted = 0
        signals_risk_rejected = 0
        signals_unfilled = 0
        signals_filled = 0

        for bar in bars:
            bars_seen += 1
            inst = self.instruments.get(bar.instrument_id)
            if inst is None:
                bars_skipped_no_instrument += 1
                continue
            sim.observe_bar(bar)

            # Mark to market before executing new signals.
            book.mark(bar.instrument_id, bar.close, bar.ts_close)

            signals = strategy(bar) or []
            signals_emitted += len(signals)
            for sig in signals:
                if risk_check is not None and not risk_check(sig):
                    signals_risk_rejected += 1
                    continue
                order = _signal_to_order(sig)
                fill, fees = sim.fill(order, inst, bar.ts_close)
                if fill is None:
                    signals_unfilled += 1
                    continue
                signals_filled += 1
                book.on_fill(fill, strategy=sig.strategy, fees=fees, stop_price=sig.stop_price)

            if on_bar:
                on_bar(bar)
            book.total_equity(ts=bar.ts_close)

        logger.info(
            "backtest_run_stats",
            bars_seen=bars_seen,
            bars_skipped_no_instrument=bars_skipped_no_instrument,
            signals_emitted=signals_emitted,
            signals_risk_rejected=signals_risk_rejected,
            signals_unfilled=signals_unfilled,
            signals_filled=signals_filled,
        )

        pnl_by_strategy: dict[str, float] = {}
        for t in book.trades:
            k = t.strategy.value
            pnl_by_strategy[k] = pnl_by_strategy.get(k, 0.0) + t.net_pnl

        metrics = compute_metrics(
            equity_curve=book.equity_curve,
            trade_pnls=[t.net_pnl for t in book.trades],
            starting_nav=self.starting_nav,
        )
        return BacktestResult(
            starting_nav=self.starting_nav,
            metrics=metrics,
            equity_curve=book.equity_curve,
            trade_pnls=[t.net_pnl for t in book.trades],
            per_strategy_pnl=pnl_by_strategy,
        )


def _signal_to_order(sig: Signal) -> OrderRequest:
    return OrderRequest(
        client_order_id=str(uuid.uuid4()),
        strategy=sig.strategy,
        instrument_id=sig.instrument_id,
        side=sig.side,
        qty=sig.intended_qty,
        order_type=sig.order_type,
        product_type=sig.product_type,
        validity=sig.validity,
        limit_price=sig.entry_price if sig.order_type == OrderType.LIMIT else None,
        parent_signal_id=sig.id,
    )
