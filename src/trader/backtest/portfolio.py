"""In-memory portfolio tracker used by the backtest engine.

Not to be confused with the live `apps/portfolio_service`; this is single-
threaded, deterministic, and only used inside a backtest run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from trader.core.domain import Fill, Position, Trade
from trader.core.enums import OrderSide, StrategyKind


@dataclass
class PortfolioTracker:
    starting_nav: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    _last_prices: dict[str, float] = field(default_factory=dict)
    _open_lot: dict[str, list[tuple[int, float, datetime, StrategyKind, str, float]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.cash = self.starting_nav

    # ---- fills -----------------------------------------------------------

    def on_fill(
        self,
        fill: Fill,
        *,
        strategy: StrategyKind,
        fees: float = 0.0,
        stop_price: Optional[float] = None,
    ) -> Optional[Trade]:
        """Apply a fill (FIFO lot matching). Returns a Trade if a round-trip closed."""
        signed_qty = fill.qty if fill.side == OrderSide.BUY else -fill.qty
        pos = self.positions.get(fill.instrument_id)
        if pos is None:
            pos = Position(
                instrument_id=fill.instrument_id, qty=0, avg_price=0.0,
                realized_pnl=0.0, unrealized_pnl=0.0, ts_updated=fill.ts,
            )
            self.positions[fill.instrument_id] = pos

        realized_delta = 0.0
        closed_trade: Optional[Trade] = None

        # Cash impact: buy debits, sell credits. Fees always debit.
        self.cash -= signed_qty * fill.price
        self.cash -= fees

        if pos.qty == 0 or (pos.qty > 0) == (signed_qty > 0):
            # Adding to (or opening) an existing position.
            new_qty = pos.qty + signed_qty
            if new_qty == 0:
                pos.avg_price = 0.0
            else:
                pos.avg_price = (pos.avg_price * pos.qty + fill.price * signed_qty) / new_qty
            pos.qty = new_qty
            self._push_lot(fill.instrument_id, signed_qty, fill.price, fill.ts, strategy,
                           stop_price=stop_price)
        else:
            # Reducing or crossing zero — FIFO match.
            lots = self._open_lot.get(fill.instrument_id, [])
            remaining = signed_qty
            realized = 0.0
            entry_qty_total = 0
            entry_notional = 0.0
            entry_ts_first: Optional[datetime] = None
            first_lot_strategy = strategy
            first_stop: Optional[float] = None
            while remaining != 0 and lots:
                lot_qty, lot_price, lot_ts, lot_strategy, _lot_tag, lot_stop = lots[0]
                # ``match`` is the (positive) number of units this iteration
                # closes against the head lot. ``lot_delta`` is how much the
                # lot's signed qty changes (opposite sign to the lot), and
                # ``remaining_delta`` is how much ``remaining`` moves toward
                # zero (opposite sign of ``remaining``).
                match = min(abs(lot_qty), abs(remaining))
                if lot_qty > 0:  # was long → sell into it
                    realized += (fill.price - lot_price) * match
                    lot_delta = -match
                    remaining_delta = +match
                else:            # was short → buy into it
                    realized += (lot_price - fill.price) * match
                    lot_delta = +match
                    remaining_delta = -match
                entry_qty_total += match
                entry_notional += lot_price * match
                if entry_ts_first is None:
                    entry_ts_first = lot_ts
                    first_lot_strategy = lot_strategy
                    first_stop = lot_stop
                lots[0] = (
                    lot_qty + lot_delta,
                    lot_price,
                    lot_ts,
                    lot_strategy,
                    _lot_tag,
                    lot_stop,
                )
                if lots[0][0] == 0:
                    lots.pop(0)
                remaining += remaining_delta

            if remaining != 0:
                # Position flipped direction — push residual as new lot.
                self._push_lot(
                    fill.instrument_id, remaining, fill.price, fill.ts, strategy,
                    stop_price=stop_price,
                )

            realized_delta = realized
            pos.qty += signed_qty
            if pos.qty == 0:
                pos.avg_price = 0.0

            # If we fully closed at least one lot, materialize a Trade record.
            if entry_qty_total > 0:
                entry_avg = entry_notional / entry_qty_total
                r_mult = None
                if first_stop is not None and abs(entry_avg - first_stop) > 1e-9:
                    r_mult = realized / (abs(entry_avg - first_stop) * entry_qty_total)
                closed_trade = Trade(
                    trade_id=f"tr-{fill.fill_id}",
                    strategy=first_lot_strategy,
                    instrument_id=fill.instrument_id,
                    side=OrderSide.BUY if signed_qty < 0 else OrderSide.SELL,
                    qty=entry_qty_total,
                    entry_price=entry_avg,
                    exit_price=fill.price,
                    entry_ts=entry_ts_first or fill.ts,
                    exit_ts=fill.ts,
                    gross_pnl=realized,
                    fees=fees,
                    net_pnl=realized - fees,
                    r_multiple=r_mult,
                )
                self.trades.append(closed_trade)

        pos.realized_pnl += realized_delta - fees
        pos.last_price = fill.price
        pos.ts_updated = fill.ts
        self._last_prices[fill.instrument_id] = fill.price
        self._mark_unrealized(pos)
        return closed_trade

    def _push_lot(
        self,
        instrument_id: str,
        qty: int,
        price: float,
        ts: datetime,
        strategy: StrategyKind,
        stop_price: Optional[float],
    ) -> None:
        lots = self._open_lot.setdefault(instrument_id, [])
        lots.append((qty, price, ts, strategy, "", stop_price if stop_price is not None else float("nan")))

    def _mark_unrealized(self, pos: Position) -> None:
        if pos.last_price is not None and pos.qty != 0:
            pos.unrealized_pnl = (pos.last_price - pos.avg_price) * pos.qty
        else:
            pos.unrealized_pnl = 0.0

    # ---- marks -----------------------------------------------------------

    def mark(self, instrument_id: str, price: float, ts: datetime) -> None:
        pos = self.positions.get(instrument_id)
        if pos is None or pos.qty == 0:
            return
        self._last_prices[instrument_id] = price
        pos.last_price = price
        pos.ts_updated = ts
        self._mark_unrealized(pos)

    def total_equity(self, ts: Optional[datetime] = None) -> float:
        upl = sum(p.unrealized_pnl for p in self.positions.values())
        # cash already reflects fills' price × qty; unrealized brings marks in.
        mv = sum((p.last_price or p.avg_price) * p.qty for p in self.positions.values())
        equity = self.cash + mv
        if ts is not None:
            self.equity_curve.append((ts, equity))
        return equity
