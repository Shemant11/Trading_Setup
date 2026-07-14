"""VWAP mean reversion (CHOP regime)."""

from trader.strategies.equity_vwap_mr.strategy import EquityVWAPMRStrategy
from trader.core.enums import StrategyKind
from trader.strategies.registry import register_strategy

register_strategy(StrategyKind.EQUITY_VWAP_MR, EquityVWAPMRStrategy)

__all__ = ["EquityVWAPMRStrategy"]
