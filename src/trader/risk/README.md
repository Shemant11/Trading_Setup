# trader.risk

Four-layer risk engine, kill switch, greeks overlay, capital ramp.

* `sizing.py` — Kelly + vol-normalized + notional cap sizers.
* `limits.py` — Book / strategy / loss-limit state containers.
* `engine.py` — `RiskEngine.check(signal)` — the single pre-trade gate.
* `kill_switch.py` — File + Redis + manual triggers.
* `greeks_overlay.py` — Book-level greek caps for options.
* `capital_ramp.py` — 10 → 25 → 50 → 100 % staged ramp with pause on breach.

All state is in-memory and reset per session via `LimitState.start_of_day_reset`.
