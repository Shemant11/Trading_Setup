"""Capital ramp controller.

Starts at 10% of allocated NAV, ramps in stages 10 → 25 → 50 → 100% over 4
weeks, gated on live statistics (win rate, DD, execution slippage). If any
gate fails, ramp *pauses* — never auto-reverts, so the operator explicitly
signs off before returning to a lower stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional


RAMP_STAGES = [0.10, 0.25, 0.50, 1.00]


@dataclass
class LiveStats:
    trades: int = 0
    win_rate: float = 0.0
    net_pnl_pct: float = 0.0
    max_dd_pct: float = 0.0
    avg_slippage_bps: float = 0.0
    days_active: int = 0


@dataclass
class CapitalRampController:
    """Owns the current allocation fraction and the promotion criteria."""

    stage_index: int = 0
    stage_started: date = field(default_factory=date.today)
    min_days_per_stage: int = 7
    min_trades_per_stage: int = 20
    min_win_rate: float = 0.45
    max_dd_pct_at_stage: float = -5.0
    max_slippage_bps: float = 12.0
    paused: bool = False
    pause_reason: Optional[str] = None

    @property
    def current_fraction(self) -> float:
        return RAMP_STAGES[self.stage_index]

    def can_promote(self, stats: LiveStats, today: Optional[date] = None) -> tuple[bool, str]:
        if self.paused:
            return False, self.pause_reason or "paused"
        if self.stage_index >= len(RAMP_STAGES) - 1:
            return False, "already at 100%"
        today = today or date.today()
        days = (today - self.stage_started).days
        if days < self.min_days_per_stage:
            return False, f"only {days} days at this stage (need {self.min_days_per_stage})"
        if stats.trades < self.min_trades_per_stage:
            return False, f"only {stats.trades} trades (need {self.min_trades_per_stage})"
        if stats.win_rate < self.min_win_rate:
            return False, f"win_rate {stats.win_rate:.2%} < {self.min_win_rate:.2%}"
        if stats.max_dd_pct < self.max_dd_pct_at_stage:
            return False, f"DD {stats.max_dd_pct:.2f}% breached"
        if stats.avg_slippage_bps > self.max_slippage_bps:
            return False, f"slippage {stats.avg_slippage_bps:.1f} bps too high"
        return True, "ok"

    def promote(self, today: Optional[date] = None) -> None:
        if self.stage_index < len(RAMP_STAGES) - 1:
            self.stage_index += 1
            self.stage_started = today or date.today()

    def pause(self, reason: str) -> None:
        self.paused = True
        self.pause_reason = reason

    def resume(self) -> None:
        self.paused = False
        self.pause_reason = None
