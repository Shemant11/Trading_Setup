"""Option chain analysis: OI build-up, PCR, max pain, ATM discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from trader.core.domain import OptionChainSnapshot, OptionQuote


def max_pain(chain: OptionChainSnapshot) -> Optional[float]:
    """Max pain = strike at which total option-writer loss is minimized.

    Loss(S) = sum(OI_call * max(S - K, 0)) + sum(OI_put * max(K - S, 0))
    """
    if not chain.quotes:
        return None
    strikes = sorted({q.strike for q in chain.quotes})
    calls_by_strike = {}
    puts_by_strike = {}
    for q in chain.quotes:
        if q.option_type == "CE":
            calls_by_strike[q.strike] = calls_by_strike.get(q.strike, 0) + q.oi
        else:
            puts_by_strike[q.strike] = puts_by_strike.get(q.strike, 0) + q.oi

    best_strike = strikes[0]
    best_loss = float("inf")
    for s in strikes:
        loss = 0.0
        for k, oi in calls_by_strike.items():
            loss += max(s - k, 0) * oi
        for k, oi in puts_by_strike.items():
            loss += max(k - s, 0) * oi
        if loss < best_loss:
            best_loss = loss
            best_strike = s
    return best_strike


@dataclass
class OIBuildup:
    """Classification of an OI change vs price change."""

    long_buildup: int = 0        # price up + OI up
    short_buildup: int = 0       # price down + OI up
    long_unwind: int = 0         # price down + OI down
    short_covering: int = 0      # price up + OI down


class ChainAnalyzer:
    """Per-underlying analyzer with an in-memory previous snapshot."""

    def __init__(self) -> None:
        self._prev: dict[str, OptionChainSnapshot] = {}

    def analyze(self, snap: OptionChainSnapshot) -> dict:
        prev = self._prev.get(snap.underlying)
        self._prev[snap.underlying] = snap
        result = {
            "underlying": snap.underlying,
            "spot": snap.spot,
            "atm_strike": self.atm_strike(snap),
            "atm_iv": snap.atm_iv,
            "pcr_oi": snap.pcr_oi,
            "pcr_volume": snap.pcr_volume,
            "max_pain": max_pain(snap),
            "buildup": None,
        }
        if prev is not None:
            result["buildup"] = self._classify_buildup(prev, snap).__dict__
        return result

    def atm_strike(self, snap: OptionChainSnapshot) -> Optional[float]:
        if not snap.quotes:
            return None
        strikes = {q.strike for q in snap.quotes}
        return min(strikes, key=lambda k: abs(k - snap.spot))

    def _classify_buildup(
        self, prev: OptionChainSnapshot, cur: OptionChainSnapshot
    ) -> OIBuildup:
        atm = self.atm_strike(cur)
        b = OIBuildup()
        if atm is None:
            return b
        # Look at ATM ±2 strikes for both CE and PE.
        prev_by_key = {(q.strike, q.option_type): q for q in prev.quotes}
        for q in cur.quotes:
            key = (q.strike, q.option_type)
            p = prev_by_key.get(key)
            if p is None:
                continue
            price_up = q.ltp > p.ltp
            oi_up = q.oi > p.oi
            if price_up and oi_up:
                b.long_buildup += 1
            elif not price_up and oi_up:
                b.short_buildup += 1
            elif not price_up and not oi_up:
                b.long_unwind += 1
            elif price_up and not oi_up:
                b.short_covering += 1
        return b
