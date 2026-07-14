"""Tests for indicator functions."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from trader.indicators import (
    atr,
    ema,
    relative_strength_percentile,
    rolling_max,
    rolling_min,
    sma,
    supertrend,
    true_range,
    vwap,
    zscore,
)


def test_sma_ema_shapes():
    x = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert len(sma(x, 3)) == 5
    assert len(ema(x, 3)) == 5


def test_sma_values():
    x = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    s = sma(x, 3)
    assert s[2] == pytest.approx(2.0)
    assert s[3] == pytest.approx(3.0)


def test_rolling_max_min():
    x = pl.Series([1.0, 3.0, 2.0, 5.0, 4.0])
    assert rolling_max(x, 2)[3] == 5.0
    assert rolling_min(x, 2)[3] == 2.0


def test_true_range_atr():
    high = pl.Series([10.0, 11.0, 12.0, 11.5])
    low = pl.Series([9.0, 10.0, 10.5, 10.0])
    close = pl.Series([9.5, 10.5, 11.0, 10.5])
    tr = true_range(high, low, close)
    assert tr[0] == pytest.approx(1.0)     # first bar: just high - low
    assert tr[1] == pytest.approx(1.5)     # includes gap over prev close
    a = atr(high, low, close, window=2)
    assert not np.isnan(a[3])


def test_vwap_monotonic_when_volume_uniform():
    price = pl.Series([100.0, 101.0, 102.0, 103.0])
    vol = pl.Series([1000, 1000, 1000, 1000])
    v = vwap(price, vol)
    # VWAP moves toward the higher prices
    assert v[3] > v[0]


def test_zscore_center():
    x = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = zscore(x, 5)
    # last value is 5, mean=3, std=sqrt(2.5) ≈ 1.581
    assert z[4] == pytest.approx(1.2649, rel=1e-2)


def test_supertrend_direction_flip():
    high = pl.Series([10.0, 11.0, 12.0, 13.0, 12.5, 11.0, 10.5])
    low = pl.Series([9.5, 10.0, 11.0, 12.0, 11.0, 9.5, 9.0])
    close = pl.Series([10.0, 10.8, 11.9, 12.8, 11.5, 10.0, 9.5])
    _, direction = supertrend(high, low, close, window=3, multiplier=2)
    # Direction should transition at least once given the price drop.
    assert len(set(direction.to_list())) > 1


def test_relative_strength_percentile_ordering():
    stock = pl.Series(np.linspace(0.001, 0.02, 60))   # increasing daily returns
    bench = pl.Series(np.zeros(60))
    p = relative_strength_percentile(stock, bench, window=20)
    # Last observation should have highest percentile among the last window.
    tail = p.tail(20).to_list()
    assert tail[-1] == pytest.approx(100.0)
