"""Historical OHLC backfill.

Iterates instruments + timeframes, calls the broker's `historical_ohlc`, and
writes to the Parquet store.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from trader.brokers.base import Broker
from trader.core.domain import Instrument
from trader.observability.logging import get_logger
from trader.storage.parquet_store import ParquetStore

logger = get_logger("trader.marketdata.backfill")


@dataclass
class BackfillJob:
    broker: Broker
    store: ParquetStore
    concurrency: int = 4

    async def run(
        self,
        instruments: list[Instrument],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        sem = asyncio.Semaphore(self.concurrency)
        out: dict[str, int] = {}

        async def _one(inst: Instrument) -> None:
            async with sem:
                try:
                    bars = await self.broker.historical_ohlc(inst, timeframe, start, end)
                except Exception as e:  # noqa: BLE001
                    logger.warning("backfill_failed", instrument=inst.symbol, error=str(e))
                    out[inst.symbol] = 0
                    return
                # Group by month for the store partitioning.
                by_month: dict[date, list[dict]] = {}
                for b in bars:
                    m = date(b.ts.year, b.ts.month, 1)
                    by_month.setdefault(m, []).append(
                        {
                            "instrument_id": inst.security_id,
                            "ts_open": b.ts,
                            "ts_close": b.ts + _timeframe_delta(timeframe),
                            "timeframe": timeframe,
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "volume": b.volume,
                            "oi": b.oi,
                        }
                    )
                total = 0
                for m, rows in by_month.items():
                    total += self.store.write_bars(timeframe, inst.security_id, m, rows)
                out[inst.symbol] = total
                logger.info("backfill_ok", instrument=inst.symbol, bars=total)

        await asyncio.gather(*(_one(i) for i in instruments))
        return out


def _timeframe_delta(tf: str) -> timedelta:
    m = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}
    return timedelta(seconds=m.get(tf, 60))


async def backfill_bars(
    broker: Broker,
    store: ParquetStore,
    instruments: list[Instrument],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    """Convenience wrapper."""
    job = BackfillJob(broker=broker, store=store)
    return await job.run(instruments, timeframe, start, end)
