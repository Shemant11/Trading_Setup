"""Iron condor.

Rule set:

* Only enter if IV Rank > `ivr_min` (default 70).
* Short strikes at ±(em_multiplier_short * expected_move) from spot.
* Long wings at ±(em_multiplier_wings * expected_move) from spot.
* Only defined-risk — the strategy never emits naked short signals.

The strategy takes decisions on option-chain snapshots (not bars); the plan
requires it because IV/greeks/OI are chain-level views.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional

from trader.config.loader import AppConfig
from trader.core.domain import Bar, OptionChainSnapshot, OptionQuote, Signal
from trader.core.enums import OrderSide, OrderType, ProductType, StrategyKind, Validity
from trader.options.iv_rank import IVRankTracker, expected_move
from trader.strategies.base import Strategy


@dataclass
class IronCondorLegs:
    short_call: OptionQuote
    long_call: OptionQuote
    short_put: OptionQuote
    long_put: OptionQuote

    @property
    def net_credit(self) -> float:
        return (
            (self.short_call.ltp - self.long_call.ltp)
            + (self.short_put.ltp - self.long_put.ltp)
        )

    @property
    def max_loss_per_lot(self) -> float:
        # width - net_credit (per side, whichever wider)
        call_width = self.long_call.strike - self.short_call.strike
        put_width = self.short_put.strike - self.long_put.strike
        return max(call_width, put_width) - self.net_credit


class IronCondorStrategy(Strategy):
    kind = StrategyKind.OPTIONS_IRON_CONDOR

    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        p = self.params
        self.ivr_min: float = float(p.get("ivr_min", 70)) / 100.0
        self.em_short: float = float(p.get("em_multiplier_short", 1.2))
        self.em_wings: float = float(p.get("em_multiplier_wings", 2.0))
        self.max_loss_pct: float = float(p.get("max_loss_per_trade_pct", 0.005))  # 0.5% NAV
        self.iv_tracker = IVRankTracker()
        self._last_entry_by_underlying: dict[str, str] = {}

    def observe_chain(self, snap: OptionChainSnapshot) -> None:
        if snap.atm_iv:
            self.iv_tracker.observe(snap.underlying, snap.atm_iv)

    def on_bar(self, bar: Bar) -> list[Signal]:
        return []

    def evaluate(self, snap: OptionChainSnapshot, days_to_expiry: int) -> list[Signal]:
        """Return signals for legs of an iron condor at the given chain snapshot."""
        if not self._enabled or snap.atm_iv is None:
            return []
        self.iv_tracker.observe(snap.underlying, snap.atm_iv)
        ivr = self.iv_tracker.rank(snap.underlying)
        if ivr != ivr or ivr < self.ivr_min:  # NaN check + threshold
            return []
        legs = self._build_condor(snap, days_to_expiry)
        if legs is None:
            return []
        if legs.max_loss_per_lot <= 0:
            return []
        # Size by max NAV loss
        max_rupees_loss = self._nav * self.max_loss_pct
        lots = int(max_rupees_loss // legs.max_loss_per_lot)
        if lots <= 0:
            return []
        # The lot size (25 for NIFTY, 15 for BANKNIFTY etc.) is baked into the
        # OptionQuote's underlying Instrument.lot_size — resolved by the caller.
        return self._legs_to_signals(legs, lots, snap.underlying)

    def _build_condor(
        self, snap: OptionChainSnapshot, dte: int
    ) -> Optional[IronCondorLegs]:
        em = expected_move(snap.spot, snap.atm_iv or 0.0, dte)
        if em == 0:
            return None
        short_call_strike = snap.spot + em * self.em_short
        short_put_strike = snap.spot - em * self.em_short
        long_call_strike = snap.spot + em * self.em_wings
        long_put_strike = snap.spot - em * self.em_wings

        calls = sorted(snap.calls(), key=lambda q: q.strike)
        puts = sorted(snap.puts(), key=lambda q: q.strike)
        short_call = _nearest(calls, short_call_strike, mode="above")
        long_call = _nearest(calls, long_call_strike, mode="above")
        short_put = _nearest(puts, short_put_strike, mode="below")
        long_put = _nearest(puts, long_put_strike, mode="below")
        if not all([short_call, long_call, short_put, long_put]):
            return None
        return IronCondorLegs(
            short_call=short_call,
            long_call=long_call,
            short_put=short_put,
            long_put=long_put,
        )

    def _legs_to_signals(self, legs: IronCondorLegs, lots: int, underlying: str) -> list[Signal]:
        # Sell the short strikes, buy the wings. We tag all four with the
        # same parent id so the risk engine and reporting can group them.
        parent = str(uuid.uuid4())
        out: list[Signal] = []
        for side, q, tag in [
            (OrderSide.SELL, legs.short_call, "short_call"),
            (OrderSide.BUY, legs.long_call, "long_call"),
            (OrderSide.SELL, legs.short_put, "short_put"),
            (OrderSide.BUY, legs.long_put, "long_put"),
        ]:
            iid = f"{underlying}:{q.option_type}:{q.strike}"
            out.append(
                Signal(
                    id=f"{parent}:{tag}",
                    strategy=self.kind,
                    instrument_id=iid,
                    side=side,
                    intended_qty=lots,
                    entry_price=q.ltp,
                    stop_price=q.ltp * (1.5 if side == OrderSide.SELL else 0.5),
                    take_profit_prices=[],
                    order_type=OrderType.LIMIT,
                    product_type=ProductType.NRML,
                    validity=Validity.DAY,
                    ts=_now(),
                    metadata={"leg": tag, "parent": parent},
                )
            )
        return out


def _nearest(
    quotes: Iterable[OptionQuote], target: float, *, mode: str = "closest"
) -> Optional[OptionQuote]:
    candidates = list(quotes)
    if not candidates:
        return None
    if mode == "closest":
        return min(candidates, key=lambda q: abs(q.strike - target))
    if mode == "above":
        above = [q for q in candidates if q.strike >= target]
        return min(above, key=lambda q: q.strike) if above else candidates[-1]
    if mode == "below":
        below = [q for q in candidates if q.strike <= target]
        return max(below, key=lambda q: q.strike) if below else candidates[0]
    raise ValueError(mode)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
