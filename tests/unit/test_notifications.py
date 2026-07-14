"""Notifier + dispatcher tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import List

import pytest

from trader.notifications import (
    LoggingNotifier,
    NotificationDispatcher,
    NotifierMessage,
    Severity,
)
from trader.notifications.base import Notifier


@dataclass
class _Recorder(Notifier):
    min_severity: Severity = Severity.INFO
    name: str = "recorder"
    calls: List[NotifierMessage] = field(default_factory=list)

    async def send(self, msg: NotifierMessage) -> bool:
        if msg.severity < self.min_severity:
            return False
        self.calls.append(msg)
        return True


async def _run(dispatcher, msg):
    return await dispatcher.dispatch(msg)


def test_dispatcher_sends_all_channels():
    r1 = _Recorder()
    r2 = _Recorder(name="r2")
    d = NotificationDispatcher(notifiers=[r1, r2])
    msg = NotifierMessage(title="hi", body="world", severity=Severity.INFO)
    asyncio.run(_run(d, msg))
    assert len(r1.calls) == 1
    assert len(r2.calls) == 1


def test_dispatcher_dedup_within_window():
    r = _Recorder()
    d = NotificationDispatcher(notifiers=[r], dedup_seconds=10)
    m1 = NotifierMessage(title="x", body="a", severity=Severity.INFO)
    m2 = NotifierMessage(title="x", body="b", severity=Severity.INFO)  # dedup
    asyncio.run(_run(d, m1))
    asyncio.run(_run(d, m2))
    assert len(r.calls) == 1


def test_critical_bypasses_dedup():
    r = _Recorder(min_severity=Severity.INFO)
    d = NotificationDispatcher(notifiers=[r], dedup_seconds=10)
    m1 = NotifierMessage(title="crit", body="1", severity=Severity.CRITICAL)
    m2 = NotifierMessage(title="crit", body="2", severity=Severity.CRITICAL)
    asyncio.run(_run(d, m1))
    asyncio.run(_run(d, m2))
    assert len(r.calls) == 2


def test_severity_filtering():
    r = _Recorder(min_severity=Severity.WARNING)
    d = NotificationDispatcher(notifiers=[r])
    asyncio.run(_run(d, NotifierMessage(title="x", body="", severity=Severity.INFO)))
    assert r.calls == []
    asyncio.run(_run(d, NotifierMessage(title="x", body="", severity=Severity.WARNING)))
    assert len(r.calls) == 1


def test_logging_notifier():
    n = LoggingNotifier()
    ok = asyncio.run(n.send(NotifierMessage(title="t", body="b")))
    assert ok is True
