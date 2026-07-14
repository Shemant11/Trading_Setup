# trader.brokers

Broker abstraction + adapters.

- `base.py` — `Broker` ABC + `BrokerCapabilities` + normalized shapes.
- `exceptions.py` — Error taxonomy.
- `dhan/` — Primary broker; full support (equity + F&O + WS).
- `groww/` — Failover broker for cash equity only.

Rules:

- Options **never** failover to Groww.
- `Broker.place_order` MUST be idempotent by `client_order_id`.
- Every adapter surfaces WS disconnects to `WS_DISCONNECTS` metric.
