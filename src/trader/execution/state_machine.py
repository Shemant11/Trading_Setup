"""Order state machine.

Encodes the allowed transitions so bugs (e.g. FILLED -> OPEN) fail fast.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from trader.core.domain import Order
from trader.core.enums import OrderStatus


ALLOWED = {
    OrderStatus.NEW: {OrderStatus.PENDING, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.PENDING: {
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.OPEN: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.EXPIRED: set(),
}


@dataclass
class OrderTransition:
    from_status: OrderStatus
    to_status: OrderStatus
    ts: datetime
    reason: Optional[str] = None


class OrderStateMachineError(RuntimeError):
    pass


class OrderStateMachine:
    """Applies transitions to a mutable `Order`."""

    def __init__(self) -> None:
        self.transitions: dict[str, list[OrderTransition]] = {}

    def transition(self, order: Order, to_status: OrderStatus, *, reason: Optional[str] = None) -> None:
        allowed = ALLOWED.get(order.status, set())
        if to_status not in allowed and to_status != order.status:
            raise OrderStateMachineError(
                f"illegal transition {order.status} -> {to_status} for order "
                f"{order.client_order_id}"
            )
        now = datetime.now(timezone.utc)
        t = OrderTransition(from_status=order.status, to_status=to_status, ts=now, reason=reason)
        self.transitions.setdefault(order.client_order_id, []).append(t)
        order.status = to_status
        if reason and to_status == OrderStatus.REJECTED:
            order.reject_reason = reason
        order.ts_updated = now
