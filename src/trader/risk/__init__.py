"""Four-layer risk engine + kill switch.

Every order MUST pass through `RiskEngine.check()`. Strategies never call the
execution gateway directly.
"""

from trader.risk.sizing import (
    fractional_kelly_size,
    kelly_fraction,
    vol_normalized_size,
)
from trader.risk.limits import (
    BookLimits,
    LimitState,
    LimitViolation,
    LossLimits,
    StrategyLimits,
)
from trader.risk.kill_switch import KillSwitch
from trader.risk.engine import RiskDecision, RiskEngine

__all__ = [
    "fractional_kelly_size",
    "kelly_fraction",
    "vol_normalized_size",
    "BookLimits",
    "LimitState",
    "LimitViolation",
    "LossLimits",
    "StrategyLimits",
    "KillSwitch",
    "RiskDecision",
    "RiskEngine",
]
