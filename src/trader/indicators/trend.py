"""Trend indicators: ADX, Supertrend, Chandelier stop."""

from __future__ import annotations

import numpy as np
import polars as pl

from trader.indicators.rolling import atr, ema


def adx(
    high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14
) -> pl.Series:
    """Wilder's Average Directional Index.

    Uses Wilder smoothing (EMA with alpha=1/window).
    """
    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = pl.Series(np.where((up > down) & (up > 0), up, 0.0))
    minus_dm = pl.Series(np.where((down > up) & (down > 0), down, 0.0))

    tr14 = atr(high, low, close, window)          # smoothed TR
    plus_dm_s = plus_dm.ewm_mean(alpha=1.0 / window, adjust=False)
    minus_dm_s = minus_dm.ewm_mean(alpha=1.0 / window, adjust=False)

    plus_di = 100.0 * plus_dm_s / tr14
    minus_di = 100.0 * minus_dm_s / tr14
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).clip(lower_bound=1e-12)
    return dx.ewm_mean(alpha=1.0 / window, adjust=False)


def chandelier_stop(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    *,
    window: int = 22,
    atr_mult: float = 2.0,
    side: str = "long",
) -> pl.Series:
    """Chandelier stop = highest_high(N) - k*ATR(N) (for longs).

    For shorts: lowest_low(N) + k*ATR(N).
    """
    a = atr(high, low, close, window)
    if side == "long":
        return high.rolling_max(window) - atr_mult * a
    if side == "short":
        return low.rolling_min(window) + atr_mult * a
    raise ValueError(f"Unknown side: {side!r}")


def supertrend(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    *,
    window: int = 10,
    multiplier: float = 3.0,
) -> tuple[pl.Series, pl.Series]:
    """Supertrend line + direction (+1 long, -1 short).

    Standard formulation:
        median = (high + low) / 2
        upper_band = median + m * ATR
        lower_band = median - m * ATR
    Then step through bars, flipping direction on close crossing bands.
    """
    a = atr(high, low, close, window).to_numpy()
    med = ((high + low) / 2.0).to_numpy()
    close_np = close.to_numpy()

    upper = med + multiplier * a
    lower = med - multiplier * a

    n = len(close_np)
    direction = np.zeros(n, dtype=np.int8)
    st = np.zeros(n)
    # Initialize
    direction[0] = 1
    st[0] = lower[0]

    for i in range(1, n):
        # Adjust bands to be non-worsening in the same trend
        if close_np[i - 1] <= upper[i - 1]:
            upper[i] = min(upper[i], upper[i - 1])
        if close_np[i - 1] >= lower[i - 1]:
            lower[i] = max(lower[i], lower[i - 1])

        if direction[i - 1] == 1:
            if close_np[i] < lower[i]:
                direction[i] = -1
                st[i] = upper[i]
            else:
                direction[i] = 1
                st[i] = lower[i]
        else:
            if close_np[i] > upper[i]:
                direction[i] = 1
                st[i] = lower[i]
            else:
                direction[i] = -1
                st[i] = upper[i]

    return pl.Series("supertrend", st), pl.Series("direction", direction)
