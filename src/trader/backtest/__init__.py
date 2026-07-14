"""Event-driven backtest engine.

Single code path with live via dependency injection: strategies produce
Signals, a MarketSimulator plays the role of the broker, and a
PortfolioTracker keeps positions + P&L.
"""

from trader.backtest.simulator import MarketSimulator, SimulatedBroker
from trader.backtest.cost_model import (
    CostModel,
    DhanCostModel,
    ImpactModel,
    LinearImpactModel,
)
from trader.backtest.portfolio import PortfolioTracker
from trader.backtest.engine import BacktestEngine, BacktestResult
from trader.backtest.metrics import PerformanceMetrics, compute_metrics
from trader.backtest.runner import BacktestRunner

__all__ = [
    "MarketSimulator",
    "SimulatedBroker",
    "CostModel",
    "DhanCostModel",
    "ImpactModel",
    "LinearImpactModel",
    "PortfolioTracker",
    "BacktestEngine",
    "BacktestResult",
    "PerformanceMetrics",
    "compute_metrics",
    "BacktestRunner",
]
