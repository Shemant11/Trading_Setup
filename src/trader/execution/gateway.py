"""Execution gateway.

The single choke-point between strategies and brokers. Responsibilities:

* Convert Signal → OrderRequest (with UUID client_order_id).
* Run Signal through the RiskEngine.
* Route via the SmartOrderRouter.
* Persist every state transition through the Journal.
* Update the RiskEngine's book counters.
* Provide slippage-controlled TWAP slicing for large orders.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from trader.brokers.base import Broker
from trader.brokers.exceptions import BrokerError, OrderRejectedError
from trader.core.domain import Instrument, Order, OrderRequest, Signal
from trader.core.enums import AssetClass, OrderStatus
from trader.execution.router import SmartOrderRouter
from trader.execution.state_machine import OrderStateMachine
from trader.observability.logging import get_logger
from trader.observability.metrics import ORDERS_REJECTED, ORDERS_SENT
from trader.risk.engine import RiskEngine
from trader.storage.journal import Journal

logger = get_logger("trader.execution")


@dataclass
class ExecutionGateway:
    router: SmartOrderRouter
    risk: RiskEngine
    journal: Journal
    state_machine: OrderStateMachine = field(default_factory=OrderStateMachine)
    slippage_participation_threshold: float = 0.005     # 0.5% of 1-min ADV
    twap_slice_seconds: float = 5.0
    twap_max_seconds: float = 120.0
    _open_orders: dict[str, Order] = field(default_factory=dict)
    instruments: dict[str, Instrument] = field(default_factory=dict)

    def register_instrument(self, inst: Instrument) -> None:
        self.instruments[inst.security_id] = inst

    # ---------- signal -> order -------------------------------------------

    async def submit(self, signal: Signal) -> Optional[Order]:
        decision = await self.risk.check(signal)
        await self.journal.record_signal(
            signal, approved=decision.approved, reason=decision.reason
        )
        if not decision.approved:
            return None
        inst = self.instruments.get(signal.instrument_id)
        if inst is None:
            logger.warning("execution_missing_instrument", instrument=signal.instrument_id)
            return None

        req = OrderRequest(
            client_order_id=str(uuid.uuid4()),
            strategy=signal.strategy,
            instrument_id=signal.instrument_id,
            side=signal.side,
            qty=decision.approved_qty,
            order_type=signal.order_type,
            product_type=signal.product_type,
            validity=signal.validity,
            limit_price=signal.entry_price if signal.order_type.value == "LIMIT" else None,
            parent_signal_id=signal.id,
            exchange=inst.exchange,
        )
        broker = await self.router.choose(req, inst.asset_class)
        if broker is None:
            logger.error("execution_no_broker", instrument=signal.instrument_id)
            ORDERS_REJECTED.labels(
                broker="none", strategy=signal.strategy.value, reason_class="no_route"
            ).inc()
            return None
        order = _initial_order(req, broker.capabilities.name)
        await self.journal.upsert_order(order)
        self._open_orders[order.client_order_id] = order

        # Decide slicing (Phase 2 basic: threshold on qty vs a proxy participation).
        if self._needs_slicing(req):
            asyncio.create_task(self._twap_slice(order, req, broker, inst.asset_class))
        else:
            await self._send(order, req, broker, inst.asset_class)
        self.risk.commit(signal, decision.approved_qty)
        return order

    async def _send(
        self, order: Order, req: OrderRequest, broker: Broker, asset: AssetClass
    ) -> None:
        try:
            self.state_machine.transition(order, OrderStatus.PENDING)
            await self.journal.upsert_order(order)
            ack = await broker.place_order(req)
            order.broker_order_id = ack.broker_order_id
            self.state_machine.transition(order, ack.status)
            await self.journal.upsert_order(order)
            ORDERS_SENT.labels(broker=broker.capabilities.name, strategy=order.strategy.value).inc()
        except OrderRejectedError as e:
            self.state_machine.transition(order, OrderStatus.REJECTED, reason=str(e))
            await self.journal.upsert_order(order)
            ORDERS_REJECTED.labels(
                broker=broker.capabilities.name,
                strategy=order.strategy.value,
                reason_class="structural",
            ).inc()
        except BrokerError as e:
            self.state_machine.transition(order, OrderStatus.REJECTED, reason=str(e))
            await self.journal.upsert_order(order)
            ORDERS_REJECTED.labels(
                broker=broker.capabilities.name,
                strategy=order.strategy.value,
                reason_class="transient",
            ).inc()

    def _needs_slicing(self, req: OrderRequest) -> bool:
        # Placeholder heuristic; Phase 2+ hooks up real ADV lookups.
        return req.qty >= 10000

    async def _twap_slice(
        self, order: Order, req: OrderRequest, broker: Broker, asset: AssetClass
    ) -> None:
        total = req.qty
        slice_qty = max(1, total // 10)
        remaining = total
        while remaining > 0:
            this = min(slice_qty, remaining)
            sliced = _copy_request(req, qty=this)
            sub = _initial_order(sliced, broker.capabilities.name, parent_id=order.client_order_id)
            await self.journal.upsert_order(sub)
            await self._send(sub, sliced, broker, asset)
            remaining -= this
            if remaining > 0:
                await asyncio.sleep(self.twap_slice_seconds)

    # ---------- broker callbacks ------------------------------------------

    async def on_broker_update(self, update) -> None:
        """Consume an OrderUpdate pushed by broker WS or polling."""
        coid = update.client_order_id
        if not coid:
            return
        order = self._open_orders.get(coid)
        if order is None:
            got = await self.journal.get_order(coid)
            if not got:
                return
            # Rehydrate minimally
            order = Order(
                client_order_id=coid,
                broker_order_id=update.broker_order_id,
                strategy=order.strategy if order else _fallback_strategy(),  # keep type
                instrument_id=got["instrument_id"],
                side=got["side"],
                qty=got["qty"],
                order_type=got["order_type"],
                product_type=got["product_type"],
                status=OrderStatus(got["status"]),
                ts_created=got["ts_created"],
                ts_updated=datetime.now(timezone.utc),
            )
        try:
            self.state_machine.transition(order, update.status, reason=update.reject_reason)
        except Exception as e:  # noqa: BLE001
            logger.warning("execution_bad_transition", error=str(e))
            return
        order.filled_qty = update.filled_qty
        order.avg_fill_price = update.avg_fill_price
        order.reject_reason = update.reject_reason
        await self.journal.upsert_order(order)
        if order.status.is_terminal:
            self._open_orders.pop(coid, None)


def _initial_order(req: OrderRequest, broker: str, parent_id: str | None = None) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        client_order_id=req.client_order_id,
        strategy=req.strategy,
        instrument_id=req.instrument_id,
        side=req.side,
        qty=req.qty,
        order_type=req.order_type,
        product_type=req.product_type,
        validity=req.validity,
        limit_price=req.limit_price,
        trigger_price=req.trigger_price,
        status=OrderStatus.NEW,
        broker=broker,
        ts_created=now,
        ts_updated=now,
        parent_signal_id=parent_id or req.parent_signal_id,
    )


def _copy_request(req: OrderRequest, qty: int) -> OrderRequest:
    return OrderRequest(
        client_order_id=str(uuid.uuid4()),
        strategy=req.strategy,
        instrument_id=req.instrument_id,
        side=req.side,
        qty=qty,
        order_type=req.order_type,
        product_type=req.product_type,
        validity=req.validity,
        limit_price=req.limit_price,
        trigger_price=req.trigger_price,
        parent_signal_id=req.parent_signal_id,
        exchange=req.exchange,
    )


def _fallback_strategy():
    from trader.core.enums import StrategyKind
    return StrategyKind.EQUITY_ORB
