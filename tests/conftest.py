"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    """Every test gets its own temp TRADER_HOME to avoid polluting the user's ~/.trader."""
    monkeypatch.setenv("TRADER_HOME", str(tmp_path / "trader"))
    monkeypatch.setenv("TRADER_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TRADER_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/trader/test.db")
    monkeypatch.setenv("TRADER_REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("TRADER_CONFIG", str(tmp_path / "trader" / "config.yaml"))
    monkeypatch.setenv("TRADER_ENV", "dev")
    from trader.config.settings import reset_settings
    reset_settings()
    yield
    reset_settings()
