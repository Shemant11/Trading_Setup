# trader.scheduler

APScheduler-based in-process cadence:

| time (IST) | job                     | purpose                              |
|-----------|--------------------------|--------------------------------------|
| 08:30     | `pre_market_refresh`     | CA adjustments, universe refresh     |
| 09:20     | `compute_regime`         | Regime classifier daily inference    |
| 15:15     | `mis_auto_square`        | Force-close intraday positions       |
| 15:45     | `eod_report`             | Telegram + email EOD                 |
| every 60s | `reconcile_positions`    | Broker ↔ journal reconciliation      |
