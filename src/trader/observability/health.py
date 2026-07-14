"""Health check registry.

Components register async `HealthCheck` functions. The monitor aggregates them
into an overall status for `/health` and boot-time gating.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Callable


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class HealthResult:
    status: HealthStatus
    detail: str = ""


HealthCheck = Callable[[], Awaitable[HealthResult]]


@dataclass
class HealthMonitor:
    checks: dict[str, HealthCheck] = field(default_factory=dict)

    def register(self, name: str, check: HealthCheck) -> None:
        self.checks[name] = check

    async def run(self) -> dict[str, HealthResult]:
        names = list(self.checks.keys())
        coros = [self.checks[n]() for n in names]
        results = await asyncio.gather(*coros, return_exceptions=True)
        out: dict[str, HealthResult] = {}
        for name, res in zip(names, results, strict=True):
            if isinstance(res, Exception):
                out[name] = HealthResult(HealthStatus.DOWN, f"exception: {res!r}")
            else:
                out[name] = res
        return out

    def summarize(self, results: dict[str, HealthResult]) -> HealthStatus:
        if any(r.status == HealthStatus.DOWN for r in results.values()):
            return HealthStatus.DOWN
        if any(r.status == HealthStatus.DEGRADED for r in results.values()):
            return HealthStatus.DEGRADED
        return HealthStatus.OK
