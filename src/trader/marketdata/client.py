"""MarketDataClient — subscribes to broker WS and fans out to consumers.

Responsibilities:

* Multi-callback subscribe (features, strategies, journal).
* Cross-source validation stub (Dhan/Groww divergence check, Phase 2).
* Backpressure: bounded async queues; slow consumers get dropped ticks logged.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

from trader.brokers.base import Broker
from trader.core.domain import Instrument, Tick
from trader.observability.logging import get_logger
from trader.observability.metrics import TICKS_INGESTED

logger = get_logger("trader.marketdata.client")


TickConsumer = Callable[[Tick], Awaitable[None]]


@dataclass
class MarketDataClient:
    primary: Broker
    consumers: list[TickConsumer] = field(default_factory=list)
    queue_size: int = 10_000
    _queue: asyncio.Queue[Tick] = field(init=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _dropped: int = 0

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=self.queue_size)

    def add_consumer(self, consumer: TickConsumer) -> None:
        self.consumers.append(consumer)

    async def start(self, instruments: list[Instrument]) -> None:
        self._task = asyncio.create_task(self._consume_loop(), name="md-consume")
        await self.primary.subscribe_ticks(instruments, self._enqueue)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover
                pass

    async def _enqueue(self, tick: Tick) -> None:
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning("marketdata_queue_full_dropping", dropped=self._dropped)

    async def _consume_loop(self) -> None:
        while True:
            tick = await self._queue.get()
            TICKS_INGESTED.labels(broker=self.primary.capabilities.name).inc()
            for cb in list(self.consumers):
                try:
                    await cb(tick)
                except Exception as e:  # noqa: BLE001 - never let one bad consumer kill the loop
                    logger.warning("consumer_error", error=str(e))
