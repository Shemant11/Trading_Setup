"""Broker ↔ journal position reconciler.

Called at boot (safe-mode) and periodically (every 60 s). Detects mismatches
and returns a report the caller can send to the notification dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from trader.brokers.base import Broker, PositionSnapshot
from trader.core.domain import Position
from trader.observability.logging import get_logger

logger = get_logger("trader.portfolio.reconciler")


@dataclass
class ReconciliationResult:
    matched: int = 0
    mismatches: list[str] = field(default_factory=list)
    only_broker: list[str] = field(default_factory=list)
    only_local: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatches or self.only_broker or self.only_local)

    def summary(self) -> str:
        return (
            f"matched={self.matched} "
            f"mismatches={len(self.mismatches)} "
            f"only_broker={len(self.only_broker)} "
            f"only_local={len(self.only_local)}"
        )


def reconcile_positions(
    local: Iterable[Position], broker: Iterable[PositionSnapshot]
) -> ReconciliationResult:
    local_by_id = {p.instrument_id: p for p in local if p.qty != 0}
    broker_by_id = {b.instrument_id: b for b in broker if b.qty != 0}

    result = ReconciliationResult()
    for iid, lp in local_by_id.items():
        if iid not in broker_by_id:
            result.only_local.append(iid)
            continue
        bp = broker_by_id[iid]
        if lp.qty != bp.qty:
            result.mismatches.append(f"{iid} local_qty={lp.qty} broker_qty={bp.qty}")
        elif abs(lp.avg_price - bp.avg_price) > 0.5:
            result.mismatches.append(
                f"{iid} avg diff local={lp.avg_price} broker={bp.avg_price}"
            )
        else:
            result.matched += 1
    for iid in broker_by_id.keys() - local_by_id.keys():
        result.only_broker.append(iid)
    return result
