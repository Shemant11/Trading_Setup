"""Job registrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.observability.logging import get_logger

logger = get_logger("trader.scheduler")


AsyncJob = Callable[[], Awaitable[None]]


@dataclass
class Scheduler:
    scheduler: AsyncIOScheduler = field(default_factory=AsyncIOScheduler)

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001, S110
            pass

    def add_daily(self, name: str, hour: int, minute: int, job: AsyncJob, tz: str = "Asia/Kolkata") -> None:
        self.scheduler.add_job(
            _wrap(job, name),
            CronTrigger(hour=hour, minute=minute, timezone=tz, day_of_week="mon-fri"),
            id=name,
            replace_existing=True,
        )

    def add_interval(self, name: str, seconds: int, job: AsyncJob) -> None:
        self.scheduler.add_job(
            _wrap(job, name),
            "interval",
            seconds=seconds,
            id=name,
            replace_existing=True,
        )


def _wrap(job: AsyncJob, name: str) -> AsyncJob:
    async def _run() -> None:
        try:
            logger.info("scheduled_job_start", job=name)
            await job()
            logger.info("scheduled_job_ok", job=name)
        except Exception as e:  # noqa: BLE001
            logger.error("scheduled_job_failed", job=name, error=str(e))
    return _run


def register_default_jobs(sch: Scheduler, hooks: dict[str, AsyncJob]) -> None:
    """Wire up the trading day cadence.

    Expected hook keys: `pre_market_refresh`, `compute_regime`,
    `mis_auto_square`, `eod_report`, `reconcile_positions`.
    """
    if "pre_market_refresh" in hooks:
        sch.add_daily("pre_market_refresh", hour=8, minute=30, job=hooks["pre_market_refresh"])
    if "compute_regime" in hooks:
        sch.add_daily("compute_regime", hour=9, minute=20, job=hooks["compute_regime"])
    if "mis_auto_square" in hooks:
        sch.add_daily("mis_auto_square", hour=15, minute=15, job=hooks["mis_auto_square"])
    if "eod_report" in hooks:
        sch.add_daily("eod_report", hour=15, minute=45, job=hooks["eod_report"])
    if "reconcile_positions" in hooks:
        sch.add_interval("reconcile_positions", seconds=60, job=hooks["reconcile_positions"])
