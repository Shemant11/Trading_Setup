"""Process health watchdog.

Tracks:
* Broker latency p95 → halt if > threshold for 60s.
* WS disconnect duration → force flat if > 10s during market hours.
* Clock drift vs NTP → halt if > 500 ms.

The watchdog exposes a "should_halt" verdict used by the RiskEngine's Layer 4.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


@dataclass
class WatchdogState:
    broker_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    last_ws_disconnect_ts: Optional[float] = None
    ws_reconnect_ts: Optional[float] = None
    clock_drift_ms: float = 0.0

    def record_latency(self, ms: float) -> None:
        self.broker_latency_ms.append(ms)

    def record_ws_disconnect(self) -> None:
        self.last_ws_disconnect_ts = time.monotonic()
        self.ws_reconnect_ts = None

    def record_ws_reconnect(self) -> None:
        self.ws_reconnect_ts = time.monotonic()

    def ws_gap_seconds(self) -> float:
        if self.last_ws_disconnect_ts is None:
            return 0.0
        end = self.ws_reconnect_ts or time.monotonic()
        return max(0.0, end - self.last_ws_disconnect_ts)


def watchdog_check(
    state: WatchdogState,
    *,
    latency_p95_halt_ms: float = 1000.0,
    ws_gap_halt_seconds: float = 10.0,
    clock_drift_halt_ms: float = 500.0,
) -> Optional[str]:
    """Return a halt reason string, or None if healthy."""
    if abs(state.clock_drift_ms) > clock_drift_halt_ms:
        return f"clock drift {state.clock_drift_ms:.0f} ms"
    if state.ws_gap_seconds() > ws_gap_halt_seconds:
        return f"WS disconnect {state.ws_gap_seconds():.1f} s"
    lat = list(state.broker_latency_ms)
    if len(lat) >= 20:
        lat_sorted = sorted(lat)
        p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))]
        if p95 > latency_p95_halt_ms:
            return f"broker p95 latency {p95:.0f} ms"
    return None
