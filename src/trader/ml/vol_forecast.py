"""Realized-volatility forecaster."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class VolForecaster:
    model: Any
    feature_names: list[str]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(X)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"model": self.model, "feature_names": self.feature_names}, f)

    @classmethod
    def load(cls, path: Path) -> VolForecaster:
        with path.open("rb") as f:
            data = pickle.load(f)
        return cls(model=data["model"], feature_names=data["feature_names"])


def train_vol_model(
    X: np.ndarray, y_realized_next_5d: np.ndarray, feature_names: list[str]
) -> VolForecaster:
    try:
        import lightgbm as lgb
        model = lgb.LGBMRegressor(
            n_estimators=300, num_leaves=31, learning_rate=0.05,
            min_child_samples=10, verbose=-1,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=3)
    model.fit(X, y_realized_next_5d)
    return VolForecaster(model=model, feature_names=feature_names)
