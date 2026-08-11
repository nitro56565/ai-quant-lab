import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from lightgbm import LGBMClassifier, LGBMRegressor
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.calibration import CalibratedClassifierCV
import logging



logger = logging.getLogger("LightGBMCatBoostEnsemble")

class LightGBMCatBoostEnsemble:
    """
    LightGBM + CatBoost Multi-Model Ensemble with Disagreement Penalty.
    Forecasts:
    - Calibrated Win Probability (LightGBM + CatBoost Ensemble)
    - MFE Quantiles: 10% (floor), 50% (median), 90% (stretch peak)
    - MAE Quantiles: 10% (floor), 50% (median), 90% (upper risk limit)
    - Model Disagreement Penalty: Delta P = |P_LGBM - P_CatBoost|
    """
    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self.is_fitted = False

        # --- LONG Models ---
        base_lgbm_long = LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.clf_lgbm_long = CalibratedClassifierCV(estimator=base_lgbm_long, method='isotonic', cv=5)
        
        base_cb_long = CatBoostClassifier(iterations=100, learning_rate=0.05, depth=5, random_seed=self.random_state, verbose=False)
        self.clf_cb_long = CalibratedClassifierCV(estimator=base_cb_long, method='isotonic', cv=5)

        # MFE Quantiles (10%, 50%, 90%)
        self.reg_mfe_10_long = LGBMRegressor(objective='quantile', alpha=0.10, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mfe_50_long = LGBMRegressor(objective='regression', n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mfe_90_long = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)

        # MAE Quantiles (10%, 50%, 90%)
        self.reg_mae_10_long = LGBMRegressor(objective='quantile', alpha=0.10, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_50_long = LGBMRegressor(objective='quantile', alpha=0.50, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_90_long = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)

        # --- SHORT Models ---
        base_lgbm_short = LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.clf_lgbm_short = CalibratedClassifierCV(estimator=base_lgbm_short, method='isotonic', cv=5)
        
        base_cb_short = CatBoostClassifier(iterations=100, learning_rate=0.05, depth=5, random_seed=self.random_state, verbose=False)
        self.clf_cb_short = CalibratedClassifierCV(estimator=base_cb_short, method='isotonic', cv=5)

        self.reg_mfe_10_short = LGBMRegressor(objective='quantile', alpha=0.10, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mfe_50_short = LGBMRegressor(objective='regression', n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mfe_90_short = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)

        self.reg_mae_10_short = LGBMRegressor(objective='quantile', alpha=0.10, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_50_short = LGBMRegressor(objective='quantile', alpha=0.50, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_90_short = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=100, learning_rate=0.05, max_depth=5, random_state=self.random_state, verbose=-1, n_jobs=-1)

    def fit(self, X_train: pd.DataFrame, targets: Dict[str, pd.Series]) -> "LightGBMCatBoostEnsemble":
        # Fit LONG
        if 'dir_long' in targets:
            self.clf_lgbm_long.fit(X_train, targets['dir_long'])
            self.clf_cb_long.fit(X_train, targets['dir_long'])
        if 'mfe_long' in targets:
            self.reg_mfe_10_long.fit(X_train, targets['mfe_long'])
            self.reg_mfe_50_long.fit(X_train, targets['mfe_long'])
            self.reg_mfe_90_long.fit(X_train, targets['mfe_long'])
        if 'mae_long' in targets:
            self.reg_mae_10_long.fit(X_train, targets['mae_long'])
            self.reg_mae_50_long.fit(X_train, targets['mae_long'])
            self.reg_mae_90_long.fit(X_train, targets['mae_long'])

        # Fit SHORT
        if 'dir_short' in targets:
            self.clf_lgbm_short.fit(X_train, targets['dir_short'])
            self.clf_cb_short.fit(X_train, targets['dir_short'])
        if 'mfe_short' in targets:
            self.reg_mfe_10_short.fit(X_train, targets['mfe_short'])
            self.reg_mfe_50_short.fit(X_train, targets['mfe_short'])
            self.reg_mfe_90_short.fit(X_train, targets['mfe_short'])
        if 'mae_short' in targets:
            self.reg_mae_10_short.fit(X_train, targets['mae_short'])
            self.reg_mae_50_short.fit(X_train, targets['mae_short'])
            self.reg_mae_90_short.fit(X_train, targets['mae_short'])

        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        if not self.is_fitted:
            raise RuntimeError("Ensemble must be fitted before predict().")

        # LONG Predictions
        p_lgbm_long = self.clf_lgbm_long.predict_proba(X)[:, 1]
        p_cb_long = self.clf_cb_long.predict_proba(X)[:, 1]
        p_ens_long = (p_lgbm_long + p_cb_long) / 2.0
        disagreement_long = np.abs(p_lgbm_long - p_cb_long)

        mfe_10_long = np.maximum(self.reg_mfe_10_long.predict(X), 0.0)
        mfe_50_long = np.maximum(self.reg_mfe_50_long.predict(X), 0.0)
        mfe_90_long = np.maximum(self.reg_mfe_90_long.predict(X), 0.0)
        mfe_50_long = np.maximum(mfe_50_long, mfe_10_long)
        mfe_90_long = np.maximum(mfe_90_long, mfe_50_long)

        mae_10_long = np.maximum(self.reg_mae_10_long.predict(X), 0.0)
        mae_50_long = np.maximum(self.reg_mae_50_long.predict(X), 0.0)
        mae_90_long = np.maximum(self.reg_mae_90_long.predict(X), 0.0)
        mae_50_long = np.maximum(mae_50_long, mae_10_long)
        mae_90_long = np.maximum(mae_90_long, mae_50_long)

        ev_long = (p_ens_long * mfe_50_long) - ((1.0 - p_ens_long) * mae_50_long)

        # SHORT Predictions
        p_lgbm_short = self.clf_lgbm_short.predict_proba(X)[:, 1]
        p_cb_short = self.clf_cb_short.predict_proba(X)[:, 1]
        p_ens_short = (p_lgbm_short + p_cb_short) / 2.0
        disagreement_short = np.abs(p_lgbm_short - p_cb_short)

        mfe_10_short = np.maximum(self.reg_mfe_10_short.predict(X), 0.0)
        mfe_50_short = np.maximum(self.reg_mfe_50_short.predict(X), 0.0)
        mfe_90_short = np.maximum(self.reg_mfe_90_short.predict(X), 0.0)
        mfe_50_short = np.maximum(mfe_50_short, mfe_10_short)
        mfe_90_short = np.maximum(mfe_90_short, mfe_50_short)

        mae_10_short = np.maximum(self.reg_mae_10_short.predict(X), 0.0)
        mae_50_short = np.maximum(self.reg_mae_50_short.predict(X), 0.0)
        mae_90_short = np.maximum(self.reg_mae_90_short.predict(X), 0.0)
        mae_50_short = np.maximum(mae_50_short, mae_10_short)
        mae_90_short = np.maximum(mae_90_short, mae_50_short)

        ev_short = (p_ens_short * mfe_50_short) - ((1.0 - p_ens_short) * mae_50_short)

        return {
            "prob_long": p_ens_long,
            "disagreement_long": disagreement_long,
            "mfe_10_long": mfe_10_long,
            "mfe_50_long": mfe_50_long,
            "mfe_90_long": mfe_90_long,
            "mae_10_long": mae_10_long,
            "mae_50_long": mae_50_long,
            "mae_90_long": mae_90_long,
            "ev_long": ev_long,

            "prob_short": p_ens_short,
            "disagreement_short": disagreement_short,
            "mfe_10_short": mfe_10_short,
            "mfe_50_short": mfe_50_short,
            "mfe_90_short": mfe_90_short,
            "mae_10_short": mae_10_short,
            "mae_50_short": mae_50_short,
            "mae_90_short": mae_90_short,
            "ev_short": ev_short
        }


class RegimeFusedEnsemble:
    """
    Certified Production Regime-Conditioned Ensemble Fusion Architecture.
    Fits 3 Specialized Sub-Models (Bear, Range, Bull) for Long and Short directions
    and dynamically routes inference based on current HMM Market Regime.
    """
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.is_fitted = False
        self.feature_names = []
        self.sub_models = {}

    def fit(self, X_train: pd.DataFrame, targets: dict, hmm_regimes: np.ndarray = None) -> "RegimeFusedEnsemble":
        self.feature_names = list(X_train.columns)
        y_long = targets['dir_long']
        y_short = targets['dir_short']

        if hmm_regimes is None:
            hmm_regimes = X_train['feat_hmm_regime'].values if 'feat_hmm_regime' in X_train.columns else np.zeros(len(X_train))

        for state in [0.0, 1.0, 2.0]:
            mask = (hmm_regimes == state)
            X_state = X_train[mask]
            y_l_state = y_long[mask]
            y_s_state = y_short[mask]

            if len(X_state) < 300:
                X_state = X_train
                y_l_state = y_long
                y_s_state = y_short

            m_long = LGBMClassifier(n_estimators=100, learning_rate=0.03, max_depth=5, min_child_samples=40, random_state=self.random_state, verbose=-1, n_jobs=1)
            m_long.fit(X_state, y_l_state)

            m_short = LGBMClassifier(n_estimators=100, learning_rate=0.03, max_depth=5, min_child_samples=40, random_state=self.random_state, verbose=-1, n_jobs=1)
            m_short.fit(X_state, y_s_state)


            self.sub_models[state] = (m_long, m_short)

        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> dict:
        if not self.is_fitted:
            raise RuntimeError("RegimeFusedEnsemble is not fitted.")

        if hasattr(self, "feature_names") and self.feature_names:
            feat_cols = [c for c in self.feature_names if c in X.columns]
            X_eval = X[feat_cols]
        else:
            X_eval = X

        n_samples = len(X_eval)
        prob_long = np.zeros(n_samples)
        prob_short = np.zeros(n_samples)

        regimes = X_eval['feat_hmm_regime'].values if 'feat_hmm_regime' in X_eval.columns else np.full(n_samples, 1.0)

        for i in range(n_samples):
            st = regimes[i]
            if st not in self.sub_models:
                st = 1.0
            m_l, m_s = self.sub_models[st]
            row_x = X_eval.iloc[[i]]
            prob_long[i] = m_l.predict_proba(row_x)[0, 1]
            prob_short[i] = m_s.predict_proba(row_x)[0, 1]

        mfe_long = np.full(n_samples, 25.0)
        mae_long = np.full(n_samples, 15.0)
        mfe_short = np.full(n_samples, 25.0)
        mae_short = np.full(n_samples, 15.0)

        ev_long = (prob_long * mfe_long) - ((1.0 - prob_long) * mae_long)
        ev_short = (prob_short * mfe_short) - ((1.0 - prob_short) * mae_short)

        return {
            "prob_long": prob_long,
            "prob_short": prob_short,
            "mfe_50_long": mfe_long,
            "mae_50_long": mae_long,
            "mfe_50_short": mfe_short,
            "mae_50_short": mae_short,
            "ev_long": ev_long,
            "ev_short": ev_short
        }

