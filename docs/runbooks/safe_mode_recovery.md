# Runbook: Safe-mode recovery after crash / power cut

## When it applies

Anytime the trader process was killed / crashed / OS restarted while the
market was open.

## What safe-mode does

On boot:

1. Loads the last-known positions from the journal.
2. Fetches broker positions.
3. Reconciles. Any delta → `safe_mode = REVIEW`.
4. **New entries are blocked** until you acknowledge.
5. Existing exit orders are honored.

## Your steps

1. **Do not panic-exit** — this often makes things worse than sitting.
2. Open the dashboard. Check the reconciliation report (top card).
3. If matched: click *Acknowledge safe-mode*. The trader resumes.
4. If mismatched:
   - Inspect the delta line by line.
   - Decide per position: hold at broker, force-flat manually, or manually update the journal via `scripts/journal_repair.py`.
   - Only then acknowledge safe-mode.
5. Add an entry to `postmortem_template.md`.
