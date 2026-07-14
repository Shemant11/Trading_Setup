"""In-process event types published on the internal bus.

The Event union is discriminated by `kind` so consumers can pattern-match
without runtime introspection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from trader.core.domain import Fill, Order, Signal, Tick


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ts: datetime


class TickEvent(_EventBase):
    kind: Literal["tick"] = "tick"
    tick: Tick


class SignalEvent(_EventBase):
    kind: Literal["signal"] = "signal"
    signal: Signal


class RiskDecisionEvent(_EventBase):
    kind: Literal["risk_decision"] = "risk_decision"
    signal_id: str
    approved: bool
    reason: str
    adjusted_qty: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderEvent(_EventBase):
    kind: Literal["order"] = "order"
    order: Order
    transition: str      # e.g. "NEW->PENDING", "OPEN->FILLED"


class FillEvent(_EventBase):
    kind: Literal["fill"] = "fill"
    fill: Fill


class KillSwitchEvent(_EventBase):
    kind: Literal["kill_switch"] = "kill_switch"
    activated: bool
    reason: str
    source: str          # "manual", "risk", "telegram", "watchdog"


Event = Annotated[
    Union[TickEvent, SignalEvent, RiskDecisionEvent, OrderEvent, FillEvent, KillSwitchEvent],
    Field(discriminator="kind"),
]
