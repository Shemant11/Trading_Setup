# Architecture

This document is the technical companion to the top-level design in `docs/../..` plan. It reflects the code as it stands today.

## Layers

```
apps/api  ─┐
           ├─ Application ─┐
scheduler ─┘               ├─► Journal ──► SQLite/Postgres
                           ├─► RedisClient
                           ├─► Brokers (Dhan, Groww)
                           ├─► NotificationDispatcher
                           └─► HealthMonitor
```

## Data Ownership

- **Journal / DB** — append-only source of truth for orders, fills, trades, signals, risk events, run log. Positions are the only mutable row (reconciled to broker on start and every 60 s).
- **Parquet Store** — high-volume ticks and bars. Partitioned by date/symbol. Never mutated after write.
- **Redis** — ephemeral: kill-switch flag, feature cache, event streams. Losing Redis stops trading but never loses journal state.

## Broker Adapters

Every adapter implements the same `Broker` ABC. `BrokerCapabilities` advertises what the adapter supports so higher layers can gate routing (Groww is equity-only failover; options never route to Groww).

Adapter code lives under `trader.brokers.<name>/`. Split into:

- `client.py`   Broker facade.
- `rest.py`     HTTP client with metrics, retries, error classification.
- `websocket.py` Market feed + order update WS.
- `mapping.py`  Enum / string translation.

## Error taxonomy

- `AuthError` — 401/403 or expired token. Not auto-retried; alert.
- `RateLimitError` — 429. Auto-retried with backoff.
- `TransientBrokerError` — 5xx / network / timeout. Auto-retried.
- `OrderRejectedError` — Structural (margin, price band). Not auto-retried.
- `BrokerError` — Base. Unknown 4xx.

## Observability

- **structlog** JSON logs to stdout + rotated `logs/trader.log`.
- **Prometheus** counters and histograms; `/metrics` scrape.
- **Health checks** aggregated at `/health` for the dashboard.

## Secrets

Argon2id-derived key + AES-256-GCM inside `~/.trader/secrets.enc`. Passphrase is prompted at process start (or read from `TRADER_SECRETS_PASSPHRASE` env). See `trader.config.secrets`.

## Kill switch

Three redundant channels — any of these halts new entries:

1. `~/.trader/halt.lock` file present.
2. Redis flag `trader:halt == "1"`.
3. Signed Telegram command (Phase 5).

The API endpoint `POST /api/halt` toggles the file + Redis flag together.
