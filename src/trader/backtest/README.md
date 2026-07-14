# trader.backtest

Event-driven engine used for both backtesting and paper trading (via
`SimulatedBroker`).

* `cost_model.py` — Dhan brokerage schedule + statutory charges + square-root impact model.
* `simulator.py` — Bar-based fill simulator + `SimulatedBroker` façade.
* `portfolio.py` — In-memory FIFO position/PnL tracker.
* `engine.py` — Iterates bars, calls the strategy, applies risk + simulator, records trades.
* `metrics.py` — Sharpe / Sortino / Calmar / DD / Ulcer / tail-ratio.
* `runner.py` — CLI-facing entry (`trader backtest STRATEGY START END`).
