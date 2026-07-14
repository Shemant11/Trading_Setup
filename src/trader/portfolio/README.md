# trader.portfolio

* `manager.py` — Live `PortfolioManager`. Owns positions + PnL. Feeds journal + metrics.
* `reconciler.py` — Compare local + broker views; returns a `ReconciliationResult`.
