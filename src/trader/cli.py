"""Typer-based CLI.

Commands:

* `trader run`         Start the trading system (default action of `run.py`).
* `trader status`      One-shot health check against DB + Redis + brokers.
* `trader backtest`    Run a backtest for the given strategy + date range.
* `trader backfill`    Pull historical OHLC into the Parquet store
                       (``--source dhan`` needs the Dhan Data API subscription;
                       ``--source yfinance`` is free but delayed and lower
                       fidelity).
* `trader universe`    Refresh universe caches.
* `trader ping-brokers`Ping brokers to verify credentials.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
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


# Our internal timeframe strings mapped to yfinance's ``interval`` argument.
# yfinance intraday caps (as of writing): 1m ~7 days, 2m/5m/15m/30m/60m ~60
# days, 1h ~730 days, 1d/1wk/1mo effectively unlimited.
_YF_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "60m",
    "1d": "1d",
}


def _timeframe_delta(tf: str) -> timedelta:
    m = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}
    return timedelta(seconds=m.get(tf, 60))


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
    timeframe: str = typer.Option(
        "5m",
        help="Bar timeframe to load from the Parquet store: 1m | 5m | 15m | "
        "30m | 1h | 1d. Must match what was backfilled AND what the strategy "
        "expects (equity_orb / equity_vwap_mr use intraday; swing_breakout "
        "requires 1d).",
    ),
) -> None:
    """Run a backtest for a single strategy."""
    _init()
    from trader.backtest.runner import BacktestRunner

    runner = BacktestRunner()
    result = asyncio.run(
        runner.run(strategy=strategy, start=start, end=end, timeframe=timeframe)
    )
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
    source: str = typer.Option(
        "dhan",
        help="Where to fetch bars from: 'dhan' (needs Data API subscription) "
        "or 'yfinance' (free Yahoo Finance, ~60d of intraday, delayed).",
    ),
) -> None:
    """Pull historical OHLC into the local Parquet store.

    The backtest engine reads from ``storage.parquet_root``; running this once
    is what turns ``trader backtest`` from a no-op into a real simulation.
    """
    _init()
    from trader.core.domain import Instrument
    from trader.core.enums import AssetClass, Exchange, Segment

    src = source.strip().lower()
    if src not in {"dhan", "yfinance"}:
        raise typer.BadParameter(
            f"--source must be 'dhan' or 'yfinance', got {source!r}"
        )

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

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    console.print(
        f"[bold]Backfilling[/bold] {len(instruments)} symbol(s) "
        f"@ {timeframe} from {start_dt:%Y-%m-%d} to {end_dt:%Y-%m-%d} "
        f"via [cyan]{src}[/cyan] into {cfg.storage.parquet_root}"
    )

    if src == "dhan":
        results = _backfill_dhan(
            instruments, timeframe, start_dt, end_dt, Path(cfg.storage.parquet_root)
        )
    else:
        results = _backfill_yfinance(
            instruments, timeframe, start_dt, end_dt, Path(cfg.storage.parquet_root)
        )

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
            "[yellow]No bars written. Check the per-symbol log lines above "
            "for the actual error (subscription, empty date range, symbol "
            "unknown to source, etc.). Try --timeframe 1d or a shorter "
            "--days window.[/yellow]"
        )


def _backfill_dhan(
    instruments: list,
    timeframe: str,
    start_dt: datetime,
    end_dt: datetime,
    parquet_root: Path,
) -> dict[str, int]:
    from trader.brokers import DhanClient
    from trader.config import load_secrets, resolve_passphrase
    from trader.marketdata.backfill import BackfillJob
    from trader.storage.parquet_store import ParquetStore

    settings = get_settings()
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
            store = ParquetStore(root=parquet_root)
            job = BackfillJob(broker=broker, store=store)
            return await job.run(instruments, timeframe, start_dt, end_dt)
        finally:
            await broker.close()

    return asyncio.run(_go())


def _backfill_yfinance(
    instruments: list,
    timeframe: str,
    start_dt: datetime,
    end_dt: datetime,
    parquet_root: Path,
) -> dict[str, int]:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as e:
        console.print(
            "[red]yfinance is not installed.[/red] Install it with:\n"
            "  [bold]pip install yfinance[/bold]"
        )
        raise typer.Exit(code=4) from e

    from trader.storage.parquet_store import ParquetStore

    yf_interval = _YF_INTERVAL_MAP.get(timeframe)
    if yf_interval is None:
        raise typer.BadParameter(
            f"Unsupported --timeframe {timeframe!r} for yfinance "
            f"(supported: {sorted(_YF_INTERVAL_MAP)})"
        )

    store = ParquetStore(root=parquet_root)
    delta = _timeframe_delta(timeframe)
    out: dict[str, int] = {}

    # yfinance's ``end`` is exclusive; add one day so today's session is
    # included when the caller asks for --days 30 ending "today".
    yf_start = start_dt.strftime("%Y-%m-%d")
    yf_end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    for inst in instruments:
        ticker = f"{inst.symbol}.NS"
        try:
            df = yf.download(
                ticker,
                start=yf_start,
                end=yf_end,
                interval=yf_interval,
                progress=False,
                auto_adjust=False,
                prepost=False,
                threads=False,
                group_by="column",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "yfinance_download_failed", instrument=inst.symbol, error=str(e)
            )
            out[inst.symbol] = 0
            continue

        if df is None or df.empty:
            logger.warning("yfinance_empty", instrument=inst.symbol, ticker=ticker)
            out[inst.symbol] = 0
            continue

        # Newer yfinance versions return a MultiIndex column layout even for a
        # single ticker; flatten to a plain "Open/High/Low/Close/Volume" set.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        needed = ["Open", "High", "Low", "Close", "Volume"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            logger.warning(
                "yfinance_missing_cols",
                instrument=inst.symbol,
                missing=missing,
                got=list(df.columns),
            )
            out[inst.symbol] = 0
            continue

        df = df[needed].dropna(subset=["Open", "High", "Low", "Close"])

        # Normalise index to tz-aware UTC (intraday is already tz-aware in the
        # exchange tz; daily is naive).
        idx = pd.to_datetime(df.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")

        opens = df["Open"].to_numpy()
        highs = df["High"].to_numpy()
        lows = df["Low"].to_numpy()
        closes = df["Close"].to_numpy()
        vols = df["Volume"].to_numpy()
        timestamps = idx.to_pydatetime()

        by_month: dict[date, list[dict]] = {}
        for i, ts in enumerate(timestamps):
            month = date(ts.year, ts.month, 1)
            by_month.setdefault(month, []).append(
                {
                    "instrument_id": inst.security_id,
                    "ts_open": ts,
                    "ts_close": ts + delta,
                    "timeframe": timeframe,
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": int(vols[i]) if pd.notna(vols[i]) else 0,
                    "oi": None,
                }
            )

        total = 0
        for m, rows in by_month.items():
            total += store.write_bars(timeframe, inst.security_id, m, rows)
        out[inst.symbol] = total
        logger.info("yfinance_backfill_ok", instrument=inst.symbol, bars=total)

    return out


if __name__ == "__main__":
    app()
