"""Smart Order Router.

Rules (from plan):

* Dhan is the default broker.
* Groww failover applies to cash equity only.
* Options NEVER failover to Groww.
* If both brokers are unhealthy → reject.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from trader.brokers.base import Broker
from trader.core.domain import OrderRequest
from trader.core.enums import AssetClass


@dataclass
class RoutingPolicy:
    primary_name: str
    failover_equity: Optional[str] = None


@dataclass
class SmartOrderRouter:
    brokers: dict[str, Broker]
    policy: RoutingPolicy

    async def choose(self, req: OrderRequest, asset_class: AssetClass) -> Optional[Broker]:
        primary = self.brokers.get(self.policy.primary_name)
        # Health check the primary — this is a cheap in-memory boolean fed by
        # the observability layer in Phase 2 (broker latency monitor).
        if primary is not None and await primary.healthy():
            if asset_class == AssetClass.OPTION and not primary.capabilities.supports_options:
                pass
            else:
                return primary
        # Failover branch
        if asset_class != AssetClass.EQUITY:
            return None
        name = self.policy.failover_equity
        if name is None:
            return None
        fb = self.brokers.get(name)
        if fb is None:
            return None
        if await fb.healthy():
            return fb
        return None
