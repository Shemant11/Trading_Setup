"""Broker adapters: unified async interface + Dhan + Groww implementations."""

from trader.brokers.base import (
    Broker,
    BrokerCapabilities,
    HistoricalBar,
    MarginInfo,
    OrderAck,
    OrderUpdate,
    PositionSnapshot,
    TickCallback,
    WSMessage,
)
from trader.brokers.exceptions import (
    BrokerError,
    OrderRejectedError,
    AuthError,
    RateLimitError,
    TransientBrokerError,
)
from trader.brokers.dhan.client import DhanClient
from trader.brokers.groww.client import GrowwClient

__all__ = [
    "Broker",
    "BrokerCapabilities",
    "HistoricalBar",
    "MarginInfo",
    "OrderAck",
    "OrderUpdate",
    "PositionSnapshot",
    "TickCallback",
    "WSMessage",
    "BrokerError",
    "OrderRejectedError",
    "AuthError",
    "RateLimitError",
    "TransientBrokerError",
    "DhanClient",
    "GrowwClient",
]
