import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.calibration import CalibratedClassifierCV
import logging

logger = logging.getLogger("LightGBMModelSuite")

class LightGBMModelSuite:
    """
    Production-grade LightGBM model suite for institutional quantitative forecasting:
    - Calibrated win probability classifier (5-fold cross-validated Isotonic scaling)
    - Peak Favorable Excursion (MFE) regressor
    - Quantile MAE regressors (50th percentile median risk & 90th percentile upper-bound risk)
    Symmetric implementation for both LONG and SHORT directions.
    """
    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.05, max_depth: int = 5, random_state: int = 42) -> None:
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.random_state = random_state
        self.is_fitted = False
        
        # LONG Models
        base_clf_long = LGBMClassifier(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
            verbose=-1,
            n_jobs=-1
        )
        self.clf_long = CalibratedClassifierCV(estimator=base_clf_long, method='isotonic', cv=5)
        self.reg_mfe_long = LGBMRegressor(objective='regression', n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_long_50 = LGBMRegressor(objective='quantile', alpha=0.50, n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_long_90 = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)

        # SHORT Models
        base_clf_short = LGBMClassifier(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
            verbose=-1,
            n_jobs=-1
        )
        self.clf_short = CalibratedClassifierCV(estimator=base_clf_short, method='isotonic', cv=5)
        self.reg_mfe_short = LGBMRegressor(objective='regression', n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_short_50 = LGBMRegressor(objective='quantile', alpha=0.50, n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)
        self.reg_mae_short_90 = LGBMRegressor(objective='quantile', alpha=0.90, n_estimators=self.n_estimators, learning_rate=self.learning_rate, max_depth=self.max_depth, random_state=self.random_state, verbose=-1, n_jobs=-1)

    def fit(self, X_train: pd.DataFrame, targets: Dict[str, pd.Series]) -> "LightGBMModelSuite":
        """
        Fit all LightGBM classifiers and regressors on training set.
        """
        # LONG fits
        if 'dir_long' in targets:
            self.clf_long.fit(X_train, targets['dir_long'])
        if 'mfe_long' in targets:
            self.reg_mfe_long.fit(X_train, targets['mfe_long'])
        if 'mae_long' in targets:
            self.reg_mae_long_50.fit(X_train, targets['mae_long'])
            self.reg_mae_long_90.fit(X_train, targets['mae_long'])

        # SHORT fits
        if 'dir_short' in targets:
            self.clf_short.fit(X_train, targets['dir_short'])
        if 'mfe_short' in targets:
            self.reg_mfe_short.fit(X_train, targets['mfe_short'])
        if 'mae_short' in targets:
            self.reg_mae_short_50.fit(X_train, targets['mae_short'])
            self.reg_mae_short_90.fit(X_train, targets['mae_short'])

        self.is_fitted = True
        logger.info("LightGBMModelSuite successfully fitted for LONG & SHORT models.")
        return self

    def predict(self, X: pd.DataFrame) -> Dict[str, np.ndarray]:
        """
        Predict calibrated probabilities and excursion targets for given dataset.
        Returns dict containing numpy arrays for all predictions.
        """
        if not self.is_fitted:
            raise RuntimeError("LightGBMModelSuite must be fitted before calling predict().")
            
        prob_long = self.clf_long.predict_proba(X)[:, 1]
        mfe_long = np.maximum(self.reg_mfe_long.predict(X), 0.0)
        mae_long_50 = np.maximum(self.reg_mae_long_50.predict(X), 0.0)
        mae_long_90 = np.maximum(self.reg_mae_long_90.predict(X), 0.0)
        
        # Enforce quantile ordering constraint (90th percentile >= 50th percentile)
        mae_long_90 = np.maximum(mae_long_90, mae_long_50)

        prob_short = self.clf_short.predict_proba(X)[:, 1]
        mfe_short = np.maximum(self.reg_mfe_short.predict(X), 0.0)
        mae_short_50 = np.maximum(self.reg_mae_short_50.predict(X), 0.0)
        mae_short_90 = np.maximum(self.reg_mae_short_90.predict(X), 0.0)
        mae_short_90 = np.maximum(mae_short_90, mae_short_50)

        # Expected Value calculations: EV = P(Win) * MFE - (1 - P(Win)) * MAE_90
        ev_long = (prob_long * mfe_long) - ((1.0 - prob_long) * mae_long_90)
        ev_short = (prob_short * mfe_short) - ((1.0 - prob_short) * mae_short_90)

        return {
            "prob_long": prob_long,
            "mfe_long": mfe_long,
            "mae_long_50": mae_long_50,
            "mae_long_90": mae_long_90,
            "ev_long": ev_long,
            
            "prob_short": prob_short,
            "mfe_short": mfe_short,
            "mae_short_50": mae_short_50,
            "mae_short_90": mae_short_90,
            "ev_short": ev_short
        }
