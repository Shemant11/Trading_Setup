"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("client_order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("broker_order_id", sa.String(64)),
        sa.Column("exchange_order_id", sa.String(64)),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("filled_qty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Float),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("product_type", sa.String(16), nullable=False),
        sa.Column("validity", sa.String(8), server_default="DAY"),
        sa.Column("limit_price", sa.Float),
        sa.Column("trigger_price", sa.Float),
        sa.Column("status", sa.String(24), server_default="NEW"),
        sa.Column("reject_reason", sa.Text),
        sa.Column("broker", sa.String(32)),
        sa.Column("ts_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tag", sa.String(64)),
        sa.Column("parent_signal_id", sa.String(64)),
    )
    op.create_index("ix_orders_client_order_id", "orders", ["client_order_id"])
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"])
    op.create_index("ix_orders_instrument_id", "orders", ["instrument_id"])
    op.create_index("ix_orders_status_ts", "orders", ["status", "ts_updated"])
    op.create_index("ix_orders_strategy", "orders", ["strategy"])

    op.create_table(
        "fills",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("fill_id", sa.String(64), nullable=False, unique=True),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("broker_order_id", sa.String(64)),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broker", sa.String(32)),
        sa.Column("fees", sa.Float, server_default="0"),
    )
    op.create_index("ix_fills_client_order", "fills", ["client_order_id"])
    op.create_index("ix_fills_instrument_id", "fills", ["instrument_id"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trade_id", sa.String(64), nullable=False, unique=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=False),
        sa.Column("entry_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gross_pnl", sa.Float, nullable=False),
        sa.Column("fees", sa.Float, server_default="0"),
        sa.Column("net_pnl", sa.Float, nullable=False),
        sa.Column("r_multiple", sa.Float),
        sa.Column("tag", sa.String(64)),
    )
    op.create_index("ix_trades_strategy_ts", "trades", ["strategy", "exit_ts"])
    op.create_index("ix_trades_instrument_id", "trades", ["instrument_id"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.String(64), nullable=False, unique=True),
        sa.Column("qty", sa.Integer, server_default="0"),
        sa.Column("avg_price", sa.Float, server_default="0"),
        sa.Column("realized_pnl", sa.Float, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float, server_default="0"),
        sa.Column("last_price", sa.Float),
        sa.Column("ts_updated", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("signal_id", sa.String(64), nullable=False, unique=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("intended_qty", sa.Integer, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("stop_price", sa.Float, nullable=False),
        sa.Column("take_profit_prices", sa.JSON),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved", sa.Boolean),
        sa.Column("reject_reason", sa.Text),
        sa.Column("metadata", sa.JSON),
    )
    op.create_index("ix_signals_strategy_ts", "signals", ["strategy", "ts"])

    op.create_table(
        "run_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("metadata", sa.JSON),
    )
    op.create_index("ix_run_log_ts", "run_log", ["ts"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("layer", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("strategy", sa.String(64)),
        sa.Column("signal_id", sa.String(64)),
    )
    op.create_index("ix_risk_events_ts", "risk_events", ["ts"])


def downgrade() -> None:
    for tbl in (
        "risk_events",
        "run_log",
        "signals",
        "positions",
        "trades",
        "fills",
        "orders",
    ):
        op.drop_table(tbl)
