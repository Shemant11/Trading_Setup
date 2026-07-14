# Runbook: Broker outage

Historical incidence: 2-3 outages/year per broker (Dhan/Groww).

## Detection

The engine detects an outage via any of:

* p95 REST latency > 1 s for 60 s.
* WS heartbeat missing > 10 s.
* Auth error (token expiry).

## Automatic response

* **Equity:** Router failovers Dhan → Groww if Groww is healthy. No manual step.
* **Options:** No failover. Existing options positions continue to be marked by the last known price. **New options entries blocked.**
* **If both brokers unhealthy** → kill switch triggers automatically.

## Manual response

1. Confirm with each broker's status page.
2. Note the exact minute in the postmortem log.
3. If the outage exceeds 5 minutes and you have MIS positions carrying overnight risk (options), manually force-exit or use the broker's web UI as backup.
4. Do NOT manually place duplicate orders while the process is running; you will double-fill.

## Recovery

1. Verify healthy via `trader ping-brokers`.
2. Reconcile positions: `POST /api/positions/reconcile`.
3. If reconciliation flags mismatches, acknowledge in the dashboard before enabling new entries.

## After

Add postmortem entry:
* Broker(s) affected.
* Duration.
* Positions and P&L impact.
* Any manual interventions.
