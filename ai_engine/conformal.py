import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional
import logging

logger = logging.getLogger("ConformalPredictor")

class ConformalPredictor:
    """
    Split Conformal Prediction Engine for distribution-free risk & uncertainty estimation.
    Provides mathematically guaranteed 1 - alpha coverage bounds without parametric assumptions.
    """
    def __init__(self, alpha: float = 0.10) -> None:
        self.alpha = alpha
        self.q_hat = None
        self.is_calibrated = False

    def calibrate(self, y_val: np.ndarray, y_pred_val: np.ndarray) -> "ConformalPredictor":
        """
        Calibrate non-conformity scores on out-of-fold validation data.
        """
        y_val = np.asarray(y_val, dtype=float)
        y_pred_val = np.asarray(y_pred_val, dtype=float)
        
        residuals = np.abs(y_val - y_pred_val)
        n = len(residuals)
        
        if n == 0:
            raise ValueError("Validation residuals array is empty.")
            
        # Finite-sample corrected quantile index
        quantile_level = np.ceil((n + 1) * (1.0 - self.alpha)) / n
        quantile_level = min(1.0, max(0.0, quantile_level))
        
        self.q_hat = float(np.quantile(residuals, quantile_level))
        self.is_calibrated = True
        logger.info(f"ConformalPredictor calibrated with q_hat = {self.q_hat:.4f} pips at {1.0 - self.alpha:.0%} confidence.")
        return self

    def predict_interval(self, y_pred: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Produce [lower_bound, upper_bound] prediction interval for target predictions.
        """
        if not self.is_calibrated or self.q_hat is None:
            raise RuntimeError("ConformalPredictor must be calibrated before predict_interval().")
            
        y_pred = np.asarray(y_pred, dtype=float)
        lower_bound = np.maximum(0.0, y_pred - self.q_hat)
        upper_bound = y_pred + self.q_hat
        
        return lower_bound, upper_bound

    def calculate_uncertainty_score(self, y_pred: np.ndarray, atr_values: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate normalized uncertainty ratio U_t and confidence score C_t.
        Returns:
            uncertainty_ratio: Interval Width / ATR
            confidence_score: Clipped [0.2, 1.0] confidence score
        """
        lower, upper = self.predict_interval(y_pred)
        width = upper - lower
        atr_values = np.maximum(atr_values, 1e-6)
        
        uncertainty_ratio = width / (atr_values * 10000.0 if np.median(atr_values) < 0.01 else atr_values)
        confidence_score = np.clip(1.0 - (0.3 * uncertainty_ratio), 0.2, 1.0)
        
        return uncertainty_ratio, confidence_score
