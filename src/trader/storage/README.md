# trader.storage

- `models.py` — SQLAlchemy 2.0 ORM tables.
- `database.py` — Async engine wrapper with SQLite PRAGMAs (WAL, sync=NORMAL, foreign_keys=ON).
- `journal.py` — All writes and reads that touch the ledger; every state transition goes through here.
- `redis_client.py` — Streams (XADD/XREAD) + flags.
- `parquet_store.py` — Partitioned Parquet store for ticks/bars/option chain.

Migrations live in `migrations/versions/` and are applied via `alembic upgrade head`.
