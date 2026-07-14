"""Dhan REST API v2 client (async).

Thin wrapper around ``httpx.AsyncClient``. Adds:

* Auth header injection.
* Per-endpoint timing → Prometheus histogram.
* Rate-limit (429) → RateLimitError, 5xx / network → TransientBrokerError,
  401/403 → AuthError, anything else non-2xx → BrokerError.
* Automatic JSON body/parsing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from trader.brokers.exceptions import (
    AuthError,
    BrokerError,
    RateLimitError,
    TransientBrokerError,
)
from trader.observability.logging import get_logger
from trader.observability.metrics import BROKER_LATENCY_MS

logger = get_logger("trader.brokers.dhan.rest")

DEFAULT_BASE_URL = "https://api.dhan.co/v2"


@dataclass
class DhanRestClient:
    client_id: str
    access_token: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 5.0
    _http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers=self._default_headers(),
                http2=False,
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _default_headers(self) -> dict[str, str]:
        return {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _raw_request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        assert self._http is not None, "DhanRestClient.start() not called"
        return await self._http.request(method, path, json=json, params=params)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        """Full request with retry, metrics, and error classification."""
        await self.start()
        endpoint_label = _endpoint_label(path)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(retries),
                wait=wait_exponential(multiplier=0.2, min=0.2, max=2.0),
                retry=retry_if_exception_type((TransientBrokerError, RateLimitError)),
                reraise=True,
            ):
                with attempt:
                    return await self._do_request(method, path, json, params, endpoint_label)
        except RetryError as e:
            raise TransientBrokerError(f"exhausted retries: {e}") from e
        return None  # pragma: no cover

    async def _do_request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
        params: dict[str, Any] | None,
        endpoint_label: str,
    ) -> Any:
        t0 = time.monotonic()
        try:
            resp = await self._raw_request(method, path, json=json_body, params=params)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            raise TransientBrokerError(f"network error: {e}") from e
        finally:
            latency_ms = (time.monotonic() - t0) * 1000
            BROKER_LATENCY_MS.labels(broker="dhan", endpoint=endpoint_label).observe(latency_ms)

        if 200 <= resp.status_code < 300:
            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text

        # Error handling ------------------------------------------------------
        text = resp.text[:500]
        if resp.status_code == 429:
            raise RateLimitError(f"rate-limited: {text}")
        if resp.status_code in (401, 403):
            raise AuthError(f"{resp.status_code}: {text}")
        if 500 <= resp.status_code < 600:
            raise TransientBrokerError(f"server error {resp.status_code}: {text}")

        # Structural rejection from broker
        raise BrokerError(f"dhan {resp.status_code}: {text}")


def _endpoint_label(path: str) -> str:
    # Reduce cardinality for metrics: strip trailing IDs.
    parts = path.strip("/").split("/")
    cleaned = []
    for p in parts:
        cleaned.append(":id" if _looks_id(p) else p)
    return "/" + "/".join(cleaned)


def _looks_id(s: str) -> bool:
    return s.isdigit() or (len(s) >= 12 and any(c.isdigit() for c in s))
