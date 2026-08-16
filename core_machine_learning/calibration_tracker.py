import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss
from typing import Dict, Any, List
import logging

logger = logging.getLogger("CalibrationTracker")

class CalibrationTracker:
    """
    Probability Calibration Tracker:
    Calculates Expected Calibration Error (ECE) and Brier Score
    to continuously monitor model probability reliability over time.
    """
    def __init__(self, n_bins: int = 10) -> None:
        self.n_bins = n_bins

    def calculate_ece(self, y_true: np.ndarray, y_prob: np.ndarray) -> float:
        """Calculate Expected Calibration Error (ECE)."""
        y_true = np.asarray(y_true, dtype=float)
        y_prob = np.asarray(y_prob, dtype=float)

        bin_boundaries = np.linspace(0.0, 1.0, self.n_bins + 1)
        ece = 0.0
        n_samples = len(y_true)

        for i in range(self.n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]

            in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper if i < self.n_bins - 1 else y_prob <= bin_upper)
            bin_size = np.sum(in_bin)

            if bin_size > 0:
                acc_in_bin = np.mean(y_true[in_bin])
                conf_in_bin = np.mean(y_prob[in_bin])
                ece += (bin_size / n_samples) * np.abs(acc_in_bin - conf_in_bin)

        return float(ece)

    def evaluate_calibration(self, y_true: np.ndarray, y_prob: np.ndarray) -> Dict[str, Any]:
        """
        Evaluate full calibration diagnostics.
        """
        ece = self.calculate_ece(y_true, y_prob)
        brier = float(brier_score_loss(y_true, y_prob))

        bin_boundaries = np.linspace(0.0, 1.0, self.n_bins + 1)
        calibration_curve = []

        for i in range(self.n_bins):
            bin_lower = bin_boundaries[i]
            bin_upper = bin_boundaries[i + 1]
            in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper if i < self.n_bins - 1 else y_prob <= bin_upper)
            if np.sum(in_bin) > 0:
                calibration_curve.append({
                    "bin_midpoint": float((bin_lower + bin_upper) / 2.0),
                    "pred_prob": float(np.mean(y_prob[in_bin])),
                    "actual_win_rate": float(np.mean(y_true[in_bin])),
                    "count": int(np.sum(in_bin))
                })

        logger.info(f"Calibration Evaluation: ECE = {ece:.4f}, Brier Score = {brier:.4f}")

        return {
            "ece": ece,
            "brier_score": brier,
            "calibration_curve": calibration_curve
        }
