"""Notifier abstractions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Protocol, runtime_checkable


class Severity(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    CRITICAL = 40


@dataclass(slots=True)
class NotifierMessage:
    title: str
    body: str
    severity: Severity = Severity.INFO
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = field(default_factory=list)

    def format_plain(self) -> str:
        header = f"[{self.severity.name}] {self.title}"
        if self.tags:
            header += "  " + " ".join(f"#{t}" for t in self.tags)
        return f"{header}\n\n{self.body}"


@runtime_checkable
class Notifier(Protocol):
    name: str
    min_severity: Severity

    async def send(self, msg: NotifierMessage) -> bool: ...
