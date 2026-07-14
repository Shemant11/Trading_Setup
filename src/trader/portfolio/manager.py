"""In-memory live portfolio manager.

Consumes Fills from the execution gateway, updates positions + P&L, marks
open positions on incoming ticks, and pushes to Prometheus + journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from trader.core.domain import Fill, Position, Tick
from trader.core.enums import OrderSide, StrategyKind
from trader.observability.logging import get_logger
from trader.observability.metrics import (
    FILLS,
    OPEN_POSITIONS,
    PNL_REALIZED,
    PNL_UNREALIZED,
)
from trader.storage.journal import Journal

logger = get_logger("trader.portfolio")


@dataclass
class PortfolioManager:
    journal: Journal
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl_by_strategy: dict[str, float] = field(default_factory=dict)

    async def on_fill(self, fill: Fill, strategy: StrategyKind) -> None:
        pos = self.positions.get(fill.instrument_id)
        signed = fill.qty if fill.side == OrderSide.BUY else -fill.qty
        realized_delta = 0.0
        if pos is None:
            pos = Position(
                instrument_id=fill.instrument_id, qty=0, avg_price=0.0,
                realized_pnl=0.0, unrealized_pnl=0.0, ts_updated=fill.ts,
            )
            self.positions[fill.instrument_id] = pos
        if pos.qty == 0 or (pos.qty > 0) == (signed > 0):
            new_qty = pos.qty + signed
            if new_qty != 0:
                pos.avg_price = (
                    pos.avg_price * pos.qty + fill.price * signed
                ) / new_qty
            pos.qty = new_qty
        else:
            # Reducing / crossing zero
            closing_qty = min(abs(signed), abs(pos.qty))
            realized_delta = (fill.price - pos.avg_price) * closing_qty * (1 if pos.qty > 0 else -1)
            pos.qty = pos.qty + signed
            if pos.qty == 0:
                pos.avg_price = 0.0
        pos.realized_pnl += realized_delta - fill.fees
        pos.last_price = fill.price
        pos.ts_updated = fill.ts

        # Journal + metrics
        await self.journal.record_fill(fill)
        await self.journal.upsert_position(
            fill.instrument_id, pos.qty, pos.avg_price,
            pos.realized_pnl, pos.unrealized_pnl, pos.last_price,
        )
        FILLS.labels(broker=fill.broker or "unknown", side=fill.side.value).inc()
        strat = strategy.value
        self.realized_pnl_by_strategy[strat] = (
            self.realized_pnl_by_strategy.get(strat, 0.0) + realized_delta - fill.fees
        )
        PNL_REALIZED.labels(strategy=strat).set(self.realized_pnl_by_strategy[strat])
        OPEN_POSITIONS.labels(strategy=strat).set(
            sum(1 for p in self.positions.values() if p.qty != 0)
        )

    def on_tick(self, tick: Tick) -> None:
        pos = self.positions.get(tick.instrument_id)
        if pos is None or pos.qty == 0:
            return
        pos.mark(tick.ltp, tick.ts_exchange)
        PNL_UNREALIZED.labels(strategy="_book").set(
            sum(p.unrealized_pnl for p in self.positions.values())
        )

    def is_flat(self, instrument_id: str) -> bool:
        p = self.positions.get(instrument_id)
        return p is None or p.qty == 0
