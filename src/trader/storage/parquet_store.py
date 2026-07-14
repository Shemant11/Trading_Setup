"""Parquet tick / bar store.

Directory layout on disk:

    {root}/
        ticks/{yyyy}/{mm}/{dd}/{security_id}.parquet
        bars/{timeframe}/{yyyy}/{mm}/{security_id}.parquet
        options_chain/{underlying}/{yyyy}/{mm}/{dd}.parquet

Reads use pyarrow.dataset for efficient partition pruning; writes append via
pyarrow.parquet.ParquetWriter (append per file, one file per symbol per day
for ticks/options chain, per month for bars).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import polars as pl
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from trader.observability.logging import get_logger

logger = get_logger("trader.storage.parquet")


@dataclass
class ParquetStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(os.path.expanduser(str(self.root))).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- path helpers ------------------------------------------------

    def _ticks_path(self, day: date, security_id: str) -> Path:
        return (
            self.root
            / "ticks"
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%d}"
            / f"{security_id}.parquet"
        )

    def _bars_path(self, timeframe: str, month_start: date, security_id: str) -> Path:
        return (
            self.root
            / "bars"
            / timeframe
            / f"{month_start:%Y}"
            / f"{month_start:%m}"
            / f"{security_id}.parquet"
        )

    def _options_chain_path(self, underlying: str, day: date) -> Path:
        return (
            self.root
            / "options_chain"
            / underlying
            / f"{day:%Y}"
            / f"{day:%m}"
            / f"{day:%d}.parquet"
        )

    # ---------- writers -----------------------------------------------------

    def write_ticks(self, security_id: str, day: date, rows: Iterable[dict]) -> int:
        path = self._ticks_path(day, security_id)
        return self._append_rows(path, rows)

    def write_bars(
        self, timeframe: str, security_id: str, month_start: date, rows: Iterable[dict]
    ) -> int:
        path = self._bars_path(timeframe, month_start, security_id)
        return self._append_rows(path, rows)

    def write_option_chain(self, underlying: str, day: date, rows: Iterable[dict]) -> int:
        path = self._options_chain_path(underlying, day)
        return self._append_rows(path, rows)

    def _append_rows(self, path: Path, rows: Iterable[dict]) -> int:
        materialized = list(rows)
        if not materialized:
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(materialized)
        table = df.to_arrow()
        if path.exists():
            existing = pq.read_table(path)
            table = pa.concat_tables([existing, table], promote_options="default")
        pq.write_table(table, path, compression="zstd")
        return len(materialized)

    # ---------- readers -----------------------------------------------------

    def read_bars(
        self, timeframe: str, security_id: str, start: datetime, end: datetime
    ) -> pl.DataFrame:
        """Load bars in [start, end) as a Polars DataFrame.

        The row-level filter is done in Polars (not pyarrow's dataset filter)
        because pyarrow silently returns zero rows on any tz mismatch between
        the query scalar and the stored column. Polars will coerce naive vs
        tz-aware datetimes into a comparable form, so callers can pass either.
        """
        dir_ = self.root / "bars" / timeframe
        if not dir_.exists():
            return pl.DataFrame()
        files: list[str] = []
        cur = date(start.year, start.month, 1)
        end_month = date(end.year, end.month, 1)
        while cur <= end_month:
            p = self._bars_path(timeframe, cur, security_id)
            if p.exists():
                files.append(str(p))
            if cur.month == 12:
                cur = date(cur.year + 1, 1, 1)
            else:
                cur = date(cur.year, cur.month + 1, 1)
        if not files:
            return pl.DataFrame()
        table = ds.dataset(files, format="parquet").to_table()
        df = pl.from_arrow(table)
        if df.is_empty():
            return df

        # Align tz of the scalars with the actual column dtype so the filter
        # is always comparing like-with-like.
        col_dtype = df.schema["ts_open"]
        col_tz = getattr(col_dtype, "time_zone", None) if isinstance(
            col_dtype, pl.Datetime
        ) else None
        if col_tz is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        else:
            if start.tzinfo is not None:
                start = start.astimezone(timezone.utc).replace(tzinfo=None)
            if end.tzinfo is not None:
                end = end.astimezone(timezone.utc).replace(tzinfo=None)

        return (
            df.filter(
                (pl.col("ts_open") >= start) & (pl.col("ts_open") < end)
            ).sort("ts_open")
        )
