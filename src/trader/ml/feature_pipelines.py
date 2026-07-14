"""Deterministic feature builders shared by training and live inference.

Same code MUST produce features in both training and live to avoid
train-serve skew. Every function takes plain arrays / DataFrames and returns
a matrix + feature-name list.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from trader.indicators.rolling import atr


@dataclass(frozen=True)
class FeatureBundle:
    X: np.ndarray
    names: list[str]


def build_regime_features(daily_bars: pl.DataFrame, vix: pl.Series | None = None) -> FeatureBundle:
    """Features for regime classifier: gap %, ATR pct, RS, VIX Δ, etc.

    `daily_bars` must have columns: ts, open, high, low, close, volume.
    """
    df = daily_bars.sort("ts")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    prev_close = close.shift(1)

    gap = ((open_ - prev_close) / prev_close).fill_null(0.0)
    ret_1d = ((close - prev_close) / prev_close).fill_null(0.0)
    atr14 = atr(high, low, close, 14).fill_null(0.0)
    atr_pct = (atr14 / close).fill_null(0.0)
    range_pct = ((high - low) / close).fill_null(0.0)

    features = np.column_stack([
        gap.to_numpy(),
        ret_1d.to_numpy(),
        atr_pct.to_numpy(),
        range_pct.to_numpy(),
    ])
    names = ["gap", "ret_1d", "atr_pct", "range_pct"]
    if vix is not None:
        v = vix.fill_null(strategy="forward")
        v_change = (v - v.shift(5)).fill_null(0.0)
        features = np.column_stack([features, v.to_numpy(), v_change.to_numpy()])
        names += ["vix", "vix_5d_change"]
    return FeatureBundle(X=features, names=names)


def build_vol_features(daily_bars: pl.DataFrame) -> FeatureBundle:
    """Features for realized-vol forecast."""
    df = daily_bars.sort("ts")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    prev_close = close.shift(1)
    ret = ((close - prev_close) / prev_close).fill_null(0.0)
    # rolling realized vol at multiple horizons
    rv5 = (ret.rolling_std(5, ddof=1) or ret).fill_null(0.0)
    rv20 = (ret.rolling_std(20, ddof=1) or ret).fill_null(0.0)
    parkinson = ((np.log(high) - np.log(low)) ** 2 * (1.0 / (4.0 * np.log(2)))) ** 0.5
    atr14 = atr(high, low, close, 14).fill_null(0.0)

    X = np.column_stack([
        rv5.to_numpy(),
        rv20.to_numpy(),
        parkinson.to_numpy() if isinstance(parkinson, np.ndarray) else pl.Series(parkinson).to_numpy(),
        (atr14 / close).fill_null(0.0).to_numpy(),
        ret.to_numpy(),
    ])
    return FeatureBundle(X=X, names=["rv5", "rv20", "parkinson", "atr_pct", "ret_1d"])
