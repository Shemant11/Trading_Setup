"""Debit spread strategy (bull-call / bear-put)."""

from trader.core.enums import StrategyKind
from trader.strategies.options_debit_spread.strategy import DebitSpreadStrategy
from trader.strategies.registry import register_strategy

register_strategy(StrategyKind.OPTIONS_DEBIT_SPREAD, DebitSpreadStrategy)

__all__ = ["DebitSpreadStrategy"]
