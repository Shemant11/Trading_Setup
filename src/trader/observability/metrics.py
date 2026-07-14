"""Prometheus-compatible metrics.

We use a thin wrapper around `prometheus_client` so tests can reset the
registry cleanly and so exposition is controlled by our FastAPI endpoint.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter as _Counter,
    Gauge as _Gauge,
    Histogram as _Histogram,
    generate_latest,
)


metrics_registry: CollectorRegistry = CollectorRegistry()


def Counter(name: str, doc: str, labelnames: list[str] | None = None) -> _Counter:
    return _Counter(name, doc, labelnames or [], registry=metrics_registry)


def Gauge(name: str, doc: str, labelnames: list[str] | None = None) -> _Gauge:
    return _Gauge(name, doc, labelnames or [], registry=metrics_registry)


def Histogram(
    name: str,
    doc: str,
    labelnames: list[str] | None = None,
    buckets: tuple[float, ...] | None = None,
) -> _Histogram:
    kwargs: dict[str, Any] = {"labelnames": labelnames or [], "registry": metrics_registry}
    if buckets is not None:
        kwargs["buckets"] = buckets
    return _Histogram(name, doc, **kwargs)


def render_metrics() -> bytes:
    """Return the OpenMetrics text exposition for `/metrics`."""
    return generate_latest(metrics_registry)


# --- Common metrics used everywhere. Import from here rather than redefining. ---

ORDERS_SENT = Counter("trader_orders_sent_total", "Orders sent to broker", ["broker", "strategy"])
ORDERS_REJECTED = Counter(
    "trader_orders_rejected_total", "Orders rejected", ["broker", "strategy", "reason_class"]
)
FILLS = Counter("trader_fills_total", "Fills received", ["broker", "side"])
PNL_REALIZED = Gauge("trader_pnl_realized_inr", "Realized PnL (INR)", ["strategy"])
PNL_UNREALIZED = Gauge("trader_pnl_unrealized_inr", "Unrealized PnL (INR)", ["strategy"])
OPEN_POSITIONS = Gauge("trader_open_positions", "Open positions count", ["strategy"])
KILL_SWITCH_ACTIVE = Gauge("trader_kill_switch_active", "1 if kill switch active")

BROKER_LATENCY_MS = Histogram(
    "trader_broker_latency_ms",
    "Broker request latency (ms)",
    ["broker", "endpoint"],
    buckets=(5, 10, 25, 50, 100, 200, 400, 800, 1500, 3000, 6000),
)
TICKS_INGESTED = Counter("trader_ticks_ingested_total", "Ticks ingested", ["broker"])
WS_DISCONNECTS = Counter("trader_ws_disconnects_total", "WS disconnects", ["broker"])
