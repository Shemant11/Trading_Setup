"""Trade journal — the append-only source of truth.

Every state-changing event goes through `Journal.record_*`. Reads are for
reporting and reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from trader.core.domain import Fill, Order, Signal, Trade
from trader.observability.logging import get_logger
from trader.storage.database import Database
from trader.storage.models import (
    FillRow,
    OrderRow,
    PositionRow,
    RiskEventRow,
    RunLogRow,
    SignalRow,
    TradeRow,
)

logger = get_logger("trader.storage.journal")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Journal:
    db: Database

    # ---- orders ----------------------------------------------------------

    async def upsert_order(self, order: Order) -> None:
        async with self.db.session() as session:
            existing = await session.scalar(
                select(OrderRow).where(OrderRow.client_order_id == order.client_order_id)
            )
            if existing is None:
                session.add(_order_to_row(order))
                return
            _apply_order_update(existing, order)

    async def get_order(self, client_order_id: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            row = await session.scalar(
                select(OrderRow).where(OrderRow.client_order_id == client_order_id)
            )
            return _row_to_dict(row) if row else None

    async def list_open_orders(self) -> list[dict[str, Any]]:
        active = ("PENDING", "OPEN", "PARTIALLY_FILLED")
        async with self.db.session() as session:
            rows = (await session.scalars(select(OrderRow).where(OrderRow.status.in_(active)))).all()
            return [_row_to_dict(r) for r in rows]

    # ---- fills -----------------------------------------------------------

    async def record_fill(self, fill: Fill) -> None:
        async with self.db.session() as session:
            session.add(
                FillRow(
                    fill_id=fill.fill_id,
                    client_order_id=fill.client_order_id,
                    broker_order_id=fill.broker_order_id,
                    instrument_id=fill.instrument_id,
                    side=fill.side.value,
                    qty=fill.qty,
                    price=fill.price,
                    ts=fill.ts,
                    broker=fill.broker,
                    fees=fill.fees,
                )
            )

    # ---- trades ----------------------------------------------------------

    async def record_trade(self, trade: Trade) -> None:
        async with self.db.session() as session:
            session.add(
                TradeRow(
                    trade_id=trade.trade_id,
                    strategy=trade.strategy.value,
                    instrument_id=trade.instrument_id,
                    side=trade.side.value,
                    qty=trade.qty,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    entry_ts=trade.entry_ts,
                    exit_ts=trade.exit_ts,
                    gross_pnl=trade.gross_pnl,
                    fees=trade.fees,
                    net_pnl=trade.net_pnl,
                    r_multiple=trade.r_multiple,
                    tag=trade.tag,
                )
            )

    # ---- signals ---------------------------------------------------------

    async def record_signal(
        self, signal: Signal, approved: Optional[bool] = None, reason: Optional[str] = None
    ) -> None:
        async with self.db.session() as session:
            session.add(
                SignalRow(
                    signal_id=signal.id,
                    strategy=signal.strategy.value,
                    instrument_id=signal.instrument_id,
                    side=signal.side.value,
                    intended_qty=signal.intended_qty,
                    entry_price=signal.entry_price,
                    stop_price=signal.stop_price,
                    take_profit_prices=signal.take_profit_prices,
                    ts=signal.ts,
                    approved=approved,
                    reject_reason=reason,
                    meta=signal.metadata or None,
                )
            )

    # ---- risk events -----------------------------------------------------

    async def record_risk_event(
        self,
        *,
        layer: str,
        action: str,
        reason: str,
        strategy: Optional[str] = None,
        signal_id: Optional[str] = None,
    ) -> None:
        async with self.db.session() as session:
            session.add(
                RiskEventRow(
                    layer=layer, action=action, reason=reason,
                    strategy=strategy, signal_id=signal_id,
                )
            )

    # ---- run log ---------------------------------------------------------

    async def record_run_event(
        self, kind: str, detail: Optional[str] = None, meta: Optional[dict] = None
    ) -> None:
        async with self.db.session() as session:
            session.add(RunLogRow(kind=kind, detail=detail, meta=meta))

    # ---- positions -------------------------------------------------------

    async def upsert_position(
        self,
        instrument_id: str,
        qty: int,
        avg_price: float,
        realized_pnl: float,
        unrealized_pnl: float,
        last_price: Optional[float] = None,
    ) -> None:
        async with self.db.session() as session:
            row = await session.scalar(
                select(PositionRow).where(PositionRow.instrument_id == instrument_id)
            )
            if row is None:
                session.add(
                    PositionRow(
                        instrument_id=instrument_id,
                        qty=qty,
                        avg_price=avg_price,
                        realized_pnl=realized_pnl,
                        unrealized_pnl=unrealized_pnl,
                        last_price=last_price,
                        ts_updated=_utcnow(),
                    )
                )
                return
            row.qty = qty
            row.avg_price = avg_price
            row.realized_pnl = realized_pnl
            row.unrealized_pnl = unrealized_pnl
            row.last_price = last_price
            row.ts_updated = _utcnow()

    async def list_positions(self) -> list[dict[str, Any]]:
        async with self.db.session() as session:
            rows = (await session.scalars(select(PositionRow))).all()
            return [_row_to_dict(r) for r in rows]


def _order_to_row(o: Order) -> OrderRow:
    return OrderRow(
        client_order_id=o.client_order_id,
        broker_order_id=o.broker_order_id,
        exchange_order_id=o.exchange_order_id,
        strategy=o.strategy.value,
        instrument_id=o.instrument_id,
        side=o.side.value,
        qty=o.qty,
        filled_qty=o.filled_qty,
        avg_fill_price=o.avg_fill_price,
        order_type=o.order_type.value,
        product_type=o.product_type.value,
        validity=o.validity.value,
        limit_price=o.limit_price,
        trigger_price=o.trigger_price,
        status=o.status.value,
        reject_reason=o.reject_reason,
        broker=o.broker,
        ts_created=o.ts_created,
        ts_updated=o.ts_updated,
        tag=o.tag,
        parent_signal_id=o.parent_signal_id,
    )


def _apply_order_update(row: OrderRow, o: Order) -> None:
    row.broker_order_id = o.broker_order_id
    row.exchange_order_id = o.exchange_order_id
    row.filled_qty = o.filled_qty
    row.avg_fill_price = o.avg_fill_price
    row.status = o.status.value
    row.reject_reason = o.reject_reason
    row.broker = o.broker
    row.ts_updated = o.ts_updated


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
