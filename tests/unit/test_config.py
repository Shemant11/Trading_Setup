"""Tests for config loader + settings."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from trader.config import AppConfig, get_settings, load_config


def test_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADER_ENV", "paper")
    monkeypatch.setenv("TRADER_LOG_LEVEL", "DEBUG")
    from trader.config.settings import reset_settings
    reset_settings()
    s = get_settings()
    assert s.env == "paper"
    assert s.log_level == "DEBUG"
    assert s.is_paper


def test_config_loader_defaults(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text("app:\n  name: test\n")
    cfg = load_config(p)
    assert isinstance(cfg, AppConfig)
    assert cfg.app.name == "test"
    assert cfg.capital.nav > 0
    assert cfg.risk.fractional_kelly == 0.25


def test_config_validates_kelly(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"risk": {"fractional_kelly": 2.0}}))
    with pytest.raises(ValueError):
        load_config(p)


def test_config_validates_nav(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"capital": {"nav": -1}}))
    with pytest.raises(ValueError):
        load_config(p)


def test_strategy_config(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump({"strategies": {"equity_orb": {"enabled": True, "foo": 42}}}))
    cfg = load_config(p)
    assert cfg.strategy_config("equity_orb")["foo"] == 42
    assert cfg.strategy_config("unknown") == {}
