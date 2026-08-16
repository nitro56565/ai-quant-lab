"""
HMM Regime Engine Guard Component.
Enforces:
1. Correct 9-State Regime Classification (3 HMM Directional States x 3 Volatility Quantiles)
2. Dynamic Regime Transition Handling
3. Regime State Persistence & Serialization Recovery
4. Invalid HMM Output Protection (NaN / Inf / Missing Model Rejection)
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any, Optional
from core_machine_learning.regime_hmm import HMMRegimeDetector

class HMMRegimeGuard:
    def __init__(self, model: Optional[HMMRegimeDetector] = None):
        self.model = model

    def set_model(self, model: HMMRegimeDetector):
        self.model = model

    def save_model(self, filepath: str):
        if self.model is None or not self.model.is_fitted:
            raise RuntimeError("Cannot save unfitted or missing HMM model.")
        joblib.dump(self.model, filepath)

    def load_model(self, filepath: str):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"HMM model file {filepath} not found.")
        self.model = joblib.load(filepath)

    def evaluate_regime(self, df_with_features: pd.DataFrame) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Evaluates current 9-State Regime (HMM Direction x Volatility Quantile).
        Returns:
            (is_valid: bool, reason_code: str, regime_info: Optional[dict])
        """
        if self.model is None or not self.model.is_fitted:
            return False, "INVALID_HMM_MISSING_MODEL", None

        if df_with_features is None or len(df_with_features) == 0:
            return False, "INVALID_HMM_EMPTY_DATA", None

        try:
            probs = self.model.predict_proba(df_with_features)
            latest_probs = probs[-1]
        except Exception as e:
            return False, f"INVALID_HMM_COMPUTATION_ERROR:{str(e)}", None

        # 1. Check NaN / Inf in HMM probabilities
        if np.isnan(latest_probs).any() or np.isinf(latest_probs).any():
            return False, "INVALID_HMM_NAN_INF_PROBABILITY", None

        # 2. Check Probability Sum Constraint (must sum to ~1.0)
        prob_sum = float(np.sum(latest_probs))
        if abs(prob_sum - 1.0) > 1e-4:
            return False, f"INVALID_HMM_PROBABILITY_SUM_{prob_sum:.4f}", None

        hmm_direction_state = int(np.argmax(latest_probs))
        if hmm_direction_state < 0 or hmm_direction_state > 2:
            return False, f"INVALID_HMM_STATE_BOUNDS_{hmm_direction_state}", None

        # Volatility Quantile Discretization
        if 'feat_vol_atr_pct' not in df_with_features.columns:
            return False, "INVALID_HMM_MISSING_VOL_FEATURE", None

        latest_vol_pct = float(df_with_features.iloc[-1]['feat_vol_atr_pct'])
        if np.isnan(latest_vol_pct) or np.isinf(latest_vol_pct):
            return False, "INVALID_HMM_VOL_PCT_NAN_INF", None

        vol_quantile = 0
        if latest_vol_pct >= 66.67:
            vol_quantile = 2
        elif latest_vol_pct >= 33.33:
            vol_quantile = 1

        state_9 = (hmm_direction_state * 3) + vol_quantile

        regime_info = {
            'hmm_direction_state': hmm_direction_state,
            'vol_quantile': vol_quantile,
            'state_9': state_9,
            'state_probs': latest_probs.tolist(),
            'vol_pct': latest_vol_pct
        }

        return True, "VALID_REGIME", regime_info
