"""Contract tests for DhanClient.

These use `respx` to mock the HTTP layer so we can verify request shapes and
response parsing without hitting the real broker.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from trader.brokers.dhan.client import DhanClient
from trader.core.domain import OrderRequest
from trader.core.enums import (
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    StrategyKind,
    Validity,
)


BASE = "https://api.dhan.co/v2"


@pytest.fixture()
async def dhan():
    b = DhanClient(client_id="CID", access_token="TOK")
    await b.rest.start()
    yield b
    await b.close()


@respx.mock
async def test_healthy_true(dhan: DhanClient):
    respx.get(f"{BASE}/fundlimit").mock(return_value=httpx.Response(200, json={"availabelBalance": "1"}))
    assert await dhan.healthy() is True


@respx.mock
async def test_healthy_false_on_500(dhan: DhanClient):
    respx.get(f"{BASE}/fundlimit").mock(return_value=httpx.Response(500, text="boom"))
    assert await dhan.healthy() is False


@respx.mock
async def test_get_margin_parses_fields(dhan: DhanClient):
    respx.get(f"{BASE}/fundlimit").mock(
        return_value=httpx.Response(200, json={
            "availabelBalance": "12345.67", "utilizedAmount": "500.00"
        })
    )
    m = await dhan.get_margin()
    assert m.available == pytest.approx(12345.67)
    assert m.utilized == pytest.approx(500.0)


@respx.mock
async def test_place_order_shape(dhan: DhanClient):
    route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(200, json={"orderId": "112233", "orderStatus": "PENDING"})
    )
    req = OrderRequest(
        client_order_id="c-1",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="500325",
        side=OrderSide.BUY,
        qty=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
        validity=Validity.DAY,
        exchange=Exchange.NSE,
    )
    ack = await dhan.place_order(req)
    assert ack.broker_order_id == "112233"
    assert ack.status == OrderStatus.PENDING
    assert route.called
    body = route.calls.last.request.content
    assert b'"correlationId":"c-1"' in body
    assert b'"transactionType":"BUY"' in body
    assert b'"productType":"INTRADAY"' in body
    assert b'"exchangeSegment":"NSE_EQ"' in body


@respx.mock
async def test_place_order_rejects_on_broker_error(dhan: DhanClient):
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(400, text='{"errorMessage":"margin insufficient"}')
    )
    req = OrderRequest(
        client_order_id="c-2",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="500325",
        side=OrderSide.BUY,
        qty=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
    )
    from trader.brokers.exceptions import OrderRejectedError
    with pytest.raises(OrderRejectedError):
        await dhan.place_order(req)


@respx.mock
async def test_list_positions_parses(dhan: DhanClient):
    respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(200, json=[{
            "securityId": "500325",
            "tradingSymbol": "RELIANCE",
            "netQty": 100,
            "buyAvg": 2900.5,
            "productType": "INTRADAY",
            "realizedProfit": 0,
            "unrealizedProfit": 250.0,
        }])
    )
    positions = await dhan.list_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "RELIANCE"
    assert positions[0].product_type == ProductType.MIS


@respx.mock
async def test_auth_error_on_401(dhan: DhanClient):
    respx.get(f"{BASE}/fundlimit").mock(return_value=httpx.Response(401, text="unauthorized"))
    from trader.brokers.exceptions import AuthError
    with pytest.raises(AuthError):
        await dhan.rest.request("GET", "/fundlimit")
