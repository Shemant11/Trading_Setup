"""Universe builder.

Applies fundamental + liquidity filters to a candidate set of instruments
and freezes the result for the trading day. Called on `refresh_day` weekly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable

from trader.config.loader import UniverseSection
from trader.core.domain import Instrument
from trader.observability.logging import get_logger

logger = get_logger("trader.marketdata.universe")


@dataclass
class Candidate:
    instrument: Instrument
    adv_cr: float                     # 20-day avg daily value in ₹ crore
    avg_spread_bps: float
    circuit_hit_last_5_days: bool = False


@dataclass
class UniverseBuilder:
    cfg: UniverseSection

    def build(self, candidates: Iterable[Candidate], as_of: date) -> list[Instrument]:
        selected: list[Instrument] = []
        rejected: list[tuple[str, str]] = []
        for c in candidates:
            reason = self._filter_reason(c)
            if reason is None:
                selected.append(c.instrument)
            else:
                rejected.append((c.instrument.symbol, reason))
        logger.info(
            "universe_built", as_of=str(as_of), selected=len(selected), rejected=len(rejected)
        )
        return selected

    def _filter_reason(self, c: Candidate) -> str | None:
        if c.adv_cr < self.cfg.min_adv_cr:
            return "adv_too_low"
        if c.avg_spread_bps > self.cfg.max_spread_bps:
            return "spread_too_wide"
        if c.circuit_hit_last_5_days:
            return "recent_circuit"
        return None
