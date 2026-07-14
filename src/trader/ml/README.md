# trader.ml

Local ML: LightGBM / XGBoost trained on the user's PC, tracked in a local
MLflow file backend under `./mlruns/`.

* `feature_pipelines.py` — Deterministic feature builders (single source of truth for train + serve).
* `regime.py` — Trend/chop/down classifier.
* `vol_forecast.py` — Realized-vol forecaster.
* `meta_labeler.py` — López de Prado meta-labeling (filter + sizer).
* `drift.py` — PSI-based drift monitor.
* `walkforward.py` — Purged walk-forward validation harness.
* `monte_carlo.py` — Trade-sequence bootstrap.

Rule: no ML where a rule works. See plan §9.
