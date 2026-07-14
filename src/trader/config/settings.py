"""Environment-driven settings.

Kept intentionally minimal — anything user-tunable belongs in `config.yaml`,
not here. This is just for process runtime, paths, and infra endpoints.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _expand(p: str | Path) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(str(p)))).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
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
        return _expand(v)

    @field_validator("db_url", mode="before")
    @classmethod
    def _expand_db_url(cls, v: str) -> str:
        # Only expand file-based URLs
        if v and "sqlite" in v and "~" in v:
            prefix, path = v.split(":///", 1)
            return f"{prefix}:///{_expand(path)}"
        return v

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide Settings singleton."""
    s = Settings()
    s.ensure_dirs()
    return s


def reset_settings() -> None:
    """Only for tests."""
    get_settings.cache_clear()
