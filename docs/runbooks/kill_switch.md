# Runbook: Kill switch

## Trigger

Any of:

* Broker outage on **both** Dhan and Groww.
* Broker–journal position mismatch (reconciliation delta > 0 shares).
* Nifty ±2 % in 15 min → auto-halve; ±3.5 % → auto-halt.
* You believe there is an execution bug in production.

## Activate

Three interchangeable channels:

1. **File:** `touch ~/.trader/halt.lock` (works even if the process is unresponsive).
2. **API:** `curl -X POST http://127.0.0.1:8000/api/halt`
3. **Redis:** `redis-cli set trader:halt 1`

The process picks these up within one risk-check cycle (< 200 ms).

## Verify

* Dashboard header shows `HALTED`.
* `GET /health` returns `kill_switch: active`.
* Prometheus metric `trader_kill_switch_active == 1`.

## While halted

* Existing orders continue to their natural terminal state.
* No new entries. Exits ARE allowed.
* Notifications: Telegram + email at CRITICAL severity.

## Resume

Only after the trigger cause has been resolved and a manual reconciliation
report is `ok`:

```bash
rm ~/.trader/halt.lock
curl -X POST http://127.0.0.1:8000/api/halt   # toggles off if file gone
```

Then confirm at the dashboard: `Safe mode: cleared`.

Add a note to the postmortem log with root cause + timeline.
