"""Tests for the journal + SQL layer using an in-memory SQLite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.core.domain import Fill, Order, Trade
from trader.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    StrategyKind,
)
from trader.storage import Journal, create_database


@pytest.fixture()
async def journal(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/j.db"
    db = create_database(url)
    await db.create_all()
    yield Journal(db=db)
    await db.dispose()


async def test_order_upsert_and_get(journal: Journal):
    ts = datetime.now(timezone.utc)
    o = Order(
        client_order_id="coid-1",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="500325",
        side=OrderSide.BUY,
        qty=10,
        order_type=OrderType.LIMIT,
        product_type=ProductType.MIS,
        limit_price=100.0,
        status=OrderStatus.NEW,
        ts_created=ts,
        ts_updated=ts,
    )
    await journal.upsert_order(o)

    # Update: status change should persist
    o.status = OrderStatus.OPEN
    o.broker_order_id = "b-42"
    await journal.upsert_order(o)

    got = await journal.get_order("coid-1")
    assert got["status"] == "OPEN"
    assert got["broker_order_id"] == "b-42"


async def test_open_orders_list(journal: Journal):
    ts = datetime.now(timezone.utc)
    for i, status in enumerate([OrderStatus.OPEN, OrderStatus.FILLED, OrderStatus.PENDING]):
        await journal.upsert_order(
            Order(
                client_order_id=f"c-{i}",
                strategy=StrategyKind.EQUITY_ORB,
                instrument_id="X",
                side=OrderSide.BUY,
                qty=1,
                order_type=OrderType.MARKET,
                product_type=ProductType.MIS,
                status=status,
                ts_created=ts,
                ts_updated=ts,
            )
        )
    opens = await journal.list_open_orders()
    assert len(opens) == 2


async def test_fill_and_trade(journal: Journal):
    ts = datetime.now(timezone.utc)
    await journal.record_fill(
        Fill(
            fill_id="f1",
            client_order_id="coid-1",
            instrument_id="X",
            side=OrderSide.BUY,
            qty=10,
            price=100.0,
            ts=ts,
        )
    )
    await journal.record_trade(
        Trade(
            trade_id="t1",
            strategy=StrategyKind.EQUITY_ORB,
            instrument_id="X",
            side=OrderSide.BUY,
            qty=10,
            entry_price=100.0,
            exit_price=105.0,
            entry_ts=ts,
            exit_ts=ts,
            gross_pnl=50.0,
            fees=5.0,
            net_pnl=45.0,
            r_multiple=1.5,
        )
    )
    # Should not raise


async def test_position_upsert(journal: Journal):
    await journal.upsert_position("X", qty=10, avg_price=100.0, realized_pnl=0.0, unrealized_pnl=5.0)
    positions = await journal.list_positions()
    assert len(positions) == 1
    assert positions[0]["qty"] == 10
    await journal.upsert_position("X", qty=20, avg_price=101.0, realized_pnl=0.0, unrealized_pnl=10.0)
    positions = await journal.list_positions()
    assert positions[0]["qty"] == 20
    assert positions[0]["avg_price"] == 101.0
