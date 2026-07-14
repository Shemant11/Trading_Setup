"""Mapping helpers between our domain enums and Dhan wire strings.

Dhan uses distinct constants for exchange, segment, product, and order type.
Centralising them here means the client code stays clean.
"""

from __future__ import annotations

from trader.core.enums import (
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    Segment,
    Validity,
)


DHAN_EXCHANGE_SEGMENT = {
    (Exchange.NSE, Segment.EQUITY): "NSE_EQ",
    (Exchange.BSE, Segment.EQUITY): "BSE_EQ",
    (Exchange.NFO, Segment.FUTURES): "NSE_FNO",
    (Exchange.NFO, Segment.OPTIONS): "NSE_FNO",
    (Exchange.BFO, Segment.OPTIONS): "BSE_FNO",
    (Exchange.NSE, Segment.INDEX): "IDX_I",
    (Exchange.BSE, Segment.INDEX): "IDX_I",
    (Exchange.MCX, Segment.COMMODITY): "MCX_COMM",
}


DHAN_PRODUCT = {
    ProductType.MIS: "INTRADAY",
    ProductType.CNC: "CNC",
    ProductType.NRML: "MARGIN",
    ProductType.COVER: "CO",
    ProductType.BRACKET: "BO",
}

DHAN_PRODUCT_INV = {v: k for k, v in DHAN_PRODUCT.items()}


DHAN_ORDER_TYPE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP_LOSS: "STOP_LOSS",
    OrderType.STOP_LOSS_MARKET: "STOP_LOSS_MARKET",
}


DHAN_VALIDITY = {
    Validity.DAY: "DAY",
    Validity.IOC: "IOC",
}


DHAN_SIDE = {
    OrderSide.BUY: "BUY",
    OrderSide.SELL: "SELL",
}


DHAN_STATUS = {
    "TRANSIT": OrderStatus.PENDING,
    "PENDING": OrderStatus.PENDING,
    "OPEN": OrderStatus.OPEN,
    "TRADED": OrderStatus.FILLED,
    "FILLED": OrderStatus.FILLED,
    "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
}


def encode_exchange_segment(exchange: Exchange, segment: Segment) -> str:
    key = (exchange, segment)
    if key not in DHAN_EXCHANGE_SEGMENT:
        raise ValueError(f"Unsupported Dhan exchange/segment combo: {exchange}/{segment}")
    return DHAN_EXCHANGE_SEGMENT[key]


def encode_product(p: ProductType) -> str:
    return DHAN_PRODUCT[p]


def decode_status(s: str) -> OrderStatus:
    return DHAN_STATUS.get(s.upper() if s else "", OrderStatus.PENDING)


def encode_timeframe(tf: str) -> str:
    """Dhan intraday supports "1", "5", "15", "25", "60" minute; daily is "D"."""
    mapping = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "1d": "D"}
    if tf not in mapping:
        raise ValueError(f"Timeframe not supported by Dhan API: {tf}")
    return mapping[tf]
