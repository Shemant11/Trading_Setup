"""Iron condor (defined-risk short-vol) strategy for high-IVR range regime."""

from trader.core.enums import StrategyKind
from trader.strategies.options_iron_condor.strategy import IronCondorStrategy
from trader.strategies.registry import register_strategy

register_strategy(StrategyKind.OPTIONS_IRON_CONDOR, IronCondorStrategy)

__all__ = ["IronCondorStrategy"]
