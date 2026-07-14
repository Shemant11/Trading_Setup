# Swing strategies

## `swing_breakout`

Long-only base-breakout on daily bars.

### Filters

Weekly fundamental screen (Nifty 500):
* ROCE > 15 %.
* D/E < 1 (ex-financials).
* Earnings growth > 10 % YoY.
* Piotroski F ≥ 6.
* No pending SEBI action.

Daily technical:
* Price > 50-DMA > 200-DMA (Stage 2).
* 12-week RS percentile > 75 vs Nifty 500.
* Weekly close > 20-WEMA.
* Base depth ≤ 25 % over ≥ 5 weeks.
* Breakout volume > 1.5 × 20-day avg.

### Entry / sizing / exits

* Buy-stop above pivot; risk_pct_per_trade default 0.5 %.
* Stop = `max(base_low, close − 2 × ATR-daily)`.
* Trail after +5 % with `3 × ATR-daily` or `20-DMA` (tighter).
* Dead-money exit if no +3 % in 15 sessions.
* Quarterly result miss → mandatory human review before continuing.

### Weekly rebalance (Sunday, automated)

* Re-score holdings.
* Bottom-quartile RS exits even in profit.
* Rebalance sector weights toward top-2 leading sectors.
