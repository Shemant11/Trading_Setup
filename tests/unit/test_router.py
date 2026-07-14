"""Smart Order Router tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from trader.brokers.base import BrokerCapabilities
from trader.core.domain import OrderRequest
from trader.core.enums import (
    AssetClass,
    OrderSide,
    OrderType,
    ProductType,
    StrategyKind,
)
from trader.execution.router import RoutingPolicy, SmartOrderRouter


def _req() -> OrderRequest:
    return OrderRequest(
        client_order_id="c1",
        strategy=StrategyKind.EQUITY_ORB,
        instrument_id="X",
        side=OrderSide.BUY,
        qty=1,
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
    )


def _mock_broker(name: str, healthy: bool, options: bool = True) -> MagicMock:
    m = MagicMock()
    m.capabilities = BrokerCapabilities(
        name=name, supports_options=options, supports_equity=True
    )
    m.healthy = AsyncMock(return_value=healthy)
    return m


async def test_primary_used_when_healthy():
    dhan = _mock_broker("dhan", healthy=True)
    groww = _mock_broker("groww", healthy=True, options=False)
    r = SmartOrderRouter(
        brokers={"dhan": dhan, "groww": groww},
        policy=RoutingPolicy(primary_name="dhan", failover_equity="groww"),
    )
    picked = await r.choose(_req(), AssetClass.EQUITY)
    assert picked.capabilities.name == "dhan"


async def test_failover_when_primary_down_equity():
    dhan = _mock_broker("dhan", healthy=False)
    groww = _mock_broker("groww", healthy=True, options=False)
    r = SmartOrderRouter(
        brokers={"dhan": dhan, "groww": groww},
        policy=RoutingPolicy(primary_name="dhan", failover_equity="groww"),
    )
    picked = await r.choose(_req(), AssetClass.EQUITY)
    assert picked.capabilities.name == "groww"


async def test_no_failover_for_options():
    dhan = _mock_broker("dhan", healthy=False)
    groww = _mock_broker("groww", healthy=True, options=False)
    r = SmartOrderRouter(
        brokers={"dhan": dhan, "groww": groww},
        policy=RoutingPolicy(primary_name="dhan", failover_equity="groww"),
    )
    picked = await r.choose(_req(), AssetClass.OPTION)
    assert picked is None


async def test_both_down_returns_none():
    dhan = _mock_broker("dhan", healthy=False)
    groww = _mock_broker("groww", healthy=False)
    r = SmartOrderRouter(
        brokers={"dhan": dhan, "groww": groww},
        policy=RoutingPolicy(primary_name="dhan", failover_equity="groww"),
    )
    picked = await r.choose(_req(), AssetClass.EQUITY)
    assert picked is None
