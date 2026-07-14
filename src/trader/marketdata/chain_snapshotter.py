"""Option chain snapshotter.

Fetches the chain periodically (default every 30 s), computes ATM IV and
greeks, and writes Parquet snapshots keyed by underlying/date. Also feeds
subscribed strategies via a callback.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional

from trader.brokers.base import Broker
from trader.core.domain import OptionChainSnapshot, OptionQuote
from trader.observability.logging import get_logger
from trader.options.greeks import bs_greeks, implied_volatility
from trader.storage.parquet_store import ParquetStore

logger = get_logger("trader.marketdata.chain")


ChainCallback = Callable[[OptionChainSnapshot], Awaitable[None]]


@dataclass
class ChainSnapshotter:
    broker: Broker
    store: ParquetStore
    interval_seconds: float = 30.0
    subscribers: list[ChainCallback] = field(default_factory=list)
    _tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    _running: bool = False

    async def start(self, underlyings: list[str]) -> None:
        self._running = True
        for u in underlyings:
            self._tasks[u] = asyncio.create_task(self._loop(u), name=f"chain-{u}")

    async def stop(self) -> None:
        self._running = False
        for t in list(self._tasks.values()):
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001, S110, PT017
                pass
        self._tasks.clear()

    def subscribe(self, cb: ChainCallback) -> None:
        self.subscribers.append(cb)

    async def _loop(self, underlying: str) -> None:
        while self._running:
            try:
                snap = await self._fetch(underlying)
                if snap is not None:
                    await self._publish(snap)
            except Exception as e:  # noqa: BLE001
                logger.warning("chain_fetch_failed", underlying=underlying, error=str(e))
            await asyncio.sleep(self.interval_seconds)

    async def _fetch(self, underlying: str) -> Optional[OptionChainSnapshot]:
        """Concrete broker call goes here.

        Placeholder returns None. Wiring to Dhan's `/optionchain` endpoint is
        done via the broker's REST client in Phase 3 wiring code; kept here
        as a hook so unit tests can call `_publish` directly.
        """
        return None

    async def _publish(self, snap: OptionChainSnapshot) -> None:
        # Enrich with IV / greeks where missing.
        enriched = self.enrich(snap)
        # Persist
        day = enriched.ts.date()
        rows = [
            {
                "underlying": enriched.underlying,
                "ts": enriched.ts,
                "spot": enriched.spot,
                "expiry": enriched.expiry,
                "strike": q.strike,
                "option_type": q.option_type,
                "ltp": q.ltp,
                "bid": q.bid,
                "ask": q.ask,
                "iv": q.iv,
                "oi": q.oi,
                "oi_change": q.oi_change,
                "volume": q.volume,
                "delta": q.delta,
                "gamma": q.gamma,
                "theta": q.theta,
                "vega": q.vega,
            }
            for q in enriched.quotes
        ]
        self.store.write_option_chain(enriched.underlying, day, rows)
        for cb in list(self.subscribers):
            try:
                await cb(enriched)
            except Exception as e:  # noqa: BLE001
                logger.warning("chain_subscriber_error", error=str(e))

    def enrich(self, snap: OptionChainSnapshot) -> OptionChainSnapshot:
        # Compute IV + greeks for every quote missing them.
        expiry_dt = datetime.combine(snap.expiry, datetime.min.time(), tzinfo=timezone.utc)
        t_years = max((expiry_dt - snap.ts).total_seconds() / (365 * 86400), 1 / 365.0)
        enriched_quotes: list[OptionQuote] = []
        atm_ivs: list[float] = []
        for q in snap.quotes:
            iv = q.iv
            if iv is None or iv <= 0:
                iv = implied_volatility(
                    price=q.ltp, spot=snap.spot, strike=q.strike,
                    t_years=t_years, kind=q.option_type,
                )
            g = bs_greeks(
                spot=snap.spot, strike=q.strike, sigma=iv if iv and iv > 0 else 0.2,
                t_years=t_years, kind=q.option_type,
            )
            enriched_quotes.append(
                OptionQuote(
                    strike=q.strike,
                    option_type=q.option_type,
                    ltp=q.ltp,
                    bid=q.bid,
                    ask=q.ask,
                    iv=iv,
                    oi=q.oi,
                    oi_change=q.oi_change,
                    volume=q.volume,
                    delta=g.delta,
                    gamma=g.gamma,
                    theta=g.theta,
                    vega=g.vega,
                )
            )
            if abs(q.strike - snap.spot) < 100 and iv and iv > 0:
                atm_ivs.append(iv)
        atm_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else snap.atm_iv
        return OptionChainSnapshot(
            underlying=snap.underlying,
            spot=snap.spot,
            expiry=snap.expiry,
            ts=snap.ts,
            atm_iv=atm_iv,
            quotes=enriched_quotes,
        )
