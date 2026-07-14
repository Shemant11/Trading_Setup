"""Tests for trader.config.paths.

All tests keep the real user's ``~/.trader`` untouched by monkeypatching
``HOME`` / ``USERPROFILE`` to a per-test ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trader.config.paths import expand_path, normalize_sqlite_url


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point ``~`` at a hermetic tmp dir for the duration of the test."""
    home = tmp_path / "home"
    home.mkdir()
    # POSIX honours HOME; Windows honours USERPROFILE (and falls back to
    # HOMEDRIVE + HOMEPATH). Set all of them to keep the test cross-platform.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOMEDRIVE", str(home.drive) if home.drive else "")
    monkeypatch.setenv("HOMEPATH", str(home)[len(home.drive) :] if home.drive else str(home))
    return home


def test_expand_path_expands_tilde(fake_home):
    p = expand_path("~/.trader/trader.db")
    assert isinstance(p, Path)
    assert p.is_absolute()
    assert "~" not in str(p)
    # Should land inside the fake home we set up.
    assert str(p).startswith(str(fake_home.resolve()))
    assert p.name == "trader.db"


def test_expand_path_expands_env_vars(fake_home, monkeypatch):
    monkeypatch.setenv("TRADER_TESTVAR", str(fake_home / "custom"))
    p = expand_path("$TRADER_TESTVAR/db")
    assert p.is_absolute()
    assert p.parent.name == "custom"


def test_expand_path_accepts_path_input(fake_home):
    p = expand_path(Path("~/.trader"))
    assert p.is_absolute()
    assert "~" not in str(p)


def test_normalize_sqlite_url_expands_and_creates_parent(fake_home):
    url = normalize_sqlite_url("sqlite+aiosqlite:///~/.trader/trader.db")
    assert url.startswith("sqlite+aiosqlite:///")
    # No ``~`` left in the URL.
    assert "~" not in url
    # Path portion is absolute with forward slashes.
    _, _, path = url.partition(":///")
    assert "/" in path
    assert "\\" not in path
    resolved = Path(path)
    assert resolved.is_absolute()
    # Parent directory was created; the DB file itself is left for SQLite.
    assert resolved.parent.is_dir()
    assert not resolved.exists()


def test_normalize_sqlite_url_leaves_postgres_alone(fake_home):
    src = "postgresql+asyncpg://user:pw@localhost:5432/trader"
    assert normalize_sqlite_url(src) == src


def test_normalize_sqlite_url_leaves_memory_alone(fake_home):
    src = "sqlite+aiosqlite:///:memory:"
    assert normalize_sqlite_url(src) == src


def test_normalize_sqlite_url_idempotent(fake_home):
    once = normalize_sqlite_url("sqlite+aiosqlite:///~/.trader/trader.db")
    twice = normalize_sqlite_url(once)
    assert once == twice


def test_normalize_sqlite_url_empty_string_passthrough():
    assert normalize_sqlite_url("") == ""
