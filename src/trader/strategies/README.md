# trader.strategies

Every strategy subclasses `Strategy` and self-registers with `register_strategy`.

* `equity_orb` — Opening Range Breakout with auction confirmation.
* `equity_vwap_mr` — VWAP mean reversion (CHOP regime).
* `options_iron_condor` — IVR > 70, range regime.
* `options_debit_spread` — IVR < 30, trending.
* `options_expiry_butterfly` — Expiry-day pin play.
* `swing_breakout` — Stage 2 base breakout on daily bars.

Rule: strategies emit Signals only. They MUST NOT call brokers directly.
