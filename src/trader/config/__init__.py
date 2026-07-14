"""Configuration and secrets management.

Two sources of truth:

* Environment variables (via `Settings`) — process-wide runtime.
* YAML config (via `ConfigLoader`) — strategy parameters, risk thresholds, etc.

Secrets (broker API keys, Telegram token, SMTP password) live in an
Argon2-derived, AES-GCM encrypted file `~/.trader/secrets.enc`. They are
loaded once at process start and held in memory only.
"""

from trader.config.settings import Settings, get_settings, reset_settings
from trader.config.secrets import (
    SecretsStore,
    SecretsError,
    load_secrets,
    write_secrets,
)
from trader.config.loader import AppConfig, ConfigLoader, load_config

__all__ = [
    "Settings",
    "get_settings",
    "reset_settings",
    "SecretsStore",
    "SecretsError",
    "load_secrets",
    "write_secrets",
    "AppConfig",
    "ConfigLoader",
    "load_config",
]
