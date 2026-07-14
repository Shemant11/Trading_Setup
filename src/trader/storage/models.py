"""SQLAlchemy ORM models (journal, ledger, event log).

Uses SQLAlchemy 2.0 typed API. Compatible with SQLite (default) and
Postgres via drop-in URL swap. All timestamps are UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Common declarative base."""


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_status_ts", "status", "ts_updated"),
        Index("ix_orders_strategy", "strategy"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    strategy: Mapped[str] = mapped_column(String(64))
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(Integer)
    filled_qty: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[Optional[float]] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(16))
    product_type: Mapped[str] = mapped_column(String(16))
    validity: Mapped[str] = mapped_column(String(8), default="DAY")
    limit_price: Mapped[Optional[float]] = mapped_column(Float)
    trigger_price: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="NEW")
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    broker: Mapped[Optional[str]] = mapped_column(String(32))
    ts_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ts_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    tag: Mapped[Optional[str]] = mapped_column(String(64))
    parent_signal_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)


class FillRow(Base):
    __tablename__ = "fills"
    __table_args__ = (Index("ix_fills_client_order", "client_order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fill_id: Mapped[str] = mapped_column(String(64), unique=True)
    client_order_id: Mapped[str] = mapped_column(String(64), index=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    broker: Mapped[Optional[str]] = mapped_column(String(32))
    fees: Mapped[float] = mapped_column(Float, default=0.0)


class TradeRow(Base):
    __tablename__ = "trades"
    __table_args__ = (Index("ix_trades_strategy_ts", "strategy", "exit_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True)
    strategy: Mapped[str] = mapped_column(String(64))
    instrument_id: Mapped[str] = mapped_column(String(64), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gross_pnl: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float)
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    tag: Mapped[Optional[str]] = mapped_column(String(64))


class PositionRow(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("instrument_id", name="uq_positions_instrument"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    last_price: Mapped[Optional[float]] = mapped_column(Float)
    ts_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SignalRow(Base):
    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_strategy_ts", "strategy", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(64), unique=True)
    strategy: Mapped[str] = mapped_column(String(64))
    instrument_id: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(8))
    intended_qty: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_price: Mapped[float] = mapped_column(Float)
    take_profit_prices: Mapped[Optional[list]] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved: Mapped[Optional[bool]] = mapped_column(Boolean)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSON)


class RunLogRow(Base):
    __tablename__ = "run_log"
    __table_args__ = (Index("ix_run_log_ts", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    kind: Mapped[str] = mapped_column(String(32))     # boot, shutdown, halt, resume, reconcile
    detail: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSON)


class RiskEventRow(Base):
    __tablename__ = "risk_events"
    __table_args__ = (Index("ix_risk_events_ts", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    layer: Mapped[str] = mapped_column(String(16))   # 1..4
    action: Mapped[str] = mapped_column(String(32))  # reject, halve, pause, halt, resume
    reason: Mapped[str] = mapped_column(Text)
    strategy: Mapped[Optional[str]] = mapped_column(String(64))
    signal_id: Mapped[Optional[str]] = mapped_column(String(64))
