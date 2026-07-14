"""Order state machine tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.core.domain import Order
from trader.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    StrategyKind,
)
from trader.execution.state_machine import OrderStateMachine, OrderStateMachineError


def _order() -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        client_order_id="c1",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="X",
        side=OrderSide.BUY,
        qty=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
        status=OrderStatus.NEW,
        ts_created=now,
        ts_updated=now,
    )


def test_valid_transitions():
    sm = OrderStateMachine()
    o = _order()
    sm.transition(o, OrderStatus.PENDING)
    sm.transition(o, OrderStatus.OPEN)
    sm.transition(o, OrderStatus.PARTIALLY_FILLED)
    sm.transition(o, OrderStatus.FILLED)
    assert o.status == OrderStatus.FILLED


def test_illegal_transition_raises():
    sm = OrderStateMachine()
    o = _order()
    sm.transition(o, OrderStatus.PENDING)
    sm.transition(o, OrderStatus.FILLED)
    with pytest.raises(OrderStateMachineError):
        sm.transition(o, OrderStatus.OPEN)     # can't go back


def test_reject_stores_reason():
    sm = OrderStateMachine()
    o = _order()
    sm.transition(o, OrderStatus.REJECTED, reason="margin insufficient")
    assert o.reject_reason == "margin insufficient"
    assert o.status == OrderStatus.REJECTED
