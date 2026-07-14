"""DhanClient — the `Broker` implementation on top of REST + WS."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

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
from trader.brokers.dhan.mapping import (
    DHAN_ORDER_TYPE,
    DHAN_PRODUCT,
    DHAN_PRODUCT_INV,
    DHAN_SIDE,
    DHAN_VALIDITY,
    decode_status,
    encode_exchange_segment,
    encode_timeframe,
)
from trader.brokers.dhan.rest import DhanRestClient
from trader.brokers.dhan.websocket import DhanMarketFeed, DhanOrderUpdateFeed
from trader.brokers.exceptions import BrokerError, OrderRejectedError
from trader.core.domain import Instrument, OrderRequest, Tick
from trader.core.enums import (
    AssetClass,
    Exchange,
    OrderStatus,
    ProductType,
    Segment,
)
from trader.observability.logging import get_logger

logger = get_logger("trader.brokers.dhan")


@dataclass
class DhanClient(Broker):
    """Dhan v2 broker implementation.

    Construct with the encrypted secrets already loaded — this class should
    never see plaintext credentials from disk. The Application wires it up.
    """

    client_id: str
    access_token: str
    capabilities: BrokerCapabilities = field(
        default_factory=lambda: BrokerCapabilities(
            name="dhan",
            supports_equity=True,
            supports_options=True,
            supports_futures=True,
            supports_bracket_order=False,   # BO deprecated on Dhan
            supports_cover_order=True,
            supports_iceberg=True,
            supports_ws_depth=True,
            max_orders_per_sec=8.0,
        )
    )
    rest: DhanRestClient = field(init=False)
    _feed: Optional[DhanMarketFeed] = field(default=None, init=False)
    _order_feed: Optional[DhanOrderUpdateFeed] = field(default=None, init=False)
    _tick_callbacks: list[TickCallback] = field(default_factory=list, init=False)
    _subs: dict[str, Instrument] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.rest = DhanRestClient(client_id=self.client_id, access_token=self.access_token)

    # ---------- lifecycle -------------------------------------------------

    async def connect(self) -> None:
        await self.rest.start()
        # Smoke test — will raise AuthError on bad credentials.
        try:
            await self.rest.request("GET", "/fundlimit")
        except BrokerError as e:
            logger.error("dhan_connect_failed", error=str(e))
            raise

    async def close(self) -> None:
        if self._feed is not None:
            await self._feed.stop()
            self._feed = None
        if self._order_feed is not None:
            await self._order_feed.stop()
            self._order_feed = None
        await self.rest.close()

    async def healthy(self) -> bool:
        try:
            await self.rest.request("GET", "/fundlimit", retries=1)
            return True
        except Exception:  # noqa: BLE001
            return False

    # ---------- account ---------------------------------------------------

    async def get_margin(self) -> MarginInfo:
        data = await self.rest.request("GET", "/fundlimit")
        # Dhan returns a dict with `availabelBalance`, `utilizedAmount`, etc.
        return MarginInfo(
            available=float(data.get("availabelBalance", 0.0)),
            utilized=float(data.get("utilizedAmount", 0.0)),
            total=float(data.get("availabelBalance", 0.0))
            + float(data.get("utilizedAmount", 0.0)),
        )

    async def list_positions(self) -> list[PositionSnapshot]:
        data = await self.rest.request("GET", "/positions") or []
        out: list[PositionSnapshot] = []
        for row in data:
            try:
                out.append(
                    PositionSnapshot(
                        instrument_id=str(row["securityId"]),
                        symbol=row.get("tradingSymbol", ""),
                        qty=int(row.get("netQty", 0)),
                        avg_price=float(row.get("buyAvg", 0.0) or row.get("costPrice", 0.0)),
                        product_type=DHAN_PRODUCT_INV.get(
                            row.get("productType", ""), ProductType.MIS
                        ),
                        realized_pnl=float(row.get("realizedProfit", 0.0)),
                        unrealized_pnl=float(row.get("unrealizedProfit", 0.0)),
                        last_price=_maybe_float(row.get("lastTradedPrice")),
                    )
                )
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("dhan_position_parse_failed", error=str(e), row=row)
        return out

    # ---------- orders ----------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        exchange_segment = _guess_exchange_segment(req)
        payload: dict[str, Any] = {
            "correlationId": req.client_order_id,
            "transactionType": DHAN_SIDE[req.side],
            "exchangeSegment": exchange_segment,
            "productType": DHAN_PRODUCT[req.product_type],
            "orderType": DHAN_ORDER_TYPE[req.order_type],
            "validity": DHAN_VALIDITY[req.validity],
            "securityId": req.instrument_id,
            "quantity": req.qty,
            "disclosedQuantity": 0,
            "price": req.limit_price or 0,
            "triggerPrice": req.trigger_price or 0,
            "afterMarketOrder": False,
        }
        try:
            data = await self.rest.request("POST", "/orders", json=payload)
        except BrokerError as e:
            raise OrderRejectedError(str(e)) from e
        broker_order_id = str(data.get("orderId") or data.get("orderid") or "")
        status = decode_status(data.get("orderStatus", "PENDING"))
        return OrderAck(
            broker_order_id=broker_order_id,
            client_order_id=req.client_order_id,
            status=status,
            ts=datetime.now(timezone.utc),
            raw=data,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self.rest.request("DELETE", f"/orders/{broker_order_id}")
            return True
        except BrokerError as e:
            logger.warning("dhan_cancel_failed", broker_order_id=broker_order_id, error=str(e))
            return False

    async def modify_order(
        self,
        broker_order_id: str,
        *,
        qty: Optional[int] = None,
        limit_price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> bool:
        payload = {
            "dhanClientId": self.client_id,
            "orderId": broker_order_id,
        }
        if qty is not None:
            payload["quantity"] = qty
        if limit_price is not None:
            payload["price"] = limit_price
        if trigger_price is not None:
            payload["triggerPrice"] = trigger_price
        try:
            await self.rest.request("PUT", f"/orders/{broker_order_id}", json=payload)
            return True
        except BrokerError as e:
            logger.warning("dhan_modify_failed", error=str(e))
            return False

    async def get_order(self, broker_order_id: str) -> OrderUpdate:
        data = await self.rest.request("GET", f"/orders/{broker_order_id}")
        return _parse_order_row(data)

    async def list_orders(self) -> list[OrderUpdate]:
        data = await self.rest.request("GET", "/orders") or []
        return [_parse_order_row(row) for row in data]

    # ---------- instruments -----------------------------------------------

    async def get_instrument(self, symbol: str, exchange: str) -> Optional[Instrument]:
        # Dhan does not offer a search endpoint; instrument master must be
        # bulk-downloaded (a CSV). In Phase 0 we do not populate this; the
        # marketdata module handles master ingestion in Phase 1.
        return None

    # ---------- market data ----------------------------------------------

    async def historical_ohlc(
        self,
        instrument: Instrument,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalBar]:
        interval = encode_timeframe(timeframe)
        payload = {
            "securityId": instrument.security_id,
            "exchangeSegment": encode_exchange_segment(instrument.exchange, instrument.segment),
            "instrument": _instrument_type(instrument),
            "interval": interval,
            "fromDate": start.strftime("%Y-%m-%d"),
            "toDate": end.strftime("%Y-%m-%d"),
        }
        endpoint = "/charts/historical" if interval == "D" else "/charts/intraday"
        data = await self.rest.request("POST", endpoint, json=payload)
        return _parse_historical(data)

    async def subscribe_ticks(
        self, instruments: list[Instrument], callback: TickCallback
    ) -> None:
        if callback not in self._tick_callbacks:
            self._tick_callbacks.append(callback)
        if self._feed is None:
            self._feed = DhanMarketFeed(
                client_id=self.client_id,
                access_token=self.access_token,
                on_message=self._on_ws_msg,
            )
            await self._feed.start()
        tokens: list[dict[str, Any]] = []
        for inst in instruments:
            self._subs[inst.security_id] = inst
            tokens.append(
                {
                    "ExchangeSegment": encode_exchange_segment(inst.exchange, inst.segment),
                    "SecurityId": inst.security_id,
                }
            )
        if tokens:
            await self._feed.subscribe(tokens)

    async def unsubscribe_ticks(self, instruments: list[Instrument]) -> None:
        if self._feed is None:
            return
        tokens = [
            {
                "ExchangeSegment": encode_exchange_segment(i.exchange, i.segment),
                "SecurityId": i.security_id,
            }
            for i in instruments
        ]
        await self._feed.unsubscribe(tokens)
        for i in instruments:
            self._subs.pop(i.security_id, None)

    async def _on_ws_msg(self, msg: dict[str, Any]) -> None:
        if msg.get("kind") != "tick":
            return
        sid = msg.get("security_id")
        if not sid or "ltp" not in msg:
            return
        inst = self._subs.get(sid)
        symbol = inst.symbol if inst else sid
        tick = Tick(
            instrument_id=sid,
            ts_exchange=datetime.fromtimestamp(msg["ltt"], tz=timezone.utc)
            if "ltt" in msg
            else datetime.now(timezone.utc),
            ts_ingest=datetime.now(timezone.utc),
            ltp=float(msg["ltp"]),
        )
        for cb in list(self._tick_callbacks):
            try:
                await cb(tick)
            except Exception as e:  # noqa: BLE001 - do not let one bad cb kill the feed
                logger.warning("tick_callback_error", symbol=symbol, error=str(e))


# ------------------------- helpers -------------------------------------------


def _parse_order_row(row: dict[str, Any]) -> OrderUpdate:
    return OrderUpdate(
        broker_order_id=str(row.get("orderId", "")),
        client_order_id=row.get("correlationId"),
        status=decode_status(row.get("orderStatus", "")),
        filled_qty=int(row.get("filledQty", 0) or 0),
        avg_fill_price=_maybe_float(row.get("averageTradedPrice")),
        reject_reason=row.get("omsErrorDescription") or None,
        ts=datetime.now(timezone.utc),
        raw=row,
    )


def _parse_historical(data: dict[str, Any] | None) -> list[HistoricalBar]:
    if not data:
        return []
    ts = data.get("timestamp") or data.get("start_Time") or []
    o = data.get("open", [])
    h = data.get("high", [])
    l = data.get("low", [])
    c = data.get("close", [])
    v = data.get("volume", [])
    oi = data.get("open_interest") or [None] * len(ts)
    out: list[HistoricalBar] = []
    for i, epoch in enumerate(ts):
        try:
            out.append(
                HistoricalBar(
                    ts=datetime.fromtimestamp(float(epoch), tz=timezone.utc),
                    open=float(o[i]),
                    high=float(h[i]),
                    low=float(l[i]),
                    close=float(c[i]),
                    volume=int(v[i] or 0),
                    oi=int(oi[i]) if oi[i] is not None else None,
                )
            )
        except (IndexError, ValueError, TypeError):
            continue
    return out


def _guess_exchange_segment(req: OrderRequest) -> str:
    if req.exchange is not None:
        return encode_exchange_segment(req.exchange, Segment.EQUITY)
    # Fall back to NSE equity
    return "NSE_EQ"


def _instrument_type(inst: Instrument) -> str:
    if inst.asset_class == AssetClass.OPTION:
        return "OPTIDX" if inst.underlying_symbol in {"NIFTY", "BANKNIFTY", "FINNIFTY"} else "OPTSTK"
    if inst.asset_class == AssetClass.FUTURE:
        return "FUTIDX" if inst.underlying_symbol in {"NIFTY", "BANKNIFTY", "FINNIFTY"} else "FUTSTK"
    if inst.asset_class == AssetClass.INDEX:
        return "INDEX"
    return "EQUITY"


def _maybe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
