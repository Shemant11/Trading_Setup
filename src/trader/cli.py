"""Typer-based CLI.

Commands:

* `trader run`         Start the trading system (default action of `run.py`).
* `trader status`      One-shot health check against DB + Redis + brokers.
* `trader backtest`    Run a backtest for the given strategy + date range.
* `trader universe`    Refresh universe caches.
* `trader ping-brokers`Ping brokers to verify credentials.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trader.config import get_settings, load_config
from trader.observability.logging import bootstrap_logging, get_logger

app = typer.Typer(help="trader — local automated trading system for Indian markets")
console = Console()
logger = get_logger("trader.cli")


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


if __name__ == "__main__":
    app()
