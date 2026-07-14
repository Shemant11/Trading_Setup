"""Encrypted local secrets store.

File format (bytes on disk):

    magic(6="TRDR\x01\x00") | salt(16) | nonce(12) | ciphertext | tag(16)

Key derivation: Argon2id(passphrase, salt) -> 32-byte key.
Cipher: AES-256-GCM.

Rationale: we cannot use OS keychains uniformly across Windows/macOS/Linux
without extra deps, and we want a single portable secrets blob users can
back up. Argon2id + AES-GCM is a modern, defensible default and lives
entirely in `cryptography` + `argon2-cffi`.

Secrets are only ever held in a `SecretsStore` in-memory dict; nothing is
logged, and the passphrase itself is never persisted.
"""

from __future__ import annotations

import json
import os
import secrets as py_secrets
from pathlib import Path
from typing import Any, Optional

from argon2.low_level import Type as Argon2Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"TRDR\x01\x00"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32
ARGON2_TIME = 3
ARGON2_MEM = 64 * 1024   # 64 MB
ARGON2_PARALLELISM = 2


class SecretsError(RuntimeError):
    """Raised on any secrets read/write failure."""


class SecretsStore:
    """In-memory, dict-like access to decrypted secrets.

    Do not log this object. Access via `get()` returning None on absence.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self._data:
            raise SecretsError(f"Secret missing: {key}")
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def as_dict(self) -> dict[str, Any]:
        # Returns a copy; the internal dict is not exposed.
        return dict(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:  # pragma: no cover - never log values
        return f"SecretsStore(keys={list(self._data.keys())!r})"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise SecretsError("Empty passphrase not allowed")
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME,
        memory_cost=ARGON2_MEM,
        parallelism=ARGON2_PARALLELISM,
        hash_len=KEY_LEN,
        type=Argon2Type.ID,
    )


def write_secrets(path: Path, passphrase: str, data: dict[str, Any]) -> None:
    """Encrypt `data` (as JSON) to `path`. Overwrites atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = py_secrets.token_bytes(SALT_LEN)
    nonce = py_secrets.token_bytes(NONCE_LEN)
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    plaintext = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=MAGIC)
    blob = MAGIC + salt + nonce + ciphertext
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    try:
        # POSIX: restrictive perms; ignored on Windows.
        os.chmod(tmp, 0o600)
    except OSError:  # pragma: no cover
        pass
    os.replace(tmp, path)


def load_secrets(path: Path, passphrase: str) -> SecretsStore:
    """Decrypt `path` using `passphrase`. Returns empty store if file absent."""
    if not path.exists():
        return SecretsStore()
    blob = path.read_bytes()
    if len(blob) < len(MAGIC) + SALT_LEN + NONCE_LEN + 16 or blob[: len(MAGIC)] != MAGIC:
        raise SecretsError(f"Invalid secrets file: {path}")
    salt = blob[len(MAGIC) : len(MAGIC) + SALT_LEN]
    nonce = blob[len(MAGIC) + SALT_LEN : len(MAGIC) + SALT_LEN + NONCE_LEN]
    ciphertext = blob[len(MAGIC) + SALT_LEN + NONCE_LEN :]
    try:
        key = _derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=MAGIC)
    except Exception as e:  # pragma: no cover - narrow to cryptography errors
        raise SecretsError("Decryption failed (bad passphrase or corrupt file)") from e
    try:
        data = json.loads(plaintext.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise SecretsError("Corrupt secrets payload") from e
    if not isinstance(data, dict):
        raise SecretsError("Corrupt secrets payload (not an object)")
    return SecretsStore(data)


def secret_keys_schema() -> dict[str, str]:
    """Documented set of known secret keys, for the installer wizard."""
    return {
        "dhan_client_id": "Dhan client id",
        "dhan_access_token": "Dhan access token (permanent OAuth-issued)",
        "groww_api_key": "Groww API key (optional)",
        "groww_api_secret": "Groww API secret (optional)",
        "telegram_bot_token": "Telegram bot token (optional)",
        "telegram_chat_ids": "Comma-separated Telegram chat ids (optional)",
        "smtp_username": "SMTP username for email alerts (optional)",
        "smtp_password": "SMTP password / app password (optional)",
    }


def resolve_passphrase(env_passphrase: str, path: Path, prompt: Optional[callable] = None) -> str:
    """Return a passphrase from env or (interactive) prompt.

    If `path` does not exist, empty passphrase is allowed (fresh install).
    """
    if env_passphrase:
        return env_passphrase
    if not path.exists():
        return ""
    if prompt is None:
        import getpass
        return getpass.getpass("trader secrets passphrase: ")
    return prompt("trader secrets passphrase: ")
