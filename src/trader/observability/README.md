# trader.observability

* `logging.py` — structlog bootstrap; JSON to files, pretty on console (dev only).
* `metrics.py` — Prometheus counters/gauges/histograms used across the app.
* `health.py` — `HealthMonitor` + `HealthCheck` protocol used by the dashboard `/health`.
