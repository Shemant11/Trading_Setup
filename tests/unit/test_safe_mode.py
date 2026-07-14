"""Safe-mode gate tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.brokers.base import PositionSnapshot
from trader.core.domain import Position
from trader.core.enums import ProductType
from trader.ops.safe_mode import SafeModeGate, SafeModeStatus
from trader.portfolio.reconciler import reconcile_positions


def test_starts_armed():
    g = SafeModeGate()
    assert g.status == SafeModeStatus.ARMED
    assert not g.allows_new_entries


def test_review_on_mismatch():
    g = SafeModeGate()
    local = [Position(instrument_id="X", qty=10, avg_price=100,
                      realized_pnl=0, unrealized_pnl=0,
                      ts_updated=datetime.now(timezone.utc))]
    broker = [PositionSnapshot(instrument_id="X", symbol="X", qty=15, avg_price=100,
                                product_type=ProductType.MIS)]
    r = reconcile_positions(local, broker)
    g.observe_reconciliation(r)
    assert g.status == SafeModeStatus.REVIEW


def test_acknowledge_clears():
    g = SafeModeGate()
    g.acknowledge("all positions reviewed")
    assert g.status == SafeModeStatus.CLEARED
    assert g.allows_new_entries
