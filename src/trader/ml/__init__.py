"""Machine-learning models.

Approved (from plan):
* Regime classifier (LightGBM).
* Volatility forecaster (LightGBM).
* Trade-quality meta-labeler (XGBoost).
* Slippage predictor (CatBoost, not implemented yet).

All models trained locally, tracked via MLflow file backend.
"""

from trader.ml.feature_pipelines import build_regime_features, build_vol_features
from trader.ml.regime import RegimeClassifier, RegimeLabel, train_regime_model
from trader.ml.vol_forecast import VolForecaster, train_vol_model
from trader.ml.meta_labeler import MetaLabeler, train_meta_labeler
from trader.ml.drift import DriftMonitor, psi
from trader.ml.walkforward import walk_forward
from trader.ml.monte_carlo import monte_carlo_bootstrap

__all__ = [
    "build_regime_features",
    "build_vol_features",
    "RegimeClassifier",
    "RegimeLabel",
    "train_regime_model",
    "VolForecaster",
    "train_vol_model",
    "MetaLabeler",
    "train_meta_labeler",
    "DriftMonitor",
    "psi",
    "walk_forward",
    "monte_carlo_bootstrap",
]
