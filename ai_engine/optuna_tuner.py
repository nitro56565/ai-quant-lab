import optuna
import lightgbm as lgb
from catboost import CatBoostClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import log_loss
import numpy as np
import pandas as pd
import logging

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger("OptunaTuner")

class OptunaTuner:
    """
    Optuna Dynamic Hyperparameter Tuner:
    Finds optimal hyperparameters per rolling walk-forward window using TimeSeriesSplit cross-validation.
    """
    def __init__(self, n_trials: int = 15, timeout: int = 30, random_state: int = 42) -> None:
        self.n_trials = n_trials
        self.timeout = timeout
        self.random_state = random_state

    def tune_lightgbm_classifier(self, X_train: pd.DataFrame, y_train: pd.Series) -> dict:
        """Find best LightGBM classifier hyperparameters."""
        def objective(trial):
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 30, 150),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
                'max_depth': trial.suggest_int('max_depth', 3, 8),
                'num_leaves': trial.suggest_int('num_leaves', 15, 63),
                'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                'random_state': self.random_state,
                'verbose': -1,
                'n_jobs': -1
            }
            
            tscv = TimeSeriesSplit(n_splits=3)
            losses = []
            for train_idx, val_idx in tscv.split(X_train):
                X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
                y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                clf = lgb.LGBMClassifier(**params)
                clf.fit(X_tr, y_tr)
                preds = clf.predict_proba(X_val)
                losses.append(log_loss(y_val, preds))
                
            return float(np.mean(losses))

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=self.n_trials, timeout=self.timeout)
        logger.info(f"Optuna LightGBM best params: {study.best_params}")
        return study.best_params

    def tune_catboost_classifier(self, X_train: pd.DataFrame, y_train: pd.Series) -> dict:
        """Find best CatBoost classifier hyperparameters."""
        def objective(trial):
            params = {
                'iterations': trial.suggest_int('iterations', 30, 150),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.15, log=True),
                'depth': trial.suggest_int('depth', 3, 7),
                'l2_leaf_reg': trial.suggest_float('l2_leaf_reg', 1e-3, 10.0, log=True),
                'random_seed': self.random_state,
                'verbose': False
            }
            
            tscv = TimeSeriesSplit(n_splits=3)
            losses = []
            for train_idx, val_idx in tscv.split(X_train):
                X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
                y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                clf = CatBoostClassifier(**params)
                clf.fit(X_tr, y_tr, verbose=False)
                preds = clf.predict_proba(X_val)
                losses.append(log_loss(y_val, preds))
                
            return float(np.mean(losses))

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=self.n_trials, timeout=self.timeout)
        logger.info(f"Optuna CatBoost best params: {study.best_params}")
        return study.best_params
