"""Filesystem path helpers.

Everything that touches disk (SQLite files, log dirs, parquet root, secrets
file, ...) flows through :func:`expand_path` so ``~`` and ``$VARS`` are
resolved consistently across Windows / macOS / Linux.

SQLite URLs get their own helper (:func:`normalize_sqlite_url`) because
``sqlite3`` treats ``~`` as a literal directory name — SQLAlchemy passes the
URL through unchanged, so ``sqlite+aiosqlite:///~/.trader/trader.db`` fails
with ``unable to open database file`` on any platform where the process
cwd doesn't happen to contain a directory literally called ``~``.

Kept dependency-free on purpose so it can be imported very early during
bootstrap (before pydantic / SQLAlchemy are touched).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

PathLike = Union[str, "os.PathLike[str]", Path]


def expand_path(p: PathLike) -> Path:
    """Return an absolute :class:`Path` with ``~`` and ``$VARS`` expanded.

    Never raises if the path does not exist — parents are the caller's job
    (:meth:`Path.mkdir`) so this helper stays safe to call from validators.
    """
    s = os.path.expandvars(str(p))
    return Path(s).expanduser().resolve()


_SQLITE_PREFIXES = ("sqlite:", "sqlite+")


def _is_sqlite_url(url: str) -> bool:
    if not url:
        return False
    head = url.split(":", 1)[0].lower()
    return head == "sqlite" or head.startswith("sqlite+")


def normalize_sqlite_url(url: str, *, create_parent: bool = True) -> str:
    """Expand ``~`` inside a SQLite SQLAlchemy URL and force forward slashes.

    * Non-sqlite URLs (Postgres, MySQL, ...) are returned unchanged.
    * ``sqlite+aiosqlite:///:memory:`` and similar in-memory forms are
      returned unchanged.
    * On Windows the resolved path is emitted with forward slashes and a
      drive letter, e.g. ``sqlite+aiosqlite:///C:/Users/you/.trader/trader.db``
      which is the canonical form SQLAlchemy expects.
    * When ``create_parent`` is true (default) the parent directory is
      created; SQLite itself will create the DB file on first connect.
    """
    if not _is_sqlite_url(url):
        return url
    if ":///" not in url:
        return url
    prefix, _, raw_path = url.partition(":///")
    stripped = raw_path.strip()
    if not stripped or stripped.startswith(":memory:") or stripped == "":
        return url
    # SQLAlchemy uses ``sqlite:////abs/path`` on POSIX for absolute paths, so
    # a leading extra ``/`` becomes part of raw_path — keep that behavior for
    # already-absolute POSIX paths that don't contain ``~`` / env vars.
    expanded = expand_path(raw_path)
    if create_parent:
        try:
            expanded.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Best-effort: surface the real error later on connect.
            pass
    return f"{prefix}:///{expanded.as_posix()}"


__all__ = ["expand_path", "normalize_sqlite_url"]
