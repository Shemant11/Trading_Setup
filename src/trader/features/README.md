# trader.features

Streaming features (stateful, on-line). Complements `indicators` (pure functions).

* `session.py` — `SessionVWAP`, `SessionOR` (session-anchored, auto-reset by IST day).
* `streaming.py` — `RollingBar`, `RollingATR`, `RollingVolatility`, `RollingZScore`, `RollingBookImbalance`.
* `bar_builder.py` — Ticks → time-aligned OHLCV bars per instrument.
