"""Thin async Redis wrapper.

Encapsulates connection handling and adds first-class helpers for the two
Redis usage patterns in this project:

* Streams — XADD / XREAD for internal event bus.
* Keys — flags (kill switch, halt) and small caches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import redis.asyncio as redis

from trader.observability.logging import get_logger

logger = get_logger("trader.storage.redis")


@dataclass
class RedisClient:
    url: str
    client: redis.Redis

    @classmethod
    def create(cls, url: str) -> RedisClient:
        client = redis.from_url(url, decode_responses=True)
        return cls(url=url, client=client)

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception as e:  # noqa: BLE001
            logger.warning("redis_ping_failed", error=str(e))
            return False

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:  # noqa: BLE001, S110
            pass

    # ----- Flags -----------------------------------------------------------

    async def set_flag(self, key: str, value: bool) -> None:
        await self.client.set(key, "1" if value else "0")

    async def get_flag(self, key: str) -> bool:
        v = await self.client.get(key)
        return v == "1"

    # ----- Streams ---------------------------------------------------------

    async def xadd(self, stream: str, data: dict[str, Any], maxlen: int | None = 100_000) -> str:
        kwargs = {"maxlen": maxlen, "approximate": True} if maxlen else {}
        # Redis needs string values.
        payload = {k: str(v) for k, v in data.items()}
        return await self.client.xadd(stream, payload, **kwargs)

    async def xread(
        self,
        stream: str,
        last_id: str = "$",
        block_ms: int = 1000,
        count: int = 100,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        while True:
            resp = await self.client.xread({stream: last_id}, count=count, block=block_ms)
            if not resp:
                continue
            for _stream_name, entries in resp:
                for entry_id, data in entries:
                    last_id = entry_id
                    yield entry_id, data
