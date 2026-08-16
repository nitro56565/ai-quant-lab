"""
Institutional AI Engine Package for AI Quant Lab.
Contains Meta Regime Engine, LightGBM + CatBoost Ensembles, Optuna Hyperparameter Tuning,
Universal Conformal Prediction, TreeSHAP Explainability, Data Drift Detection,
Probability Calibration Tracking, Model Persistence, and Calibrated Risk Grid Position Sizing.
"""

from .regime_hmm import HMMRegimeDetector
from .meta_regime import MetaRegimeEngine
from .lgbm_suite import LightGBMModelSuite
from .ensemble import LightGBMCatBoostEnsemble
from .optuna_tuner import OptunaTuner
from .conformal import ConformalPredictor
from .explainability import SignalExplainer
from .adaptive_sizer import AdaptivePositionSizer
from .drift_detector import DataDriftDetector
from .calibration_tracker import CalibrationTracker
from .persistence import ModelPersistor

__all__ = [
    "HMMRegimeDetector",
    "MetaRegimeEngine",
    "LightGBMModelSuite",
    "LightGBMCatBoostEnsemble",
    "OptunaTuner",
    "ConformalPredictor",
    "SignalExplainer",
    "AdaptivePositionSizer",
    "DataDriftDetector",
    "CalibrationTracker",
    "ModelPersistor"
]
