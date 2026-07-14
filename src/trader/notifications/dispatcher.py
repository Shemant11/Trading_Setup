"""Dispatch a message to all registered notifiers concurrently.

Also implements a rate-limited de-duplicator so repeated alerts (broker
outage flapping, e.g.) don't spam Telegram.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Iterable

from trader.notifications.base import Notifier, NotifierMessage, Severity
from trader.observability.logging import get_logger

logger = get_logger("trader.notify.dispatch")


@dataclass
class LoggingNotifier(Notifier):
    """A trivial notifier that just logs — used as a safety-net fallback."""

    min_severity: Severity = Severity.INFO
    name: str = "log"

    async def send(self, msg: NotifierMessage) -> bool:
        logger.info("notification", title=msg.title, body=msg.body, severity=msg.severity.name)
        return True


@dataclass
class NotificationDispatcher:
    notifiers: list[Notifier] = field(default_factory=list)
    dedup_seconds: float = 60.0
    _last_sent: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def add(self, notifier: Notifier) -> None:
        self.notifiers.append(notifier)

    def _dedup_key(self, msg: NotifierMessage) -> str:
        return f"{msg.severity.name}|{msg.title}"

    def _should_send(self, msg: NotifierMessage) -> bool:
        # CRITICAL always goes through; other severities dedup.
        if msg.severity >= Severity.CRITICAL:
            return True
        key = self._dedup_key(msg)
        last = self._last_sent.get(key, 0)
        now = time.monotonic()
        if now - last < self.dedup_seconds:
            return False
        self._last_sent[key] = now
        return True

    async def dispatch(self, msg: NotifierMessage) -> dict[str, bool]:
        if not self._should_send(msg):
            return {n.name: False for n in self.notifiers}
        if not self.notifiers:
            logger.info("notification_no_channels", title=msg.title)
            return {}
        results = await asyncio.gather(
            *(self._safe_send(n, msg) for n in self.notifiers), return_exceptions=False
        )
        return {n.name: r for n, r in zip(self.notifiers, results, strict=True)}

    async def _safe_send(self, n: Notifier, msg: NotifierMessage) -> bool:
        try:
            return await n.send(msg)
        except Exception as e:  # noqa: BLE001
            logger.warning("notifier_exception", notifier=n.name, error=str(e))
            return False
