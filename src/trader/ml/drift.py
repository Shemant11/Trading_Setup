"""Feature drift monitoring — PSI (Population Stability Index).

PSI < 0.1  : no drift.
PSI < 0.25 : slight drift.
PSI ≥ 0.25 : material drift → alert.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index between two distributions."""
    if expected.size == 0 or actual.size == 0:
        return 0.0
    # Bucket by quantiles of expected
    q = np.linspace(0, 1, buckets + 1)
    edges = np.quantile(expected, q)
    edges[0] = -np.inf
    edges[-1] = np.inf
    e_hist, _ = np.histogram(expected, bins=edges)
    a_hist, _ = np.histogram(actual, bins=edges)
    e_pct = np.clip(e_hist / e_hist.sum(), 1e-9, None)
    a_pct = np.clip(a_hist / max(a_hist.sum(), 1), 1e-9, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


@dataclass
class DriftMonitor:
    baseline: dict[str, np.ndarray]

    def check(self, new_batch: dict[str, np.ndarray], threshold: float = 0.25) -> dict[str, float]:
        report = {}
        for k, ref in self.baseline.items():
            cur = new_batch.get(k)
            if cur is None:
                continue
            report[k] = psi(ref, cur)
        return report
