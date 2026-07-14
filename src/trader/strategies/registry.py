"""Strategy registry.

Strategies register a factory keyed by `StrategyKind`. This lets configs
reference strategies by name (`equity_orb`, `options_iron_condor`, etc.) and
lets the engine/backtester build them dynamically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from trader.config.loader import AppConfig
from trader.core.enums import StrategyKind
from trader.strategies.base import Strategy


StrategyFactory = Callable[[AppConfig], Strategy]

_REGISTRY: dict[StrategyKind, StrategyFactory] = {}


def register_strategy(kind: StrategyKind, factory: StrategyFactory) -> None:
    _REGISTRY[kind] = factory


def build_strategy(name: str, config: AppConfig) -> Strategy:
    try:
        kind = StrategyKind(name)
    except ValueError as e:
        raise KeyError(f"unknown strategy: {name}") from e
    if kind not in _REGISTRY:
        # Force-load submodules to populate registry.
        _autoload_strategies()
    if kind not in _REGISTRY:
        raise KeyError(f"strategy {name} not registered — is the module imported?")
    return _REGISTRY[kind](config)


def _autoload_strategies() -> None:
    # Import known strategy packages so they can register themselves.
    modules = [
        "trader.strategies.equity_orb",
        "trader.strategies.equity_vwap_mr",
        "trader.strategies.options_iron_condor",
        "trader.strategies.options_debit_spread",
        "trader.strategies.options_expiry_butterfly",
        "trader.strategies.swing_breakout",
    ]
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            continue
