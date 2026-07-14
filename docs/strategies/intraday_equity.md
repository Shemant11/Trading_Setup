# Intraday equity strategies

Two setups gated by a regime classifier:

* **`equity_orb`** — Opening Range Breakout with auction confirmation. Runs in TREND regimes.
* **`equity_vwap_mr`** — VWAP mean reversion. Runs in CHOP regime.

Universe: F&O stocks, 20-day ADV > ₹200 Cr, ₹100–₹5000, spread < 5 bps.

## `equity_orb`

### Entry (long side; short is symmetric)

1. Bar timeframe: 5m.
2. After 09:30 IST and before 14:45 IST.
3. `bar.close > OR_high * (1 + break_threshold_pct)`, default 0.15 %.
4. Bar volume ≥ 2× rolling 20-bar mean volume.
5. `bar.close > session VWAP`.
6. Book imbalance ≥ 0.55 (if depth data available).

### Sizing

`risk_pct_per_trade * NAV` / `(entry − stop)`. Default 0.4 %.

### Stops / targets

* Stop = `min(OR mid, close − 1 * ATR-15m)`.
* Targets = +1R and +2R; trail remainder.
* Time stop 14:45; auto-square 15:15.

### Known failure modes

* Regime classifier wrong ~15 % of days (per plan).
* Flat-VIX weeks: fewer setups, unchanged win rate.

## `equity_vwap_mr`

### Entry

* `abs((close - VWAP) / rolling_sigma) >= 1.5` (fade extremes).
* `no_entry_after 14:30 IST`.
* Max 3 signals per instrument per day.

### Stops / targets

* Stop at 2σ from VWAP.
* Target = VWAP.
* Time stop = 45 minutes.
