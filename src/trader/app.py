"""Application wiring.

Constructs the full object graph and coordinates start/stop. Kept small — the
individual modules do the work; this file just hands them their dependencies.
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from trader.brokers import DhanClient, GrowwClient
from trader.brokers.base import Broker
from trader.config import (
    AppConfig,
    Settings,
    get_settings,
    load_config,
    load_secrets,
    resolve_passphrase,
)
from trader.notifications import (
    EmailNotifier,
    LoggingNotifier,
    NotificationDispatcher,
    TelegramNotifier,
)
from trader.observability import (
    HealthMonitor,
    HealthResult,
    HealthStatus,
    bootstrap_logging,
    get_logger,
)
from trader.observability.metrics import KILL_SWITCH_ACTIVE
from trader.storage import Database, Journal, RedisClient, create_database

logger = get_logger("trader.app")


@dataclass
class Application:
    """Top-level composition root."""

    settings: Settings
    config: AppConfig
    db: Database
    redis: RedisClient
    journal: Journal
    brokers: dict[str, Broker]
    notifier: NotificationDispatcher
    health: HealthMonitor
    _shutdown: asyncio.Event = field(default_factory=asyncio.Event)

    # ---------- construction ----------------------------------------------

    @classmethod
    async def build(cls, config_path: Path) -> Application:
        settings = get_settings()
        bootstrap_logging(
            level=settings.log_level, json=settings.log_json, log_dir=settings.log_dir
        )
        config = load_config(config_path)

        # Secrets
        passphrase = resolve_passphrase(settings.secrets_passphrase, settings.secrets_file)
        secrets = load_secrets(settings.secrets_file, passphrase) if passphrase else None

        # Storage
        db = create_database(config.storage.db_url)
        redis_enabled = bool(config.storage.redis_enabled)
        redis = RedisClient.create(
            config.storage.redis_url or "", enabled=redis_enabled
        )
        if not redis_enabled:
            logger.info("redis_disabled", reason="not configured")
        journal = Journal(db=db)

        # Brokers
        brokers: dict[str, Broker] = {}
        if secrets and secrets.get("dhan_client_id") and secrets.get("dhan_access_token"):
            brokers["dhan"] = DhanClient(
                client_id=secrets.require("dhan_client_id"),
                access_token=secrets.require("dhan_access_token"),
            )
        if secrets and secrets.get("groww_api_key") and secrets.get("groww_api_secret"):
            brokers["groww"] = GrowwClient(
                api_key=secrets.require("groww_api_key"),
                api_secret=secrets.require("groww_api_secret"),
            )

        # Notifications
        notifier = NotificationDispatcher()
        notifier.add(LoggingNotifier())
        if config.notifications.telegram.enabled and secrets and secrets.get(
            "telegram_bot_token"
        ):
            chats_raw = secrets.get("telegram_chat_ids", "")
            chats = [c.strip() for c in str(chats_raw).split(",") if c.strip()]
            if chats:
                notifier.add(
                    TelegramNotifier(
                        bot_token=secrets.require("telegram_bot_token"),
                        chat_ids=chats,
                    )
                )
        if config.notifications.email.enabled and secrets and secrets.get("smtp_username"):
            notifier.add(
                EmailNotifier(
                    smtp_host=config.notifications.email.smtp_host,
                    smtp_port=config.notifications.email.smtp_port,
                    from_addr=config.notifications.email.from_addr
                    or secrets.get("smtp_username"),
                    to_addrs=config.notifications.email.to_addrs,
                    username=secrets.get("smtp_username"),
                    password=secrets.get("smtp_password"),
                )
            )

        # Health
        health = HealthMonitor()

        async def _db_check() -> HealthResult:
            try:
                async with db.session() as s:
                    await s.execute(_select_1())
                return HealthResult(HealthStatus.OK, "ok")
            except Exception as e:  # noqa: BLE001
                return HealthResult(HealthStatus.DOWN, str(e))

        health.register("db", _db_check)

        if redis_enabled:
            # One-shot startup ping. If Redis is documented as optional but the
            # user *did* configure a URL, we still want to be graceful when the
            # daemon happens to be down at boot — log ONCE and skip registering
            # the recurring check so /health polls don't spam warnings.
            first_ping_ok = await redis.ping()
            if not first_ping_ok:
                logger.warning(
                    "redis_unavailable",
                    url=config.storage.redis_url,
                    detail="falling back to in-process bus (health check will be skipped)",
                )
            else:
                # Register a throttled recurring check. State lives on the
                # closure so we don't need a new module-level singleton.
                redis_state: dict[str, float | bool] = {
                    "last_warn_ts": 0.0,
                    "was_down": False,
                }
                warn_interval_sec = 300.0

                async def _redis_check() -> HealthResult:
                    ok = await redis.ping()
                    now = time.monotonic()
                    if ok:
                        if redis_state["was_down"]:
                            logger.info("redis_recovered", url=config.storage.redis_url)
                            redis_state["was_down"] = False
                            redis_state["last_warn_ts"] = 0.0
                        return HealthResult(HealthStatus.OK, "ok")
                    redis_state["was_down"] = True
                    if now - float(redis_state["last_warn_ts"]) > warn_interval_sec:
                        logger.warning(
                            "redis_ping_failed",
                            url=config.storage.redis_url,
                        )
                        redis_state["last_warn_ts"] = now
                    else:
                        logger.debug(
                            "redis_ping_failed",
                            url=config.storage.redis_url,
                        )
                    return HealthResult(HealthStatus.DEGRADED, "ping failed")

                health.register("redis", _redis_check)
        for name, broker in brokers.items():
            def _factory(b: Broker = broker):
                async def _check() -> HealthResult:
                    ok = await b.healthy()
                    return HealthResult(
                        HealthStatus.OK if ok else HealthStatus.DEGRADED,
                        "ok" if ok else "broker unhealthy",
                    )
                return _check
            health.register(f"broker:{name}", _factory())

        return cls(
            settings=settings,
            config=config,
            db=db,
            redis=redis,
            journal=journal,
            brokers=brokers,
            notifier=notifier,
            health=health,
        )

    # ---------- lifecycle -------------------------------------------------

    async def start(self) -> None:
        logger.info("application_starting")
        for name, broker in self.brokers.items():
            try:
                await broker.connect()
                logger.info("broker_connected", broker=name)
            except Exception as e:  # noqa: BLE001
                logger.error("broker_connect_failed", broker=name, error=str(e))
        await self.journal.record_run_event("boot", detail=f"env={self.settings.env}")

    async def stop(self) -> None:
        logger.info("application_stopping")
        for name, broker in self.brokers.items():
            try:
                await broker.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("broker_close_failed", broker=name, error=str(e))
        await self.redis.close()
        await self.db.dispose()
        try:
            await self.journal.record_run_event("shutdown")
        except Exception:  # noqa: BLE001, S110
            pass

    async def wait_for_shutdown(self) -> None:
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:  # pragma: no cover (Windows)
                signal.signal(sig, lambda *_: self._shutdown.set())
        await self._shutdown.wait()

    # ---------- convenience commands --------------------------------------

    @classmethod
    async def launch(cls, config_path: Path, dry_run: bool = False) -> None:
        appn = await cls.build(config_path)
        try:
            await appn.start()
            if dry_run:
                logger.info("dry_run_boot_ok")
                return
            # Phase 0 has no engines yet; keep API + wait for signal.
            from trader.api.server import ApiServer  # local import to avoid cycles
            api = ApiServer(appn)
            await api.serve_until(appn.wait_for_shutdown())
        finally:
            await appn.stop()

    @classmethod
    async def status_only(cls, cfg: AppConfig) -> dict[str, HealthResult]:
        # Lightweight probe — build a stripped-down app with just db+redis.
        db = create_database(cfg.storage.db_url)
        redis_enabled = bool(cfg.storage.redis_enabled)
        redis = RedisClient.create(cfg.storage.redis_url or "", enabled=redis_enabled)
        health = HealthMonitor()

        async def _db() -> HealthResult:
            try:
                async with db.session() as s:
                    await s.execute(_select_1())
                return HealthResult(HealthStatus.OK, "ok")
            except Exception as e:  # noqa: BLE001
                return HealthResult(HealthStatus.DOWN, str(e))

        health.register("db", _db)

        if redis_enabled:
            async def _rd() -> HealthResult:
                ok = await redis.ping()
                return HealthResult(
                    HealthStatus.OK if ok else HealthStatus.DEGRADED,
                    "ok" if ok else "ping failed",
                )

            health.register("redis", _rd)
        try:
            return await health.run()
        finally:
            await redis.close()
            await db.dispose()

    @classmethod
    async def ping_brokers(cls, settings: Settings) -> dict[str, bool]:
        passphrase = resolve_passphrase(settings.secrets_passphrase, settings.secrets_file)
        secrets = load_secrets(settings.secrets_file, passphrase) if passphrase else None
        results: dict[str, bool] = {}
        if secrets and secrets.get("dhan_client_id") and secrets.get("dhan_access_token"):
            b = DhanClient(
                client_id=secrets.require("dhan_client_id"),
                access_token=secrets.require("dhan_access_token"),
            )
            try:
                await b.connect()
                results["dhan"] = await b.healthy()
            finally:
                await b.close()
        else:
            results["dhan"] = False
        if secrets and secrets.get("groww_api_key") and secrets.get("groww_api_secret"):
            g = GrowwClient(
                api_key=secrets.require("groww_api_key"),
                api_secret=secrets.require("groww_api_secret"),
            )
            try:
                await g.connect()
                results["groww"] = await g.healthy()
            finally:
                await g.close()
        else:
            results["groww"] = False
        return results


def _select_1():
    from sqlalchemy import text
    return text("SELECT 1")
