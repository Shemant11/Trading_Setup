"""GrowwClient — equity-only failover broker.

The Groww API surface is much smaller (equity + basic F&O). We wire it up as
a failover for cash equity only. Structure mirrors DhanClient but with far
fewer features so it stays under 300 lines.

Note: Groww's REST endpoints have evolved. This adapter targets the
publicly-documented `/v1/orders`, `/v1/portfolio` shapes as of 2025. The
methods that fail with 404 log a warning and raise `BrokerError` so callers
can decide to skip Groww routing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from trader.brokers.base import (
    Broker,
    BrokerCapabilities,
    HistoricalBar,
    MarginInfo,
    OrderAck,
    OrderUpdate,
    PositionSnapshot,
    TickCallback,
)
from trader.brokers.exceptions import (
    AuthError,
    BrokerError,
    OrderRejectedError,
    RateLimitError,
    TransientBrokerError,
)
from trader.core.domain import Instrument, OrderRequest, Tick
from trader.core.enums import OrderSide, OrderStatus, OrderType, ProductType
from trader.observability.logging import get_logger
from trader.observability.metrics import BROKER_LATENCY_MS

logger = get_logger("trader.brokers.groww")

DEFAULT_BASE_URL = "https://api.groww.in/v1"


@dataclass
class GrowwClient(Broker):
    api_key: str
    api_secret: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 5.0
    capabilities: BrokerCapabilities = field(
        default_factory=lambda: BrokerCapabilities(
            name="groww",
            supports_equity=True,
            supports_options=False,
            supports_futures=False,
            supports_bracket_order=False,
            supports_cover_order=False,
            supports_iceberg=False,
            supports_ws_depth=False,
            max_orders_per_sec=5.0,
        )
    )
    _http: httpx.AsyncClient | None = field(default=None, init=False)

    # ---------- lifecycle -------------------------------------------------

    async def connect(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "X-API-KEY": self.api_key,
                    "X-API-SECRET": self.api_secret,
                    "Content-Type": "application/json",
                },
            )
        try:
            await self._req("GET", "/user/margin")
        except AuthError:
            raise
        except BrokerError as e:
            logger.warning("groww_connect_soft_fail", error=str(e))

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def healthy(self) -> bool:
        try:
            await self._req("GET", "/user/margin")
            return True
        except Exception:  # noqa: BLE001
            return False

    # ---------- account ---------------------------------------------------

    async def get_margin(self) -> MarginInfo:
        data = await self._req("GET", "/user/margin")
        return MarginInfo(
            available=float(data.get("available", 0.0)),
            utilized=float(data.get("utilized", 0.0)),
            total=float(data.get("total", 0.0)),
        )

    async def list_positions(self) -> list[PositionSnapshot]:
        data = await self._req("GET", "/portfolio/positions") or []
        out: list[PositionSnapshot] = []
        for row in data:
            try:
                out.append(
                    PositionSnapshot(
                        instrument_id=str(row["symbolIsin"]),
                        symbol=row.get("tradingSymbol", ""),
                        qty=int(row.get("netQuantity", 0)),
                        avg_price=float(row.get("averagePrice", 0.0)),
                        product_type=ProductType.MIS if row.get("product") == "MIS"
                        else ProductType.CNC,
                        realized_pnl=float(row.get("realizedPnl", 0.0)),
                        unrealized_pnl=float(row.get("unrealizedPnl", 0.0)),
                        last_price=_maybe_float(row.get("lastPrice")),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return out

    # ---------- orders ----------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        if not self.capabilities.supports_options and req.instrument_id.endswith(("CE", "PE")):
            raise OrderRejectedError("groww failover does not support options")
        payload = {
            "correlationId": req.client_order_id,
            "symbolIsin": req.instrument_id,
            "transactionType": req.side.value,
            "orderType": req.order_type.value,
            "quantity": req.qty,
            "price": req.limit_price or 0,
            "triggerPrice": req.trigger_price or 0,
            "product": "MIS" if req.product_type == ProductType.MIS else "CNC",
            "validity": req.validity.value,
        }
        try:
            data = await self._req("POST", "/orders/create", json=payload)
        except BrokerError as e:
            raise OrderRejectedError(str(e)) from e
        return OrderAck(
            broker_order_id=str(data.get("orderId", "")),
            client_order_id=req.client_order_id,
            status=OrderStatus.PENDING,
            ts=datetime.now(timezone.utc),
            raw=data,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._req("DELETE", f"/orders/{broker_order_id}")
            return True
        except BrokerError:
            return False

    async def modify_order(
        self,
        broker_order_id: str,
        *,
        qty: Optional[int] = None,
        limit_price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> bool:
        payload: dict[str, Any] = {}
        if qty is not None:
            payload["quantity"] = qty
        if limit_price is not None:
            payload["price"] = limit_price
        if trigger_price is not None:
            payload["triggerPrice"] = trigger_price
        try:
            await self._req("PUT", f"/orders/{broker_order_id}", json=payload)
            return True
        except BrokerError:
            return False

    async def get_order(self, broker_order_id: str) -> OrderUpdate:
        data = await self._req("GET", f"/orders/{broker_order_id}")
        return _parse_order(data)

    async def list_orders(self) -> list[OrderUpdate]:
        data = await self._req("GET", "/orders") or []
        return [_parse_order(row) for row in data]

    # ---------- instruments -----------------------------------------------

    async def get_instrument(self, symbol: str, exchange: str) -> Optional[Instrument]:
        return None

    # ---------- market data (not used — Dhan is authoritative) -----------

    async def historical_ohlc(
        self,
        instrument: Instrument,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalBar]:
        raise BrokerError("Groww historical OHLC not used; Dhan is the market-data broker")

    async def subscribe_ticks(
        self, instruments: list[Instrument], callback: TickCallback
    ) -> None:
        raise BrokerError("Groww tick subscription not used; Dhan is the market-data broker")

    async def unsubscribe_ticks(self, instruments: list[Instrument]) -> None:
        return

    # ---------- HTTP -------------------------------------------------------

    async def _req(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        assert self._http is not None, "GrowwClient.connect() not called"
        t0 = time.monotonic()
        try:
            resp = await self._http.request(method, path, json=json, params=params)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            raise TransientBrokerError(f"network error: {e}") from e
        finally:
            BROKER_LATENCY_MS.labels(broker="groww", endpoint=path.split("/", 3)[-1]).observe(
                (time.monotonic() - t0) * 1000
            )
        if 200 <= resp.status_code < 300:
            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        text = resp.text[:500]
        if resp.status_code == 429:
            raise RateLimitError(text)
        if resp.status_code in (401, 403):
            raise AuthError(text)
        if 500 <= resp.status_code < 600:
            raise TransientBrokerError(f"{resp.status_code}: {text}")
        raise BrokerError(f"groww {resp.status_code}: {text}")


def _parse_order(row: dict[str, Any]) -> OrderUpdate:
    status_map = {
        "OPEN": OrderStatus.OPEN,
        "PENDING": OrderStatus.PENDING,
        "EXECUTED": OrderStatus.FILLED,
        "COMPLETED": OrderStatus.FILLED,
        "CANCELLED": OrderStatus.CANCELLED,
        "REJECTED": OrderStatus.REJECTED,
        "PARTIALLY_EXECUTED": OrderStatus.PARTIALLY_FILLED,
    }
    return OrderUpdate(
        broker_order_id=str(row.get("orderId", "")),
        client_order_id=row.get("correlationId"),
        status=status_map.get(str(row.get("orderStatus", "")).upper(), OrderStatus.PENDING),
        filled_qty=int(row.get("filledQuantity", 0) or 0),
        avg_fill_price=_maybe_float(row.get("averagePrice")),
        reject_reason=row.get("errorMessage"),
        ts=datetime.now(timezone.utc),
        raw=row,
    )


def _maybe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
