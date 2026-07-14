"""End-of-day report builder.

Reads today's trades from the journal, computes per-strategy PnL, best/worst
trades, and slippage stats. Returns an `EodReport` object usable both for
Telegram/email dispatch and dashboard display.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select

from trader.storage import Journal
from trader.storage.models import TradeRow


@dataclass
class EodReport:
    date: date
    nav_start: float
    nav_end: float
    pnl: float
    pnl_pct: float
    trades: int
    win_rate: float
    per_strategy: dict[str, dict[str, float]] = field(default_factory=dict)
    best: Optional[dict] = None
    worst: Optional[dict] = None

    def to_markdown(self) -> str:
        lines = [
            f"# EOD {self.date.isoformat()}",
            f"",
            f"- NAV: ₹{self.nav_start:,.0f} → ₹{self.nav_end:,.0f}",
            f"- PnL: ₹{self.pnl:,.0f}  ({self.pnl_pct:.2f}%)",
            f"- Trades: {self.trades}  Win rate: {self.win_rate*100:.1f}%",
        ]
        if self.per_strategy:
            lines.append("")
            lines.append("## Per-strategy")
            for k, d in sorted(self.per_strategy.items(), key=lambda x: -x[1].get("pnl", 0)):
                lines.append(
                    f"- {k}: ₹{d['pnl']:,.0f}  trades={int(d['trades'])}  "
                    f"win={d['win_rate']*100:.0f}%"
                )
        if self.best:
            lines.append("")
            lines.append(
                f"Best trade: {self.best['instrument_id']} +₹{self.best['net_pnl']:,.0f}"
            )
        if self.worst:
            lines.append(
                f"Worst trade: {self.worst['instrument_id']} ₹{self.worst['net_pnl']:,.0f}"
            )
        return "\n".join(lines)


async def generate_eod_report(
    journal: Journal,
    *,
    on_date: date,
    nav_start: float,
) -> EodReport:
    """Compute the EOD report from journal rows for a specific date."""
    day_start = datetime.combine(on_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = datetime.combine(on_date, datetime.max.time(), tzinfo=timezone.utc)
    async with journal.db.session() as session:
        rows = (
            await session.scalars(
                select(TradeRow).where(TradeRow.exit_ts >= day_start).where(TradeRow.exit_ts <= day_end)
            )
        ).all()
    trades = [_trade_to_dict(r) for r in rows]
    return _summarize(trades, on_date=on_date, nav_start=nav_start)


def _summarize(trades: list[dict], on_date: date, nav_start: float) -> EodReport:
    if not trades:
        return EodReport(
            date=on_date,
            nav_start=nav_start,
            nav_end=nav_start,
            pnl=0.0,
            pnl_pct=0.0,
            trades=0,
            win_rate=0.0,
        )
    total_pnl = sum(t["net_pnl"] for t in trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    per_strat: dict[str, dict[str, float]] = {}
    for t in trades:
        d = per_strat.setdefault(t["strategy"], {"pnl": 0.0, "trades": 0, "wins": 0})
        d["pnl"] += t["net_pnl"]
        d["trades"] += 1
        if t["net_pnl"] > 0:
            d["wins"] += 1
    for k, d in per_strat.items():
        d["win_rate"] = (d["wins"] / d["trades"]) if d["trades"] > 0 else 0.0
    best = max(trades, key=lambda t: t["net_pnl"])
    worst = min(trades, key=lambda t: t["net_pnl"])
    return EodReport(
        date=on_date,
        nav_start=nav_start,
        nav_end=nav_start + total_pnl,
        pnl=total_pnl,
        pnl_pct=(total_pnl / nav_start * 100) if nav_start > 0 else 0.0,
        trades=len(trades),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        per_strategy=per_strat,
        best=best,
        worst=worst,
    )


def _trade_to_dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
