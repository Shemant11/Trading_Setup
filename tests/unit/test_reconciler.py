"""Position reconciliation tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.brokers.base import PositionSnapshot
from trader.core.domain import Position
from trader.core.enums import ProductType
from trader.portfolio import reconcile_positions


def _lp(qty: int, avg: float = 100.0) -> Position:
    return Position(
        instrument_id="X", qty=qty, avg_price=avg,
        realized_pnl=0.0, unrealized_pnl=0.0, ts_updated=datetime.now(timezone.utc),
    )


def _bp(qty: int, avg: float = 100.0) -> PositionSnapshot:
    return PositionSnapshot(
        instrument_id="X", symbol="X", qty=qty, avg_price=avg,
        product_type=ProductType.MIS,
    )


def test_matched():
    r = reconcile_positions([_lp(10)], [_bp(10)])
    assert r.matched == 1
    assert r.ok


def test_qty_mismatch():
    r = reconcile_positions([_lp(10)], [_bp(15)])
    assert r.mismatches
    assert not r.ok


def test_only_local():
    r = reconcile_positions([_lp(10)], [])
    assert r.only_local == ["X"]


def test_only_broker():
    r = reconcile_positions([], [_bp(10)])
    assert r.only_broker == ["X"]


def test_price_close_enough():
    r = reconcile_positions([_lp(10, 100.0)], [_bp(10, 100.2)])
    # Within 0.5 threshold — treated as match
    assert r.matched == 1
