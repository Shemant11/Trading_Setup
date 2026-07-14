# trader.ops

Local ops primitives:

* `safe_mode.py` — On-boot reconciliation gate. New entries blocked until human ack.
* `watchdog.py` — Latency / WS-disconnect / clock-drift halts.
