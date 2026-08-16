# 🧠 Machine Learning Specification

### Models
* **CatBoost, LightGBM, XGBoost** classifiers.
* **Ensemble:** Soft-voting probability averaging (50/25/25).
* **Regime Filter:** 4-State Gaussian HMM (Trend/Range x High/Low Vol).

### Training Protocol
* **Walk-Forward Procedure:** 8 Folds across the OOS period (2018-2025).
* **Law:** Training data must ALWAYS precede prediction data. Overlapping windows are strictly forbidden.

### Persistence
* Final canonical weights are serialized to `trained_model_artifacts/production_deployment/model_suite.joblib`.
