"""Swing base-breakout strategy."""

from trader.core.enums import StrategyKind
from trader.strategies.registry import register_strategy
from trader.strategies.swing_breakout.strategy import SwingBreakoutStrategy

register_strategy(StrategyKind.SWING_BREAKOUT, SwingBreakoutStrategy)

__all__ = ["SwingBreakoutStrategy"]
