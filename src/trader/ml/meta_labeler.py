"""Trade-quality meta-labeler (López de Prado, AFML ch. 3).

Given a *primary* strategy signal + market context features, predict:

    P(trade hits +1R take-profit before -1R stop-loss).

Downstream:
* Filter: skip trade if p < 0.55.
* Sizer: multiply base size by (0.5..1.5) mapped from p.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class MetaLabeler:
    model: Any
    feature_names: list[str]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return P(hit +1R first) in [0, 1]."""
        return self.model.predict_proba(X)[:, 1]

    def should_take(self, X: np.ndarray, threshold: float = 0.55) -> np.ndarray:
        return self.predict_proba(X) >= threshold

    def size_multiplier(self, X: np.ndarray) -> np.ndarray:
        """Map probability → 0.5..1.5 sizer multiplier."""
        p = self.predict_proba(X)
        return 0.5 + p  # 0.5..1.5 as p goes 0..1

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"model": self.model, "feature_names": self.feature_names}, f)

    @classmethod
    def load(cls, path: Path) -> MetaLabeler:
        with path.open("rb") as f:
            data = pickle.load(f)
        return cls(model=data["model"], feature_names=data["feature_names"])


def train_meta_labeler(
    X: np.ndarray, y_hit_1r: np.ndarray, feature_names: list[str]
) -> MetaLabeler:
    """y_hit_1r ∈ {0, 1}: 1 iff the trade reached +1R before -1R."""
    try:
        import xgboost as xgb
        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            eval_metric="logloss", use_label_encoder=False, verbosity=0,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(n_estimators=300, learning_rate=0.05, max_depth=3)
    model.fit(X, y_hit_1r)
    return MetaLabeler(model=model, feature_names=feature_names)
