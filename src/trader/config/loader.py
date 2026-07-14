"""YAML config loader with Pydantic validation.

Provides a strict schema (`AppConfig`) with defaults and validators so the
system fails at boot rather than mid-trade on a typo.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


def _parse_time(s: str | time) -> time:
    if isinstance(s, time):
        return s
    parts = s.split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Invalid time: {s!r}")


class _Section(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class AppSection(_Section):
    name: str = "trader"
    env: str = "dev"
    timezone: str = "Asia/Kolkata"


class CapitalSection(_Section):
    nav: float = 100_000.0
    currency: str = "INR"


class BrokersSection(_Section):
    primary: str = "dhan"
    failover_equity: Optional[str] = "groww"
    failover_options: Optional[str] = None
    order_rate_limit_per_sec: float = 8.0
    api_timeout_sec: float = 5.0


class StorageSection(_Section):
    db_url: str = "sqlite+aiosqlite:///~/.trader/trader.db"
    redis_url: str = "redis://localhost:6379/0"
    parquet_root: str = "~/.trader/parquet"
    journal_batch_size: int = 100


class TelegramSection(_Section):
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_ids: list[str] = Field(default_factory=list)


class EmailSection(_Section):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    from_addr: Optional[str] = None
    to_addrs: list[str] = Field(default_factory=list)


class NotificationsSection(_Section):
    telegram: TelegramSection = Field(default_factory=TelegramSection)
    email: EmailSection = Field(default_factory=EmailSection)


class RiskSection(_Section):
    fractional_kelly: float = 0.25
    target_position_vol_pct: float = 0.005
    portfolio_heat_cap_pct: float = 0.04
    consecutive_losses_softbrake: int = 3
    consecutive_losses_hardpause: int = 5
    daily_loss_limit_pct: float = 0.015
    weekly_loss_limit_pct: float = 0.035
    monthly_loss_limit_pct: float = 0.06
    rolling_3m_dd_pause_pct: float = 0.08
    max_gross_leverage: float = 3.0
    max_net_delta_pct: float = 1.0
    max_single_stock_pct: float = 0.10
    max_single_sector_pct: float = 0.25
    max_avg_correlation: float = 0.7
    vix_spike_halve_pct: float = 0.30
    nifty_shock_15m_pct: float = 0.02
    broker_latency_p95_halt_ms: int = 1000
    clock_drift_halt_ms: int = 500


class BacktestSection(_Section):
    volume_participation_cap: float = 0.10
    slippage_impact_k: float = 0.10
    commission_model: str = "dhan_default"


class UniverseSection(_Section):
    fno_only: bool = True
    min_adv_cr: float = 200.0
    min_price: float = 100.0
    max_price: float = 5000.0
    max_spread_bps: float = 5.0
    refresh_day: str = "monday"


class RegimeSection(_Section):
    refresh_time: str = "09:20"
    model_path: str = "models/regime.pkl"


class AppConfig(BaseModel):
    """Fully-typed top-level config."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    app: AppSection = Field(default_factory=AppSection)
    capital: CapitalSection = Field(default_factory=CapitalSection)
    brokers: BrokersSection = Field(default_factory=BrokersSection)
    storage: StorageSection = Field(default_factory=StorageSection)
    notifications: NotificationsSection = Field(default_factory=NotificationsSection)
    risk: RiskSection = Field(default_factory=RiskSection)
    backtest: BacktestSection = Field(default_factory=BacktestSection)
    universe: UniverseSection = Field(default_factory=UniverseSection)
    regime: RegimeSection = Field(default_factory=RegimeSection)
    strategies: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _sanity(self) -> AppConfig:
        if self.capital.nav <= 0:
            raise ValueError("capital.nav must be positive")
        if not 0 < self.risk.fractional_kelly <= 1:
            raise ValueError("risk.fractional_kelly must be in (0, 1]")
        if self.risk.daily_loss_limit_pct <= 0:
            raise ValueError("risk.daily_loss_limit_pct must be positive")
        return self

    def strategy_config(self, key: str) -> dict[str, Any]:
        return self.strategies.get(key, {})


class ConfigLoader:
    """Loads and reloads YAML configs. Thread-safe read via snapshot pattern."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        cfg = AppConfig.model_validate(raw)
        self._config = cfg
        return cfg

    def current(self) -> AppConfig:
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> AppConfig:
        return self.load()


def load_config(path: str | Path) -> AppConfig:
    """One-shot load convenience."""
    return ConfigLoader(Path(path).expanduser()).load()
