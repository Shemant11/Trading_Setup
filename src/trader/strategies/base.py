"""Strategy ABC.

Strategies live in isolated modules and register themselves via the registry.
They receive bars/ticks and emit `Signal`s. All state must live inside the
strategy — the engine treats them as event handlers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trader.config.loader import AppConfig
from trader.core.domain import Bar, Fill, Signal, Tick
from trader.core.enums import StrategyKind


@dataclass
class StrategyContext:
    """Contextual info made available to a strategy on every event."""

    nav: float
    strategies_cfg: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyOutput:
    signals: list[Signal] = field(default_factory=list)


class Strategy(ABC):
    """Base class. Subclasses must set `kind` and implement handlers.

    Handlers return a list of `Signal`s to submit. The strategy MUST NOT
    submit orders directly; that goes through the execution gateway (which,
    in backtests, is the MarketSimulator).
    """

    kind: StrategyKind

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        cfg = config.strategy_config(self.kind.value)
        self._enabled: bool = bool(cfg.get("enabled", False))
        self._nav: float = config.capital.nav
        self.params: dict[str, Any] = cfg

    # ---- lifecycle -------------------------------------------------------

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        return None

    def enabled(self) -> bool:
        return self._enabled

    # ---- events ----------------------------------------------------------

    @abstractmethod
    def on_bar(self, bar: Bar) -> list[Signal]:
        ...

    def on_tick(self, tick: Tick) -> list[Signal]:  # pragma: no cover - default noop
        return []

    def on_fill(self, fill: Fill) -> None:  # pragma: no cover - default noop
        return None
