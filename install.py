#!/usr/bin/env python
"""One-shot installer for the trader system.

Interactive. Safe to re-run. Does the following:

1.  Verify Python 3.12+.
2.  Create `.venv/` and install dependencies (prefers `uv` if available).
3.  Ensure `~/.trader/` exists with a config file copied from the template.
4.  Prompt for broker + notification secrets and store encrypted in
    `~/.trader/secrets.enc`.
5.  Run `alembic upgrade head` to create the DB schema.
6.  Optionally bring up Redis via Docker if the user opts in.
7.  Print next steps.

Skipping is always allowed at each prompt so users can wire things later.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PY = (3, 12)
ROOT = Path(__file__).resolve().parent
CONFIG_TEMPLATE = ROOT / "config" / "config.example.yaml"
ENV_TEMPLATE = ROOT / ".env.example"
HOME = Path(os.path.expanduser("~/.trader"))


def log(msg: str) -> None:
    print(f"[install] {msg}")


def die(msg: str, code: int = 1) -> None:
    print(f"[install][error] {msg}", file=sys.stderr)
    sys.exit(code)


def check_python() -> None:
    if sys.version_info < MIN_PY:
        die(f"Python >= {MIN_PY[0]}.{MIN_PY[1]} required, got {sys.version_info.major}."
            f"{sys.version_info.minor}")
    log(f"python {sys.version.split()[0]} OK")


def make_venv() -> Path:
    venv = ROOT / ".venv"
    if venv.exists():
        log(".venv already exists, skipping creation")
    else:
        log("creating .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    return venv


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )


def install_deps(venv: Path) -> None:
    py = _venv_python(venv)
    uv = shutil.which("uv")
    log("upgrading pip ...")
    subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel"])
    if uv:
        log("using uv to install (fast)")
        subprocess.check_call([uv, "pip", "install", "--python", str(py), "-e", ".[dev]"])
    else:
        log("installing dependencies via pip (this can take a few minutes) ...")
        subprocess.check_call([str(py), "-m", "pip", "install", "-e", ".[dev]"])


def ensure_home() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    log(f"trader home: {HOME}")
    target_cfg = HOME / "config.yaml"
    if not target_cfg.exists():
        shutil.copy2(CONFIG_TEMPLATE, target_cfg)
        log(f"copied default config -> {target_cfg}")
    else:
        log("config.yaml already present (leaving as-is)")
    env_file = ROOT / ".env"
    if not env_file.exists() and ENV_TEMPLATE.exists():
        shutil.copy2(ENV_TEMPLATE, env_file)
        log(f"copied .env template -> {env_file}")


def prompt(msg: str, default: str = "", *, secret: bool = False) -> str:
    suffix = f" [{default}]" if default and not secret else ""
    prompt_text = f"{msg}{suffix}: "
    val = getpass.getpass(prompt_text) if secret else input(prompt_text)
    val = val.strip()
    return val or default


def configure_secrets(venv: Path) -> None:
    log("configuring secrets (leave blank to skip a field) ...")
    print()
    dhan_client_id = prompt("Dhan client ID")
    dhan_token = prompt("Dhan access token", secret=True)
    groww_key = prompt("Groww API key (optional)")
    groww_secret = prompt("Groww API secret (optional)", secret=True) if groww_key else ""
    tg_token = prompt("Telegram bot token (optional)", secret=True)
    tg_chat = prompt("Telegram chat id(s) comma-separated (optional)") if tg_token else ""
    smtp_user = prompt("SMTP username (optional)")
    smtp_pass = prompt("SMTP password / app password (optional)", secret=True) if smtp_user else ""

    if not any([dhan_client_id, dhan_token, groww_key, tg_token, smtp_user]):
        log("no secrets provided — skipping secrets file creation")
        return

    print()
    passphrase = prompt("passphrase to encrypt secrets", secret=True)
    if not passphrase:
        die("passphrase is required to write encrypted secrets")
    passphrase_confirm = prompt("confirm passphrase", secret=True)
    if passphrase != passphrase_confirm:
        die("passphrases do not match")

    # We shell out into the venv's Python so we don't need to have the
    # installer's env know about cryptography/argon2.
    script = f"""
import json, sys
sys.path.insert(0, "src")
from pathlib import Path
from trader.config.secrets import write_secrets

secrets = {{
    'dhan_client_id': {dhan_client_id!r},
    'dhan_access_token': {dhan_token!r},
    'groww_api_key': {groww_key!r},
    'groww_api_secret': {groww_secret!r},
    'telegram_bot_token': {tg_token!r},
    'telegram_chat_ids': {tg_chat!r},
    'smtp_username': {smtp_user!r},
    'smtp_password': {smtp_pass!r},
}}
secrets = {{k: v for k, v in secrets.items() if v}}
write_secrets(Path.home() / '.trader' / 'secrets.enc', {passphrase!r}, secrets)
print('secrets written', len(secrets))
"""
    subprocess.check_call([str(_venv_python(venv)), "-c", script], cwd=str(ROOT))
    log("secrets encrypted to ~/.trader/secrets.enc")


def run_migrations(venv: Path) -> None:
    py = _venv_python(venv)
    log("running alembic migrations ...")
    # Compose the URL with forward slashes so it works on Windows
    # (``sqlite:///C:/Users/.../trader.db``) as well as POSIX.
    db_file = (HOME / "trader.db").resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{db_file.as_posix()}"
    subprocess.check_call(
        [str(py), "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        env={**os.environ, "TRADER_DB_URL": db_url},
    )
    log("db schema ready")


def maybe_start_redis() -> None:
    ans = prompt("bring up Redis via docker compose now? (y/N)", "n")
    if ans.lower() not in {"y", "yes"}:
        log("skipping docker; make sure a Redis is reachable on redis://localhost:6379/0")
        return
    if not shutil.which("docker"):
        log("docker not found on PATH; skipping")
        return
    try:
        subprocess.check_call(["docker", "compose", "up", "-d", "redis"], cwd=str(ROOT))
        log("Redis running on 127.0.0.1:6379")
    except subprocess.CalledProcessError as e:
        log(f"docker compose failed ({e}); continue manually if needed")


def print_next_steps(venv: Path) -> None:
    py = _venv_python(venv)
    print()
    print("=" * 70)
    print("install complete.")
    print()
    print("next steps:")
    print(f"  1. activate the venv:  {venv / ('Scripts' if os.name == 'nt' else 'bin')}/activate")
    print(f"  2. review config:      {HOME / 'config.yaml'}")
    print(f"  3. run the trader:     {py} run.py")
    print("  4. open dashboard:     http://127.0.0.1:8000")
    print("=" * 70)


def main() -> None:
    check_python()
    venv = make_venv()
    install_deps(venv)
    ensure_home()
    configure_secrets(venv)
    run_migrations(venv)
    maybe_start_redis()
    print_next_steps(venv)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("cancelled by user")
    except subprocess.CalledProcessError as e:
        die(f"subprocess failed: {e}")
