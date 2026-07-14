"""ML module tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from trader.ml.drift import psi, DriftMonitor
from trader.ml.monte_carlo import monte_carlo_bootstrap
from trader.ml.walkforward import walk_forward


def test_psi_identical_zero():
    x = np.random.default_rng(0).normal(size=1000)
    assert psi(x, x) < 0.01


def test_psi_shifted_positive():
    rng = np.random.default_rng(0)
    x = rng.normal(size=1000)
    y = rng.normal(loc=1.0, size=1000)
    assert psi(x, y) > 0.25


def test_drift_monitor():
    rng = np.random.default_rng(1)
    base = {"f1": rng.normal(size=500)}
    m = DriftMonitor(baseline=base)
    same = m.check({"f1": rng.normal(size=500)})
    drifted = m.check({"f1": rng.normal(loc=2.0, size=500)})
    assert same["f1"] < drifted["f1"]


def test_monte_carlo_basic():
    pnls = [100, -50, 80, -40, 60, -30]
    r = monte_carlo_bootstrap(pnls, starting_nav=100_000, n_paths=1000)
    assert r.n_paths == 1000
    assert r.cagr_p05 <= r.cagr_p50 <= r.cagr_p95
    assert r.max_dd_p05 <= r.max_dd_p50 <= r.max_dd_p95


def test_walk_forward_basic():
    rng = np.random.default_rng(0)
    # 3 years of daily observations
    n = 750
    ts = np.array([datetime(2022, 1, 1) + timedelta(days=i) for i in range(n)])
    X = rng.normal(size=(n, 3))
    y = X[:, 0] * 0.5 + rng.normal(size=n) * 0.1

    def _fit(Xt, yt, Xv):
        w = np.linalg.lstsq(Xt, yt, rcond=None)[0]
        return Xv @ w

    def _score(y_true, y_pred):
        return float(-np.mean((y_true - y_pred) ** 2))

    r = walk_forward(ts, X, y, train_months=6, test_months=1, fit_predict=_fit, scorer=_score)
    assert len(r.folds) > 0
