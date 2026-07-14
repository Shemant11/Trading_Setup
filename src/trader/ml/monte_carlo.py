"""Monte-Carlo bootstrap of trade sequences.

Given a vector of realized trade PnLs, sample with replacement to build
equity paths and return 5th/50th/95th-percentile CAGR + max-DD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class MonteCarloResult:
    n_paths: int
    cagr_p05: float
    cagr_p50: float
    cagr_p95: float
    max_dd_p05: float
    max_dd_p50: float
    max_dd_p95: float


def monte_carlo_bootstrap(
    trade_pnls: Sequence[float],
    starting_nav: float,
    *,
    n_paths: int = 10_000,
    trades_per_year: int = 250,
    seed: int = 42,
) -> MonteCarloResult:
    if not trade_pnls:
        return MonteCarloResult(0, 0, 0, 0, 0, 0, 0)
    rng = np.random.default_rng(seed)
    pnls = np.array(trade_pnls, dtype=float)
    n = len(pnls)
    # Sample paths of length n
    samples = rng.choice(pnls, size=(n_paths, n), replace=True)
    equity = starting_nav + np.cumsum(samples, axis=1)
    end_nav = equity[:, -1]
    years = max(n / trades_per_year, 1e-6)
    cagr = (end_nav / starting_nav) ** (1 / years) - 1

    running_max = np.maximum.accumulate(equity, axis=1)
    dd = (equity - running_max) / running_max
    max_dd = dd.min(axis=1) * 100

    return MonteCarloResult(
        n_paths=n_paths,
        cagr_p05=float(np.percentile(cagr, 5)),
        cagr_p50=float(np.percentile(cagr, 50)),
        cagr_p95=float(np.percentile(cagr, 95)),
        max_dd_p05=float(np.percentile(max_dd, 5)),
        max_dd_p50=float(np.percentile(max_dd, 50)),
        max_dd_p95=float(np.percentile(max_dd, 95)),
    )
