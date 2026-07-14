"""Market data ingestion + normalization.

Sources:

* Historical OHLC — Dhan REST (`/charts/intraday`, `/charts/historical`).
* Live tick — Dhan WS (primary), Groww WS (backup, equity only).
* Corporate actions — Dhan REST.

Outputs:

* Parquet tick store (`data/parquet/ticks/...`).
* Parquet bar store (`data/parquet/bars/...`).
* Redis Stream `md:ticks:{security_id}` for strategy consumption.
"""

from trader.marketdata.client import MarketDataClient
from trader.marketdata.backfill import BackfillJob, backfill_bars
from trader.marketdata.universe import UniverseBuilder

__all__ = ["MarketDataClient", "BackfillJob", "backfill_bars", "UniverseBuilder"]
