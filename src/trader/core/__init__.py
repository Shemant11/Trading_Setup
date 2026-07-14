"""Core domain models and enums shared across all layers.

This is the *only* module that has no dependencies on other trader modules,
by design. Everything else may import `trader.core`; `trader.core` imports
nothing internal.
"""

from trader.core.enums import (
    AssetClass,
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Segment,
    StrategyKind,
    Timeframe,
    Validity,
)
from trader.core.domain import (
    Bar,
    Fill,
    Instrument,
    OptionChainSnapshot,
    OptionQuote,
    Order,
    OrderRequest,
    Position,
    Quote,
    Signal,
    Tick,
    Trade,
)
from trader.core.events import (
    Event,
    KillSwitchEvent,
    OrderEvent,
    RiskDecisionEvent,
    SignalEvent,
    TickEvent,
)

__all__ = [
    # enums
    "AssetClass",
    "Exchange",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "ProductType",
    "Segment",
    "StrategyKind",
    "Timeframe",
    "Validity",
    # domain
    "Bar",
    "Fill",
    "Instrument",
    "OptionChainSnapshot",
    "OptionQuote",
    "Order",
    "OrderRequest",
    "Position",
    "Quote",
    "Signal",
    "Tick",
    "Trade",
    # events
    "Event",
    "KillSwitchEvent",
    "OrderEvent",
    "RiskDecisionEvent",
    "SignalEvent",
    "TickEvent",
]
