# trader.marketdata

Ingestion + normalization.

* `client.py` — WS subscribe fan-out with bounded backpressure.
* `backfill.py` — Async historical OHLC → Parquet.
* `universe.py` — Weekly liquidity / spread / circuit filter.
* `chain_snapshotter.py` — Option chain poller + IV/greeks enrichment + subscriber fan-out.
