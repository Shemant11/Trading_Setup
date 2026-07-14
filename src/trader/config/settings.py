"""Environment-driven settings.

Kept intentionally minimal — anything user-tunable belongs in `config.yaml`,
not here. This is just for process runtime, paths, and infra endpoints.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trader.config.paths import expand_path, normalize_sqlite_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # Run field validators on defaults too so ``~`` in the built-in
        # defaults gets expanded even when the user hasn't set the env var.
        validate_default=True,
    )

    env: Literal["dev", "paper", "live"] = "dev"
    home: Path = Field(default=Path("~/.trader"))
    log_level: str = "INFO"
    log_json: bool = True
    log_dir: Path = Field(default=Path("logs"))

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    db_url: str = "sqlite+aiosqlite:///~/.trader/trader.db"
    redis_url: str = "redis://localhost:6379/0"
    config_path: Path = Field(default=Path("~/.trader/config.yaml"))

    secrets_passphrase: str = ""
    halt: bool = False

    @field_validator("home", "log_dir", "config_path", mode="before")
    @classmethod
    def _expand_paths(cls, v: str | Path) -> Path:
        return expand_path(v)

    @field_validator("db_url", mode="before")
    @classmethod
    def _expand_db_url(cls, v: str) -> str:
        # No-op for postgres / mysql / etc.; expands ``~`` and normalizes
        # the path (forward slashes, absolute) for sqlite.
        return normalize_sqlite_url(v) if v else v

    @property
    def halt_file(self) -> Path:
        return self.home / "halt.lock"

    @property
    def secrets_file(self) -> Path:
        return self.home / "secrets.enc"

    @property
    def is_live(self) -> bool:
        return self.env == "live"

    @property
    def is_paper(self) -> bool:
        return self.env == "paper"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Secrets file lives under ``home`` today; keep the parent explicit
        # so a future move (e.g. secrets_file overridden via env) still works.
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide Settings singleton."""
    s = Settings()
    s.ensure_dirs()
    return s


def reset_settings() -> None:
    """Only for tests."""
    get_settings.cache_clear()
