"""BacktestRunner — the CLI/programmatic entrypoint.

Loads bars from the Parquet store (or accepts an in-memory iterable for
tests), constructs a strategy via `strategies.registry.get`, wires the
BacktestEngine and returns the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import polars as pl

from trader.backtest.engine import BacktestEngine, BacktestResult
from trader.config import get_settings, load_config
from trader.core.domain import Bar, Instrument
from trader.core.enums import AssetClass, Exchange, Segment
from trader.observability.logging import get_logger
from trader.storage.parquet_store import ParquetStore

logger = get_logger("trader.backtest.runner")


@dataclass
class BacktestRunner:
    store: ParquetStore | None = None
    _cfg = None

    def __post_init__(self) -> None:
        settings = get_settings()
        cfg = load_config(settings.config_path)
        self._cfg = cfg
        if self.store is None:
            self.store = ParquetStore(root=Path(cfg.storage.parquet_root))

    async def run(
        self,
        strategy: str,
        start: str,
        end: str,
        *,
        timeframe: str = "5m",
        instruments: Iterable[Instrument] | None = None,
    ) -> BacktestResult:
        from trader.strategies.registry import build_strategy

        assert self._cfg is not None
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        # Parquet columns are tz-aware UTC (see marketdata.backfill). PyArrow's
        # dataset filter refuses to compare a tz-aware column with a naive
        # scalar and silently returns zero rows; normalise here so a plain
        # ``YYYY-MM-DD`` on the CLI still matches the stored bars.
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        insts = list(instruments) if instruments else self._demo_universe()
        inst_map = {i.security_id: i for i in insts}

        bars: list[Bar] = []
        assert self.store is not None
        for i in insts:
            df = self.store.read_bars(timeframe, i.security_id, start_dt, end_dt)
            for row in df.iter_rows(named=True):
                bars.append(_row_to_bar(row))
        bars.sort(key=lambda b: b.ts_open)

        strat = build_strategy(strategy, self._cfg)
        engine = BacktestEngine(
            starting_nav=self._cfg.capital.nav,
            instruments=inst_map,
        )
        return engine.run(bars, strat.on_bar)

    def _demo_universe(self) -> list[Instrument]:
        # Small default universe for smoke tests. Real universe comes from
        # `apps/marketdata/universe` in Phase 2.
        return [
            Instrument(
                security_id="2885",
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                segment=Segment.EQUITY,
                asset_class=AssetClass.EQUITY,
                lot_size=1,
            ),
        ]


def _row_to_bar(row: dict) -> Bar:
    return Bar(
        instrument_id=row["instrument_id"],
        ts_open=row["ts_open"],
        ts_close=row["ts_close"],
        timeframe=row["timeframe"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"] or 0,
        oi=row.get("oi"),
    )
