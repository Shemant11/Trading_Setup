"""Regime classifier.

Uses LightGBM if installed at training-time; otherwise falls back to a
scikit-learn GradientBoosting classifier. Serialized to disk via joblib.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import numpy as np


class RegimeLabel(IntEnum):
    TREND_UP = 1
    CHOP = 0
    TREND_DOWN = -1


@dataclass
class RegimeClassifier:
    """Wrapper around whatever tree model we trained."""

    model: Any
    feature_names: list[str]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)

    def predict_regime(self, X: np.ndarray) -> list[RegimeLabel]:
        return [RegimeLabel(int(p)) for p in self.predict(X)]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"model": self.model, "feature_names": self.feature_names}, f)

    @classmethod
    def load(cls, path: Path) -> RegimeClassifier:
        with path.open("rb") as f:
            data = pickle.load(f)
        return cls(model=data["model"], feature_names=data["feature_names"])


def _make_labels(returns: np.ndarray, threshold: float = 0.005) -> np.ndarray:
    """Simple label from next-day returns: > threshold → up, < -threshold → down, else chop."""
    y = np.zeros_like(returns, dtype=int)
    y[returns > threshold] = 1
    y[returns < -threshold] = -1
    return y


def train_regime_model(
    X: np.ndarray, returns_next_day: np.ndarray, feature_names: list[str]
) -> RegimeClassifier:
    """Train a regime classifier from features + next-day returns."""
    y = _make_labels(returns_next_day)
    try:
        import lightgbm as lgb
        model = lgb.LGBMClassifier(
            n_estimators=200, num_leaves=31, learning_rate=0.05, objective="multiclass",
            num_class=3, min_child_samples=10, verbose=-1,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3)
    # Sklearn expects labels in [0, num_class), so shift by 1.
    y_shifted = y + 1
    model.fit(X, y_shifted)
    # Wrap predict to shift back
    original_predict = model.predict

    def _predict(x):
        p = original_predict(x)
        return p - 1

    class _M:
        def __init__(self, m):
            self._m = m
        def predict(self, x):
            return _predict(x)
    return RegimeClassifier(model=_M(model), feature_names=feature_names)
