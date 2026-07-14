"""Relative-strength utilities."""

from __future__ import annotations

import numpy as np
import polars as pl


def relative_strength_percentile(
    stock_returns: pl.Series,
    benchmark_returns: pl.Series,
    window: int = 60,
) -> pl.Series:
    """Cross-sectional-ish RS: excess-return over benchmark, rolling percentile.

    Percentile is in [0, 100]. Requires `benchmark_returns` aligned to
    `stock_returns` by index.
    """
    excess = stock_returns - benchmark_returns
    return _rolling_percentile(excess, window)


def _rolling_percentile(x: pl.Series, window: int) -> pl.Series:
    values = x.to_numpy()
    n = len(values)
    out = np.full(n, np.nan)
    for i in range(window - 1, n):
        win = values[i - window + 1 : i + 1]
        finite = win[~np.isnan(win)]
        if finite.size == 0:
            continue
        rank = float((finite <= values[i]).sum())
        out[i] = 100.0 * rank / finite.size
    return pl.Series(out)
