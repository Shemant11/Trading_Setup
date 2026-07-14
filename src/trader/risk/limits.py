"""Risk limits — mutable state that the engine reads on every check."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional


@dataclass
class LimitViolation:
    layer: str
    action: str
    reason: str
    strategy: Optional[str] = None


@dataclass
class StrategyLimits:
    """Per-strategy state (consecutive losses, PnL today)."""

    strategy: str
    consecutive_losses: int = 0
    trades_today: int = 0
    pnl_today: float = 0.0
    paused_today: bool = False
    size_multiplier: float = 1.0

    def apply_trade(self, net_pnl: float) -> None:
        self.trades_today += 1
        self.pnl_today += net_pnl
        if net_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def reset_day(self) -> None:
        self.trades_today = 0
        self.pnl_today = 0.0
        self.paused_today = False
        self.size_multiplier = 1.0
        # consecutive_losses intentionally persists across sessions.


@dataclass
class LossLimits:
    """Book-level rolling loss caps."""

    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    rolling_3m_dd_pct: float = 0.0
    peak_nav: float = 0.0


@dataclass
class BookLimits:
    open_gross_notional: float = 0.0
    open_net_delta: float = 0.0
    open_by_stock: dict[str, float] = field(default_factory=dict)
    open_by_sector: dict[str, float] = field(default_factory=dict)
    portfolio_heat: float = 0.0


@dataclass
class LimitState:
    """Aggregated state for the engine."""

    day: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    strategies: dict[str, StrategyLimits] = field(default_factory=dict)
    loss: LossLimits = field(default_factory=LossLimits)
    book: BookLimits = field(default_factory=BookLimits)
    capital_preservation_mode: bool = False

    def strategy_limits(self, name: str) -> StrategyLimits:
        s = self.strategies.get(name)
        if s is None:
            s = StrategyLimits(strategy=name)
            self.strategies[name] = s
        return s

    def start_of_day_reset(self, today: date) -> None:
        if today == self.day:
            return
        self.day = today
        self.loss.daily_pnl = 0.0
        for s in self.strategies.values():
            s.reset_day()
