"""Structured logging via structlog.

Output:

* Console: pretty (dev) or JSON (paper/live).
* File: JSON always, rotated daily (`logs/trader.log`).

Every log line automatically carries:

* `ts` — ISO8601 UTC.
* `level`
* `logger`
* Any keys bound via `bind_context(...)` (persistent) or passed inline.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import structlog


_context: ContextVar[dict[str, Any]] = ContextVar("trader_log_context", default={})
_bootstrapped = False


def _ctx_processor(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    ctx = _context.get()
    if ctx:
        # Bound context takes precedence unless the caller passed a key inline.
        for k, v in ctx.items():
            event.setdefault(k, v)
    return event


def bootstrap_logging(
    *,
    level: str = "INFO",
    json: bool = True,
    log_dir: Path | None = None,
    console: bool = True,
) -> None:
    """Idempotent global logging setup."""
    global _bootstrapped
    if _bootstrapped:
        return

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _ctx_processor,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_dir / "trader.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
            utc=True,
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        err_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_dir / "trader.err.log"),
            when="midnight",
            backupCount=60,
            encoding="utf-8",
            utc=True,
        )
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(formatter)
        root.addHandler(err_handler)

    # Tone down noisy libraries.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "websockets.client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _bootstrapped = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or "trader")


def bind_context(**kwargs: Any) -> None:
    """Merge kwargs into the ambient log context."""
    current = dict(_context.get())
    current.update(kwargs)
    _context.set(current)


def clear_context() -> None:
    _context.set({})
