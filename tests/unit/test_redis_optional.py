"""Tests for the "Redis is optional" path.

Covers:

* ``RedisClient`` is fully inert when ``enabled=False`` and never touches the
  network — ``ping()`` returns True, writes are no-ops, reads yield None/False.
* ``StorageSection`` infers ``redis_enabled=False`` from an empty / ``None`` /
  ``"disabled"`` ``redis_url`` so users don't need two knobs.
* The ``HealthMonitor`` registration count is smaller when Redis is off,
  which is what actually silences the /health poll spam.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import yaml

from trader.config.loader import StorageSection, load_config
from trader.observability.health import HealthMonitor, HealthResult, HealthStatus
from trader.storage import redis_client as redis_client_mod
from trader.storage.redis_client import RedisClient


def _run(coro):
    return asyncio.run(coro)


# ---------- Client short-circuits ---------------------------------------------


def test_disabled_client_ping_is_true_and_offline():
    client = RedisClient.create("redis://localhost:6379/0", enabled=False)
    assert client.enabled is False
    assert client.client is None
    assert _run(client.ping()) is True


def test_disabled_client_writes_are_noops():
    client = RedisClient.create("", enabled=False)

    async def go():
        await client.set_flag("trader:halt", True)
        assert await client.get_flag("trader:halt") is False
        await client.set("k", "v")
        assert await client.get("k") is None
        assert await client.xadd("stream", {"a": 1}) == ""
        await client.close()

    _run(go())


def test_enabled_client_ping_delegates_to_backing_client():
    # Inject an AsyncMock — no real Redis daemon needed.
    fake = MagicMock()
    fake.ping = AsyncMock(return_value=True)
    client = RedisClient(url="redis://x", client=fake, enabled=True)
    assert _run(client.ping()) is True
    fake.ping.assert_awaited_once()


def test_enabled_client_ping_returns_false_on_error_without_logging(monkeypatch):
    fake = MagicMock()
    fake.ping = AsyncMock(side_effect=ConnectionRefusedError("boom"))
    client = RedisClient(url="redis://x", client=fake, enabled=True)

    # Fail loudly if the client tries to emit a WARN on a failed ping —
    # throttled logging is the health check's job, not the client's.
    warn = MagicMock()
    monkeypatch.setattr(redis_client_mod.logger, "warning", warn)
    assert _run(client.ping()) is False
    warn.assert_not_called()


# ---------- Config validator --------------------------------------------------


def test_storage_section_empty_url_disables_redis():
    s = StorageSection(redis_url="")
    assert s.redis_enabled is False


def test_storage_section_none_url_disables_redis():
    s = StorageSection(redis_url=None)
    assert s.redis_enabled is False


def test_storage_section_disabled_literal_disables_redis():
    s = StorageSection(redis_url="disabled")
    assert s.redis_enabled is False


def test_storage_section_default_keeps_redis_on():
    s = StorageSection()
    assert s.redis_enabled is True
    assert s.redis_url == "redis://localhost:6379/0"


def test_storage_section_explicit_false_wins(tmp_path: Path):
    p = tmp_path / "cfg.yaml"
    p.write_text(
        yaml.safe_dump(
            {"storage": {"redis_url": "redis://x:6379/0", "redis_enabled": False}}
        )
    )
    cfg = load_config(p)
    assert cfg.storage.redis_enabled is False


# ---------- Health registration count -----------------------------------------


def test_health_registration_count_when_disabled():
    """Simulate what ``Application.build`` does for health registration.

    When Redis is disabled we expect *no* redis check to be registered so the
    /health poll can't produce ``redis_ping_failed`` warnings.
    """
    monitor_disabled = HealthMonitor()
    monitor_disabled.register("db", AsyncMock(return_value=HealthResult(HealthStatus.OK)))
    # NOTE: no redis registration when disabled.

    monitor_enabled = HealthMonitor()
    monitor_enabled.register("db", AsyncMock(return_value=HealthResult(HealthStatus.OK)))
    monitor_enabled.register(
        "redis", AsyncMock(return_value=HealthResult(HealthStatus.OK))
    )

    assert len(monitor_disabled.checks) < len(monitor_enabled.checks)
    assert "redis" not in monitor_disabled.checks
    assert "redis" in monitor_enabled.checks


def test_disabled_client_survives_close_without_client():
    client = RedisClient.create("", enabled=False)
    # Must not raise even though the backing client is None.
    _run(client.close())
