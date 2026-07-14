"""Opening Range Breakout + Auction Confirmation strategy."""

from trader.strategies.equity_orb.strategy import EquityORBStrategy
from trader.core.enums import StrategyKind
from trader.strategies.registry import register_strategy

register_strategy(StrategyKind.EQUITY_ORB, EquityORBStrategy)

__all__ = ["EquityORBStrategy"]
