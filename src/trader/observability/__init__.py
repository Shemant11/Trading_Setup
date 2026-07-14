"""Structured logging + metrics.

`bootstrap_logging()` MUST be called once at process startup before any other
trader module logs, otherwise you'll get default stdlib formatting.
"""

from trader.observability.logging import (
    bind_context,
    bootstrap_logging,
    clear_context,
    get_logger,
)
from trader.observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    metrics_registry,
    render_metrics,
)
from trader.observability.health import HealthCheck, HealthMonitor, HealthResult, HealthStatus

__all__ = [
    "bind_context",
    "bootstrap_logging",
    "clear_context",
    "get_logger",
    "Counter",
    "Gauge",
    "Histogram",
    "metrics_registry",
    "render_metrics",
    "HealthCheck",
    "HealthMonitor",
    "HealthResult",
    "HealthStatus",
]
