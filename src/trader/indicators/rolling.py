"""Rolling-window indicators.

Deterministic, side-effect free. Given a series in bar order they return a
series of the same length where the first `window - 1` values are NaN.
"""

from __future__ import annotations

import numpy as np
import polars as pl


def sma(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    """Simple moving average."""
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    return x.rolling_mean(window)


def ema(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    """Exponential moving average using the classic alpha = 2/(n+1) form."""
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    return x.ewm_mean(span=window, adjust=False)


def rolling_max(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    return x.rolling_max(window)


def rolling_min(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    return x.rolling_min(window)


def rolling_std(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    return x.rolling_std(window, ddof=1)


def true_range(high: pl.Series, low: pl.Series, close: pl.Series) -> pl.Series:
    """Wilder's True Range.

    tr = max(high - low, |high - prev_close|, |low - prev_close|).
    """
    prev = close.shift(1)
    tr = pl.max_horizontal([high - low, (high - prev).abs(), (low - prev).abs()])
    return tr


def atr(high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14) -> pl.Series:
    """Wilder's Average True Range — smoothed via RMA (equivalent to Wilder MA)."""
    tr = true_range(high, low, close)
    # Wilder smoothing: alpha = 1/window.
    return tr.ewm_mean(alpha=1.0 / window, adjust=False)


def vwap(price: pl.Series, volume: pl.Series) -> pl.Series:
    """Cumulative session VWAP.

    Caller must reset per session (pass a per-session slice) — this function
    intentionally does not know about session boundaries.
    """
    pv = price * volume
    return pv.cum_sum() / volume.cum_sum()


def zscore(x: pl.Series | np.ndarray, window: int) -> pl.Series:
    """Rolling z-score with ddof=1."""
    if isinstance(x, np.ndarray):
        x = pl.Series(x)
    m = x.rolling_mean(window)
    s = x.rolling_std(window, ddof=1)
    # Avoid divide-by-zero.
    return (x - m) / s.fill_null(strategy="forward").clip(lower_bound=1e-12)
