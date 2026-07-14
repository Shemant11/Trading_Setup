"""Safe-mode-on-boot.

The single biggest local-deployment risk: a crash or power cut leaves
positions open. Safe mode forces a broker reconciliation before *any* new
entries are allowed. Existing exit orders are always permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from trader.observability.logging import get_logger
from trader.portfolio.reconciler import ReconciliationResult

logger = get_logger("trader.ops.safe_mode")


class SafeModeStatus(StrEnum):
    ARMED = "armed"        # boot state; only exits allowed
    REVIEW = "review"      # reconciliation mismatch — human ack required
    CLEARED = "cleared"    # user acknowledged; new entries allowed


@dataclass
class SafeModeGate:
    """Owns safe-mode state + human acknowledgment.

    The dashboard exposes a `/api/safe-mode/ack` endpoint that sets `cleared`.
    """

    status: SafeModeStatus = SafeModeStatus.ARMED
    entered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_reconciliation: Optional[ReconciliationResult] = None
    ack_reason: Optional[str] = None

    def observe_reconciliation(self, r: ReconciliationResult) -> None:
        self.last_reconciliation = r
        if r.ok:
            logger.info("safe_mode_reconciled_ok", summary=r.summary())
            # Still needs human ack per policy.
        else:
            self.status = SafeModeStatus.REVIEW
            logger.warning("safe_mode_reconciliation_mismatch", summary=r.summary())

    def acknowledge(self, reason: str) -> None:
        self.status = SafeModeStatus.CLEARED
        self.ack_reason = reason
        logger.info("safe_mode_cleared", reason=reason)

    @property
    def allows_new_entries(self) -> bool:
        return self.status == SafeModeStatus.CLEARED
