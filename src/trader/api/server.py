"""FastAPI server wrapping the Application for HTTP inspection.

Phase 0 endpoints:

* GET /health          Aggregated health check.
* GET /metrics         Prometheus scrape endpoint.
* GET /                Minimal HTML dashboard (Jinja).
* GET /api/positions   List positions from the journal.
* GET /api/orders/open List open orders.
* POST /api/halt       Toggle the halt file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

from trader.observability.logging import get_logger
from trader.observability.metrics import render_metrics

logger = get_logger("trader.api")


_INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>trader</title>
<style>
 body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 2rem; }
 h1 { margin-bottom: 0; } small { color: #888; }
 .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; margin-top: 1rem; }
 .card { border: 1px solid #ddd; border-radius: 6px; padding: 1rem; }
 .ok { color: #093; } .warn { color: #b60; } .down { color: #b00; }
 code { background: #f2f2f2; padding: 0 4px; border-radius: 3px; }
</style></head><body>
<h1>trader</h1><small>local automated trading system</small>
<div class="grid" id="grid">Loading…</div>
<script>
 async function refresh() {
  const h = await fetch('/health').then(r => r.json());
  const p = await fetch('/api/positions').then(r => r.json());
  const o = await fetch('/api/orders/open').then(r => r.json());
  const grid = document.getElementById('grid');
  const cls = s => ({ok:'ok', degraded:'warn', down:'down'})[s] || '';
  const rows = Object.entries(h.checks).map(([k,v]) =>
    `<div>${k}: <span class="${cls(v.status)}">${v.status}</span> <small>${v.detail}</small></div>`).join('');
  grid.innerHTML = `
    <div class="card"><h3>Health <span class="${cls(h.status)}">${h.status}</span></h3>${rows}</div>
    <div class="card"><h3>Open positions (${p.length})</h3>${p.map(r =>
      `<div>${r.instrument_id} qty=${r.qty} avg=${r.avg_price}</div>`).join('') || '<em>none</em>'}</div>
    <div class="card"><h3>Open orders (${o.length})</h3>${o.map(r =>
      `<div>${r.strategy} ${r.side} ${r.qty} ${r.instrument_id} ${r.status}</div>`).join('') || '<em>none</em>'}</div>
  `;
 }
 refresh();
 setInterval(refresh, 5000);
</script>
</body></html>
"""


class ApiServer:
    """Wraps FastAPI + uvicorn.Server so we can shut it down cleanly."""

    def __init__(self, application: Any) -> None:
        self.app_ = application
        self.fastapi = self._build_app()

    def _build_app(self) -> FastAPI:
        api = FastAPI(title="trader", version="0.1.0", docs_url="/docs", redoc_url=None)

        @api.get("/", response_class=HTMLResponse)
        async def index() -> str:
            return _INDEX_HTML

        @api.get("/health")
        async def health() -> dict[str, Any]:
            results = await self.app_.health.run()
            summary = self.app_.health.summarize(results)
            return {
                "status": summary.value,
                "checks": {name: {"status": r.status.value, "detail": r.detail}
                           for name, r in results.items()},
            }

        @api.get("/metrics")
        async def metrics() -> Response:
            return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")

        @api.get("/api/positions")
        async def positions() -> list[dict]:
            return await self.app_.journal.list_positions()

        @api.get("/api/orders/open")
        async def open_orders() -> list[dict]:
            return await self.app_.journal.list_open_orders()

        @api.post("/api/halt")
        async def toggle_halt() -> dict:
            f = self.app_.settings.halt_file
            if f.exists():
                f.unlink()
                await self.app_.redis.set_flag("trader:halt", False)
                return {"halted": False}
            f.touch()
            await self.app_.redis.set_flag("trader:halt", True)
            return {"halted": True}

        return api

    async def serve_until(self, until: Awaitable[None]) -> None:
        import uvicorn  # local import; uvicorn is a heavy module

        settings = self.app_.settings
        config = uvicorn.Config(
            self.fastapi,
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.lower(),
            log_config=None,
        )
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve(), name="uvicorn")
        try:
            await until
        finally:
            server.should_exit = True
            await server_task
