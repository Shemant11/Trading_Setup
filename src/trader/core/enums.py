"""Enumerations used across the domain.

Kept as plain `str` enums so they serialize cleanly to JSON / DB and can be
compared to broker string codes without conversion.
"""

from __future__ import annotations

from enum import StrEnum


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"       # NSE F&O
    BFO = "BFO"       # BSE F&O
    MCX = "MCX"


class Segment(StrEnum):
    EQUITY = "EQ"
    FUTURES = "FUT"
    OPTIONS = "OPT"
    INDEX = "IDX"
    CURRENCY = "CUR"
    COMMODITY = "COM"


class AssetClass(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    OPTION = "option"
    FUTURE = "future"
    CURRENCY = "currency"
    COMMODITY = "commodity"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


class ProductType(StrEnum):
    """Broker product types across Dhan/Groww terminology.

    MIS  = intraday (Margin Intraday Square-off).
    CNC  = delivery (Cash & Carry).
    NRML = overnight F&O.
    """

    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"
    COVER = "CO"
    BRACKET = "BO"


class OrderStatus(StrEnum):
    """Broker-agnostic order lifecycle states."""

    NEW = "NEW"                # created locally, not yet sent
    PENDING = "PENDING"        # sent, awaiting broker ack
    OPEN = "OPEN"              # ack'd, resting in the book
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }

    @property
    def is_active(self) -> bool:
        return self in {OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


class Timeframe(StrEnum):
    TICK = "tick"
    S1 = "1s"
    S5 = "5s"
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1w"


class StrategyKind(StrEnum):
    EQUITY_ORB = "equity_orb"
    EQUITY_VWAP_MR = "equity_vwap_mr"
    OPTIONS_IRON_CONDOR = "options_iron_condor"
    OPTIONS_DEBIT_SPREAD = "options_debit_spread"
    OPTIONS_EXPIRY_BUTTERFLY = "options_expiry_butterfly"
    SWING_BREAKOUT = "swing_breakout"
