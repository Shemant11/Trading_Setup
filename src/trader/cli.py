"""Typer-based CLI.

Commands:

* `trader run`         Start the trading system (default action of `run.py`).
* `trader status`      One-shot health check against DB + Redis + brokers.
* `trader backtest`    Run a backtest for the given strategy + date range.
* `trader backfill`    Pull historical OHLC from Dhan into the Parquet store.
* `trader universe`    Refresh universe caches.
* `trader ping-brokers`Ping brokers to verify credentials.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trader.config import get_settings, load_config
from trader.observability.logging import bootstrap_logging, get_logger

app = typer.Typer(help="trader — local automated trading system for Indian markets")
console = Console()
logger = get_logger("trader.cli")


# Dhan security_id lookup for the small default universe used by
# `trader backfill`. Values are stable NSE scrip codes as exposed by Dhan.
# Users who want other names should look up the id in Dhan's instrument
# master CSV and pass it via ``--symbol-ids``.
_DEFAULT_SECURITY_IDS: dict[str, str] = {
    "RELIANCE": "2885",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "INFY": "1594",
    "TCS": "11536",
}


def _init() -> None:
    settings = get_settings()
    bootstrap_logging(
        level=settings.log_level,
        json=settings.log_json,
        log_dir=settings.log_dir,
        console=True,
    )


@app.command()
def run(
    dry_run: bool = typer.Option(False, help="Boot and exit without starting engines"),
    config_path: Path = typer.Option(None, help="Override config file path"),
) -> None:
    """Start the trader (paper by default; live only if TRADER_ENV=live)."""
    _init()
    from trader.app import Application

    settings = get_settings()
    cfg_path = config_path or settings.config_path
    logger.info("starting_trader", env=settings.env, config=str(cfg_path))
    asyncio.run(Application.launch(cfg_path, dry_run=dry_run))


@app.command()
def status() -> None:
    """Print a one-shot health summary."""
    _init()
    from trader.app import Application

    settings = get_settings()
    cfg = load_config(settings.config_path)

    async def _go() -> None:
        health = await Application.status_only(cfg)
        table = Table(title="trader status")
        table.add_column("component")
        table.add_column("status")
        table.add_column("detail")
        for name, res in health.items():
            table.add_row(name, res.status.value, res.detail)
        console.print(table)

    asyncio.run(_go())


@app.command()
def ping_brokers() -> None:
    """Verify broker credentials by making a light call."""
    _init()
    from trader.app import Application

    settings = get_settings()

    async def _go() -> None:
        ok = await Application.ping_brokers(settings)
        for broker, healthy in ok.items():
            colour = "green" if healthy else "red"
            console.print(f"[bold]{broker}[/bold]: [{colour}]{healthy}[/{colour}]")

    asyncio.run(_go())


@app.command()
def backtest(
    strategy: str = typer.Argument(..., help="Strategy key, e.g. equity_orb"),
    start: str = typer.Argument(..., help="YYYY-MM-DD"),
    end: str = typer.Argument(..., help="YYYY-MM-DD"),
) -> None:
    """Run a backtest for a single strategy."""
    _init()
    from trader.backtest.runner import BacktestRunner

    runner = BacktestRunner()
    result = asyncio.run(runner.run(strategy=strategy, start=start, end=end))
    console.print(result.summary())


@app.command()
def backfill(
    symbols: str = typer.Option(
        "RELIANCE,HDFCBANK,ICICIBANK,INFY,TCS",
        help="Comma-separated NSE symbols (must be in the built-in map) OR "
        "leave blank and pass --symbol-ids.",
    ),
    symbol_ids: str = typer.Option(
        "",
        help="Comma-separated Dhan security_ids to backfill directly "
        "(bypasses the symbol map). Format: 'SYMBOL:ID,SYMBOL:ID,...'.",
    ),
    timeframe: str = typer.Option("5m", help="1m | 5m | 15m | 30m | 1h | 1d"),
    days: int = typer.Option(30, help="How many trailing calendar days to pull"),
) -> None:
    """Pull historical OHLC from Dhan into the local Parquet store.

    The backtest engine reads from ``storage.parquet_root``; running this once
    is what turns ``trader backtest`` from a no-op into a real simulation.
    """
    _init()
    from trader.brokers import DhanClient
    from trader.config import load_secrets, resolve_passphrase
    from trader.core.domain import Instrument
    from trader.core.enums import AssetClass, Exchange, Segment
    from trader.marketdata.backfill import BackfillJob
    from trader.storage.parquet_store import ParquetStore

    settings = get_settings()
    cfg = load_config(settings.config_path)

    resolved: dict[str, str] = {}
    if symbol_ids:
        for pair in (p.strip() for p in symbol_ids.split(",") if p.strip()):
            if ":" not in pair:
                raise typer.BadParameter(
                    f"--symbol-ids entry '{pair}' must be 'SYMBOL:ID'"
                )
            sym, sid = pair.split(":", 1)
            resolved[sym.strip().upper()] = sid.strip()
    else:
        for sym in (s.strip().upper() for s in symbols.split(",") if s.strip()):
            if sym not in _DEFAULT_SECURITY_IDS:
                raise typer.BadParameter(
                    f"Symbol '{sym}' not in the built-in map "
                    f"({sorted(_DEFAULT_SECURITY_IDS)}). "
                    f"Use --symbol-ids SYMBOL:ID to override."
                )
            resolved[sym] = _DEFAULT_SECURITY_IDS[sym]

    if not resolved:
        raise typer.BadParameter("No symbols to backfill.")

    instruments = [
        Instrument(
            security_id=sid,
            symbol=sym,
            exchange=Exchange.NSE,
            segment=Segment.EQUITY,
            asset_class=AssetClass.EQUITY,
            lot_size=1,
        )
        for sym, sid in resolved.items()
    ]

    passphrase = resolve_passphrase(settings.secrets_passphrase, settings.secrets_file)
    secrets = load_secrets(settings.secrets_file, passphrase) if passphrase else None
    if not secrets or not secrets.get("dhan_client_id") or not secrets.get(
        "dhan_access_token"
    ):
        console.print(
            "[red]Dhan credentials not found in secrets store. "
            "Re-run the installer to set dhan_client_id / dhan_access_token.[/red]"
        )
        raise typer.Exit(code=2)

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    console.print(
        f"[bold]Backfilling[/bold] {len(instruments)} symbol(s) "
        f"@ {timeframe} from {start_dt:%Y-%m-%d} to {end_dt:%Y-%m-%d} "
        f"into {cfg.storage.parquet_root}"
    )

    async def _go() -> dict[str, int]:
        broker = DhanClient(
            client_id=secrets.require("dhan_client_id"),
            access_token=secrets.require("dhan_access_token"),
        )
        try:
            await broker.connect()
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Dhan connect failed:[/red] {e}")
            raise typer.Exit(code=3) from e
        try:
            store = ParquetStore(root=Path(cfg.storage.parquet_root))
            job = BackfillJob(broker=broker, store=store)
            return await job.run(instruments, timeframe, start_dt, end_dt)
        finally:
            await broker.close()

    results = asyncio.run(_go())

    table = Table(title="backfill results")
    table.add_column("symbol")
    table.add_column("security_id")
    table.add_column("bars written", justify="right")
    total = 0
    for inst in instruments:
        n = results.get(inst.symbol, 0)
        total += n
        colour = "green" if n > 0 else "red"
        table.add_row(inst.symbol, inst.security_id, f"[{colour}]{n}[/{colour}]")
    table.add_row("[bold]total[/bold]", "", f"[bold]{total}[/bold]")
    console.print(table)

    if total == 0:
        console.print(
            "[yellow]No bars written. Common causes: Dhan intraday history "
            "cap (usually ~90 days), non-trading date range, or symbol/id "
            "mismatch. Try --timeframe 1d or a shorter --days window.[/yellow]"
        )


if __name__ == "__main__":
    app()
