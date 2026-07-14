#!/usr/bin/env python
"""Nightly backup script.

Creates `~/trader-backups/YYYY-MM-DD.tar.zst` containing:

* `~/.trader/` — config + secrets + SQLite DB.
* `logs/` from the repo root.

Keeps the last 30 by default. Zero cloud dependency.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
from datetime import date, datetime
from pathlib import Path


def _home() -> Path:
    return Path(os.path.expanduser("~/.trader"))


def _backup_dir() -> Path:
    p = Path(os.path.expanduser("~/trader-backups"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _snapshot_sqlite(dst: Path) -> None:
    """Copy SQLite DB using .backup so we don't miss WAL frames."""
    db = _home() / "trader.db"
    if not db.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3 shell has .backup that's WAL-safe
    subprocess.check_call(["sqlite3", str(db), f".backup '{dst}'"])


def _tar_zstd(src_paths: list[Path], out_file: Path) -> None:
    """Create a tar.zst archive by piping tar through zstd."""
    inputs = [str(p) for p in src_paths if p.exists()]
    if not inputs:
        return
    # Fall back to plain tar.gz if zstd is unavailable.
    if _which("zstd"):
        p = subprocess.Popen(
            ["tar", "-cf", "-", *inputs], stdout=subprocess.PIPE
        )
        with open(out_file, "wb") as f:
            subprocess.check_call(
                ["zstd", "-19", "-o", str(out_file)], stdin=p.stdout
            )
        p.wait()
    else:
        gz = out_file.with_suffix(".tar.gz")
        with tarfile.open(gz, "w:gz") as t:
            for p in inputs:
                t.add(p, arcname=Path(p).name)


def _prune(dir_: Path, keep: int) -> None:
    files = sorted(dir_.glob("*.tar.*"))
    for f in files[:-keep] if len(files) > keep else []:
        try:
            f.unlink()
        except OSError:
            pass


def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def main() -> None:
    parser = argparse.ArgumentParser(description="trader nightly backup")
    parser.add_argument("--keep", type=int, default=30)
    args = parser.parse_args()

    today = date.today().isoformat()
    tmp = _backup_dir() / f"trader-{today}.db"
    _snapshot_sqlite(tmp)

    out = _backup_dir() / f"{today}.tar.zst"
    src = [_home(), Path("logs")]
    _tar_zstd(src, out)
    if tmp.exists():
        tmp.unlink()
    _prune(_backup_dir(), args.keep)
    print(f"backup written: {out}")


if __name__ == "__main__":
    main()
