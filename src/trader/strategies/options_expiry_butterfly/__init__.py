"""Expiry-day butterfly toward max-pain."""

from trader.core.enums import StrategyKind
from trader.strategies.options_expiry_butterfly.strategy import ExpiryButterflyStrategy
from trader.strategies.registry import register_strategy

register_strategy(StrategyKind.OPTIONS_EXPIRY_BUTTERFLY, ExpiryButterflyStrategy)

__all__ = ["ExpiryButterflyStrategy"]
