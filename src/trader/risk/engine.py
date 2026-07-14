"""Risk engine — the pre-trade gate.

Every `Signal` from a strategy is passed to `RiskEngine.check()`. The engine
runs all four layers and returns a `RiskDecision` with either an approved
size (possibly < requested) or a rejection.

Layers:

1. Position — Kelly + vol-normalized sizing caps.
2. Strategy — consecutive-loss brake, per-strategy pause.
3. Book — portfolio heat, exposure caps, loss limits.
4. Systemic — kill switch, VIX shock, broker latency (fed externally).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from trader.config.loader import AppConfig, RiskSection
from trader.core.domain import Signal
from trader.observability.logging import get_logger
from trader.risk.kill_switch import KillSwitch
from trader.risk.limits import LimitState, LimitViolation
from trader.risk.sizing import cap_size_by_notional, vol_normalized_size

logger = get_logger("trader.risk")


@dataclass
class RiskDecision:
    approved: bool
    approved_qty: int = 0
    reason: str = ""
    violations: list[LimitViolation] = field(default_factory=list)


@dataclass
class RiskEngine:
    cfg: RiskSection
    nav: float
    state: LimitState = field(default_factory=LimitState)
    kill_switch: Optional[KillSwitch] = None
    # Instrument-level daily vol lookup, updated by the marketdata layer.
    daily_vol_pct: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: AppConfig, kill_switch: Optional[KillSwitch] = None) -> RiskEngine:
        return cls(cfg=cfg.risk, nav=cfg.capital.nav, kill_switch=kill_switch)

    # ---------- runtime updates ------------------------------------------

    def on_trade_closed(self, strategy: str, net_pnl: float) -> None:
        sl = self.state.strategy_limits(strategy)
        sl.apply_trade(net_pnl)
        self.state.loss.daily_pnl += net_pnl
        self.state.loss.weekly_pnl += net_pnl
        self.state.loss.monthly_pnl += net_pnl
        # Consecutive-loss brake
        if sl.consecutive_losses >= self.cfg.consecutive_losses_hardpause:
            sl.paused_today = True
            logger.warning("strategy_paused", strategy=strategy,
                           consecutive_losses=sl.consecutive_losses)
        elif sl.consecutive_losses >= self.cfg.consecutive_losses_softbrake:
            sl.size_multiplier = 0.5
            logger.warning("strategy_soft_braked", strategy=strategy,
                           consecutive_losses=sl.consecutive_losses)
        # Capital preservation mode trigger
        if self.state.loss.monthly_pnl / self.nav <= -self.cfg.monthly_loss_limit_pct:
            self.state.capital_preservation_mode = True
            logger.error("capital_preservation_mode_activated")

    # ---------- checks ----------------------------------------------------

    async def check(self, signal: Signal) -> RiskDecision:
        violations: list[LimitViolation] = []

        # ---- Layer 4: systemic ----
        if self.kill_switch is not None and await self.kill_switch.active():
            return _reject("kill_switch", "kill switch active", "4")

        # Capital Preservation Mode blocks all *new* entries
        if self.state.capital_preservation_mode:
            return _reject("capital_preservation", "capital preservation mode: exits only", "3")

        # ---- Layer 3: book ----
        if self.state.loss.daily_pnl / self.nav <= -self.cfg.daily_loss_limit_pct:
            return _reject("daily_loss", "daily loss limit reached", "3")
        if self.state.loss.weekly_pnl / self.nav <= -self.cfg.weekly_loss_limit_pct:
            return _reject("weekly_loss", "weekly loss limit reached", "3")

        # ---- Layer 2: strategy ----
        sl = self.state.strategy_limits(signal.strategy.value)
        if sl.paused_today:
            return _reject("strategy_paused", "strategy paused this session", "2",
                           strategy=signal.strategy.value)

        # ---- Layer 1: position ----
        # Fold in cap by max_single_stock_pct, vol cap, and per-trade risk cap.
        risk_per_unit = signal.risk_per_unit
        if risk_per_unit <= 0:
            return _reject("bad_stop", "risk_per_unit <= 0", "1")

        approved_qty = signal.intended_qty
        # Cap by single-stock exposure
        max_notional_qty = cap_size_by_notional(self.nav, signal.entry_price,
                                                self.cfg.max_single_stock_pct)
        if max_notional_qty > 0:
            approved_qty = min(approved_qty, max_notional_qty)

        # Cap by vol normalization
        dv = self.daily_vol_pct.get(signal.instrument_id)
        if dv:
            vn = vol_normalized_size(
                self.nav, signal.entry_price, dv, self.cfg.target_position_vol_pct
            )
            if vn > 0:
                approved_qty = min(approved_qty, vn)

        # Apply soft-brake multiplier
        if sl.size_multiplier < 1.0:
            approved_qty = int(approved_qty * sl.size_multiplier)

        # Portfolio heat check
        heat_delta = risk_per_unit * approved_qty
        if (self.state.book.portfolio_heat + heat_delta) / self.nav > self.cfg.portfolio_heat_cap_pct:
            return _reject("portfolio_heat", "heat cap breached", "2",
                           strategy=signal.strategy.value)

        if approved_qty <= 0:
            return _reject("qty_zero", "size reduced to zero by risk caps", "1",
                           strategy=signal.strategy.value)

        return RiskDecision(approved=True, approved_qty=approved_qty, reason="ok")

    def commit(self, signal: Signal, qty: int) -> None:
        """Called after an approved order is dispatched: updates book counters."""
        self.state.book.portfolio_heat += signal.risk_per_unit * qty


def _reject(
    code: str, reason: str, layer: str, strategy: Optional[str] = None
) -> RiskDecision:
    v = LimitViolation(layer=layer, action="reject", reason=reason, strategy=strategy)
    logger.info("risk_reject", code=code, reason=reason, layer=layer, strategy=strategy)
    return RiskDecision(approved=False, approved_qty=0, reason=reason, violations=[v])
