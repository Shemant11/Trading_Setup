# trader.execution

Only path from Signal → Order → Broker.

* `state_machine.py` — Enforces legal `OrderStatus` transitions.
* `router.py` — `SmartOrderRouter` (Dhan default, Groww failover for equity only, options never failover).
* `gateway.py` — `ExecutionGateway` wires risk + router + journal + slicing.

Idempotency: `client_order_id` is a UUID minted by the gateway. Brokers reject duplicates.
