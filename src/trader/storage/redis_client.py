"""Thin async Redis wrapper.

Encapsulates connection handling and adds first-class helpers for the two
Redis usage patterns in this project:

* Streams — XADD / XREAD for internal event bus.
* Keys — flags (kill switch, halt) and small caches.

Redis is treated as **optional**. When ``enabled=False`` the public surface is
preserved but every method short-circuits into a safe no-op (``ping`` returns
``True``, ``get_flag`` returns ``False``, ``xadd`` returns an empty id, etc.).
This lets strategies and the kill switch keep publishing to the "bus" without
any conditionals when the operator runs single-process without a Redis daemon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import redis.asyncio as redis

from trader.observability.logging import get_logger

logger = get_logger("trader.storage.redis")


@dataclass
class RedisClient:
    url: str
    client: Optional[redis.Redis] = None
    enabled: bool = True

    @classmethod
    def create(cls, url: str, *, enabled: bool = True) -> RedisClient:
        """Build a client. Pass ``enabled=False`` to get a fully-inert stub
        that keeps the public API but never touches the network.
        """
        if not enabled or not url:
            return cls(url=url or "", client=None, enabled=False)
        client = redis.from_url(url, decode_responses=True)
        return cls(url=url, client=client, enabled=True)

    async def ping(self) -> bool:
        if not self.enabled or self.client is None:
            return True
        try:
            return bool(await self.client.ping())
        except Exception:  # noqa: BLE001
            # Intentionally no logging here — the caller (health check) is
            # responsible for throttled reporting so we don't spam logs on
            # every 5-second poll when the daemon is down.
            return False

    async def close(self) -> None:
        if self.client is None:
            return
        try:
            await self.client.close()
        except Exception:  # noqa: BLE001, S110
            pass

    # ----- Flags -----------------------------------------------------------

    async def set_flag(self, key: str, value: bool) -> None:
        if not self.enabled or self.client is None:
            return
        try:
            await self.client.set(key, "1" if value else "0")
        except Exception:  # noqa: BLE001, S110
            pass

    async def get_flag(self, key: str) -> bool:
        if not self.enabled or self.client is None:
            return False
        try:
            v = await self.client.get(key)
        except Exception:  # noqa: BLE001
            return False
        return v == "1"

    async def set(self, key: str, value: str) -> None:
        if not self.enabled or self.client is None:
            return
        try:
            await self.client.set(key, value)
        except Exception:  # noqa: BLE001, S110
            pass

    async def get(self, key: str) -> Optional[str]:
        if not self.enabled or self.client is None:
            return None
        try:
            return await self.client.get(key)
        except Exception:  # noqa: BLE001
            return None

    # ----- Streams ---------------------------------------------------------

    async def xadd(self, stream: str, data: dict[str, Any], maxlen: int | None = 100_000) -> str:
        if not self.enabled or self.client is None:
            return ""
        kwargs = {"maxlen": maxlen, "approximate": True} if maxlen else {}
        payload = {k: str(v) for k, v in data.items()}
        try:
            return await self.client.xadd(stream, payload, **kwargs)
        except Exception:  # noqa: BLE001
            return ""

    async def xread(
        self,
        stream: str,
        last_id: str = "$",
        block_ms: int = 1000,
        count: int = 100,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if not self.enabled or self.client is None:
            # Nothing to yield — return immediately so consumers can decide
            # whether to fall back to an in-process bus.
            return
        while True:
            resp = await self.client.xread({stream: last_id}, count=count, block=block_ms)
            if not resp:
                continue
            for _stream_name, entries in resp:
                for entry_id, data in entries:
                    last_id = entry_id
                    yield entry_id, data
