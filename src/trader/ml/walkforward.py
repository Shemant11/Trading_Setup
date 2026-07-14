"""Walk-forward validation.

Splits `X, y` into rolling 12m-train / 3m-test windows (configurable) and
returns per-fold OOS metrics. Never fits on data whose timestamp is later
than the test period start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

import numpy as np


@dataclass
class WalkForwardFold:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    metric: float


@dataclass
class WalkForwardResult:
    folds: list[WalkForwardFold] = field(default_factory=list)
    def mean(self) -> float:
        return float(np.mean([f.metric for f in self.folds])) if self.folds else 0.0
    def std(self) -> float:
        return float(np.std([f.metric for f in self.folds])) if self.folds else 0.0
    def min(self) -> float:
        return float(np.min([f.metric for f in self.folds])) if self.folds else 0.0


def walk_forward(
    timestamps: np.ndarray,
    X: np.ndarray,
    y: np.ndarray,
    *,
    train_months: int = 12,
    test_months: int = 3,
    step_months: int = 1,
    fit_predict: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray] | None = None,
    scorer: Callable[[np.ndarray, np.ndarray], float] | None = None,
) -> WalkForwardResult:
    """Iterate rolling windows and score.

    `fit_predict(X_train, y_train, X_test) -> y_pred_test`.
    `scorer(y_true, y_pred) -> float`.
    """
    if fit_predict is None or scorer is None:
        raise ValueError("fit_predict and scorer are required")
    if len(timestamps) == 0:
        return WalkForwardResult()

    result = WalkForwardResult()
    start = timestamps[0]
    end = timestamps[-1]
    cur = start
    while True:
        train_start = cur
        train_end = _add_months(train_start, train_months)
        test_start = train_end
        test_end = _add_months(test_start, test_months)
        if test_end > end:
            break
        idx_train = (timestamps >= train_start) & (timestamps < train_end)
        idx_test = (timestamps >= test_start) & (timestamps < test_end)
        if idx_train.sum() < 30 or idx_test.sum() < 5:
            cur = _add_months(cur, step_months)
            continue
        y_pred = fit_predict(X[idx_train], y[idx_train], X[idx_test])
        m = scorer(y[idx_test], y_pred)
        result.folds.append(
            WalkForwardFold(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                metric=m,
            )
        )
        cur = _add_months(cur, step_months)
    return result


def _add_months(dt: datetime, months: int) -> datetime:
    # Approximate — good enough for splitting; use exact date math when needed.
    return dt + timedelta(days=30 * months)
