# trader — Institutional-Grade Indian Market Trading System (Local)

Automated multi-strategy trading for **NSE/BSE** on top of **Dhan** and **Groww** retail broker APIs.
Runs entirely on your own PC — zero cloud, zero paid services.

**Not financial advice. This is a research/engineering project. Trade real money at your own risk.**

## What it does

- **Intraday Equity** — Opening Range Breakout with auction confirmation + VWAP mean-reversion, regime-gated.
- **Options** — Iron Condor, debit spreads, expiry-day butterfly on NIFTY / BANKNIFTY / FINNIFTY / SENSEX and top-6 stock options. **No naked shorts.**
- **Swing** — Stage-2 base breakouts, pullbacks, and post-earnings drift on Nifty 500.
- **Risk engine** — Fractional Kelly + vol-normalized sizing, portfolio heat, four layers of loss limits, kill switch, capital preservation mode.
- **Backtest engine** — Same code path as live via dependency injection. Walk-forward + Monte Carlo + OOS validation.

## Quick start

Requires Python **3.12+**. Optional: Docker (for Redis / Postgres in one command).

```bash
git clone <this-repo>
cd trader
python install.py           # interactive: sets up venv, deps, secrets, DB, watchdog
.venv/Scripts/activate      # Windows (or: source .venv/bin/activate on Linux/Mac)
python run.py               # starts the trading system
```

Then open the dashboard at `http://127.0.0.1:8000`.

## Documentation

- [Architecture](docs/architecture.md)
- [Install guide](docs/install.md)
- [Runbooks](docs/runbooks/)
- [Strategy specs](docs/strategies/)

## Layout

```
src/trader/
    core/            # domain models
    config/          # settings + encrypted secrets
    observability/   # structured logging + metrics
    notifications/   # Telegram + email
    storage/         # SQLite/Postgres + Redis + Parquet
    brokers/         # Dhan + Groww adapters
    marketdata/      # WS + historical ingestion
    features/        # VWAP, ATR, RS, greeks, IV rank
    indicators/      # pure functions
    strategies/      # equity_orb, vwap_mr, options_*, swing_breakout
    risk/            # 4-layer risk engine + kill switch
    execution/       # order state machine, SOR, slicing
    portfolio/       # positions + PnL + greeks
    backtest/        # event engine + cost model + fill sim
    ml/              # feature pipelines, meta-labeler, drift
    scheduler/       # APScheduler daily/intraday jobs
    api/             # FastAPI control + dashboard
```

# Every day, in order:
.\venv\Scripts\Activate.ps1                             # 1. venv
python run.py status                                    # 2. health
python run.py ping-brokers                              # 3. broker creds

# Choose ONE:
$env:TRADER_ENV="paper"; python run.py run              # paper session
$env:TRADER_ENV="live"; python run.py run               # live session

# Anytime:
python -m trader.cli kill                               # emergency stop
python -m trader.cli resume                             # release kill switch
python -m trader.cli reconcile                          # broker vs journal
python run.py backtest equity_orb 2024-01-01 2024-12-31 # backtest
python scripts\backup.py                                # nightly snapshot


## License

MIT
