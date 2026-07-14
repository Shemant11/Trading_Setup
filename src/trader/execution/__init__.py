"""Execution gateway: order state machine + SOR + slicing."""

from trader.execution.state_machine import OrderStateMachine, OrderTransition
from trader.execution.router import SmartOrderRouter, RoutingPolicy
from trader.execution.gateway import ExecutionGateway

__all__ = [
    "OrderStateMachine",
    "OrderTransition",
    "SmartOrderRouter",
    "RoutingPolicy",
    "ExecutionGateway",
]
