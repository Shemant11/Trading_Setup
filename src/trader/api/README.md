# trader.api

FastAPI control + dashboard.

* `/`               HTML dashboard (health + positions + orders).
* `/health`         Aggregated health JSON.
* `/metrics`        Prometheus scrape (OpenMetrics text).
* `/api/positions`  JSON positions from the journal.
* `/api/orders/open` JSON open orders.
* `/api/halt`       Toggle kill switch (file + Redis).

Binds `127.0.0.1` by default — no inbound network exposure unless the user opts in.
