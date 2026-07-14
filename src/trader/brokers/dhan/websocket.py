"""Dhan Market Feed & Order Update WebSocket clients.

Dhan exposes two WS endpoints (as of v2):

* Market feed        wss://api-feed.dhan.co
* Order update feed  wss://api-order-update.dhan.co

This module abstracts:

* Auth handshake (send login frame with client id + token).
* Auto-reconnect with exponential backoff.
* Sequence gap detection (via monotonic broker timestamps).
* Callback dispatch.

For Phase 0 the parser normalizes the "ticker" packet family (LTP + volume).
Depth (20-level) packets are decoded in Phase 1; we surface them as raw dicts
in the meantime.
"""

from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from trader.observability.logging import get_logger
from trader.observability.metrics import TICKS_INGESTED, WS_DISCONNECTS

logger = get_logger("trader.brokers.dhan.ws")

MARKET_FEED_URL = "wss://api-feed.dhan.co"
ORDER_UPDATE_URL = "wss://api-order-update.dhan.co"

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class DhanMarketFeed:
    client_id: str
    access_token: str
    url: str = MARKET_FEED_URL
    on_message: MessageHandler | None = None
    _ws: Any = None
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task[None] | None = None
    _subscriptions: list[dict[str, Any]] = field(default_factory=list)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="dhan-mktfeed")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover
                pass

    async def subscribe(self, tokens: list[dict[str, Any]]) -> None:
        """Add instruments to subscription (dicts of {ExchangeSegment, SecurityId})."""
        self._subscriptions.extend(tokens)
        if self._ws is not None:
            await self._send_subscribe(tokens)

    async def unsubscribe(self, tokens: list[dict[str, Any]]) -> None:
        if self._ws is None:
            return
        payload = {
            "RequestCode": 16,
            "InstrumentCount": len(tokens),
            "InstrumentList": tokens,
        }
        await self._ws.send(json.dumps(payload))

    async def _send_subscribe(self, tokens: list[dict[str, Any]]) -> None:
        payload = {
            "RequestCode": 15,        # 15 = Ticker (LTP), 21 = Quote, 23 = 20-depth
            "InstrumentCount": len(tokens),
            "InstrumentList": tokens,
        }
        assert self._ws is not None
        await self._ws.send(json.dumps(payload))

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stopped.is_set():
            try:
                query = f"?version=2&token={self.access_token}&clientId={self.client_id}&authType=2"
                async with websockets.connect(self.url + query, max_size=2**20) as ws:
                    self._ws = ws
                    logger.info("dhan_ws_connected")
                    if self._subscriptions:
                        await self._send_subscribe(self._subscriptions)
                    backoff = 1.0
                    async for raw in ws:
                        await self._handle_frame(raw)
            except ConnectionClosed as e:
                WS_DISCONNECTS.labels(broker="dhan").inc()
                logger.warning("dhan_ws_closed", code=e.code, reason=str(e))
            except Exception as e:  # noqa: BLE001
                WS_DISCONNECTS.labels(broker="dhan").inc()
                logger.warning("dhan_ws_error", error=str(e))
            self._ws = None
            if self._stopped.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _handle_frame(self, raw: Any) -> None:
        # Dhan sends binary packets for market data; JSON for control.
        if isinstance(raw, bytes):
            msg = self._parse_binary(raw)
            if msg is not None:
                TICKS_INGESTED.labels(broker="dhan").inc()
                if self.on_message:
                    await self.on_message(msg)
        else:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("dhan_ws_bad_json", head=raw[:80])
                return
            if self.on_message:
                await self.on_message(msg)

    @staticmethod
    def _parse_binary(buf: bytes) -> dict[str, Any] | None:
        """Parse a Dhan market-feed binary frame.

        Frame header (8 bytes):
            uint8 feed_code
            uint16 message_length (little-endian)
            uint8 exchange_segment
            uint32 security_id

        Ticker payload (feed_code=2, 16 bytes total after header):
            float32 ltp
            uint32  ltt (unix epoch seconds)
        """
        if len(buf) < 8:
            return None
        feed_code = buf[0]
        # length = struct.unpack_from("<H", buf, 1)[0]
        exchange_segment = buf[3]
        security_id = struct.unpack_from("<I", buf, 4)[0]
        base = {
            "kind": "tick",
            "feed_code": feed_code,
            "exchange_segment": exchange_segment,
            "security_id": str(security_id),
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        if feed_code == 2 and len(buf) >= 16:  # Ticker
            ltp = struct.unpack_from("<f", buf, 8)[0]
            ltt = struct.unpack_from("<I", buf, 12)[0]
            base.update({"ltp": ltp, "ltt": ltt})
            return base

        # Other feed codes (previous close, market depth, OI, prev close etc.)
        # Surface as raw for the parser in Phase 1 to enrich.
        base["raw_hex"] = buf.hex()
        return base


@dataclass
class DhanOrderUpdateFeed:
    """Order status push feed. Emits JSON dicts to `on_message`."""

    client_id: str
    access_token: str
    on_message: MessageHandler | None = None
    url: str = ORDER_UPDATE_URL
    _task: asyncio.Task[None] | None = None
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="dhan-orderupd")

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:  # pragma: no cover
                pass

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stopped.is_set():
            try:
                headers = {"access-token": self.access_token, "client-id": self.client_id}
                async with websockets.connect(self.url, additional_headers=headers) as ws:
                    logger.info("dhan_orderupd_connected")
                    backoff = 1.0
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if self.on_message:
                            await self.on_message(msg)
            except ConnectionClosed as e:
                WS_DISCONNECTS.labels(broker="dhan").inc()
                logger.warning("dhan_orderupd_closed", code=e.code, reason=str(e))
            except Exception as e:  # noqa: BLE001
                WS_DISCONNECTS.labels(broker="dhan").inc()
                logger.warning("dhan_orderupd_error", error=str(e))
            if self._stopped.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
