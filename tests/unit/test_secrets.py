"""Tests for the encrypted secrets store."""

from __future__ import annotations

from pathlib import Path

import pytest

from trader.config.secrets import SecretsError, load_secrets, write_secrets


def test_roundtrip(tmp_path: Path):
    path = tmp_path / "s.enc"
    write_secrets(path, "correct horse battery staple", {"dhan_client_id": "1000123",
                                                          "telegram_bot_token": "abc:xyz"})
    store = load_secrets(path, "correct horse battery staple")
    assert store.require("dhan_client_id") == "1000123"
    assert store.get("telegram_bot_token") == "abc:xyz"
    assert "smtp_password" not in store


def test_wrong_passphrase_fails(tmp_path: Path):
    path = tmp_path / "s.enc"
    write_secrets(path, "hunter2", {"a": "b"})
    with pytest.raises(SecretsError):
        load_secrets(path, "wrong")


def test_empty_when_missing(tmp_path: Path):
    store = load_secrets(tmp_path / "missing.enc", "anything")
    assert store.keys() == []


def test_repr_hides_values(tmp_path: Path):
    path = tmp_path / "s.enc"
    write_secrets(path, "pw", {"my_secret": "topsecret"})
    store = load_secrets(path, "pw")
    text = repr(store)
    assert "topsecret" not in text
    assert "my_secret" in text
