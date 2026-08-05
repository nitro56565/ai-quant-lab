import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger("DataDriftDetector")

class DataDriftDetector:
    """
    Data Drift & Covariate Shift Detection Engine:
    Calculates Kolmogorov-Smirnov (KS) test statistics and Population Stability Index (PSI)
    comparing out-of-sample feature distributions against training baseline distributions.
    Flags drift status ('NORMAL', 'MODERATE_DRIFT', 'SEVERE_DRIFT').
    """
    def __init__(self, ks_alpha: float = 0.01, psi_threshold_moderate: float = 0.10, psi_threshold_severe: float = 0.25) -> None:
        self.ks_alpha = ks_alpha
        self.psi_threshold_moderate = psi_threshold_moderate
        self.psi_threshold_severe = psi_threshold_severe

    def calculate_psi(self, reference: np.ndarray, current: np.ndarray, num_buckets: int = 10) -> float:
        """Calculate Population Stability Index (PSI) between reference and current distribution."""
        reference = reference[~np.isnan(reference)]
        current = current[~np.isnan(current)]
        
        if len(reference) == 0 or len(current) == 0:
            return 0.0

        percentiles = np.linspace(0, 100, num_buckets + 1)
        buckets = np.percentile(reference, percentiles)
        buckets[0] -= 1e-5
        buckets[-1] += 1e-5

        ref_counts, _ = np.histogram(reference, bins=buckets)
        curr_counts, _ = np.histogram(current, bins=buckets)

        ref_pct = np.maximum(ref_counts / len(reference), 1e-4)
        curr_pct = np.maximum(curr_counts / len(current), 1e-4)

        psi_val = np.sum((curr_pct - ref_pct) * np.log(curr_pct / ref_pct))
        return float(psi_val)

    def detect_drift(self, df_train: pd.DataFrame, df_test: pd.DataFrame, feature_cols: List[str]) -> Dict[str, Any]:
        """
        Calculates feature-level KS p-values and PSI values.
        Returns overall dataset drift status and drifted feature count.
        """
        drifted_features = []
        psi_scores = {}
        
        for col in feature_cols:
            if col not in df_train.columns or col not in df_test.columns:
                continue

            train_vals = df_train[col].dropna().values
            test_vals = df_test[col].dropna().values

            if len(train_vals) == 0 or len(test_vals) == 0:
                continue

            # 1. KS Test
            ks_stat, p_val = ks_2samp(train_vals, test_vals)
            # 2. PSI
            psi_val = self.calculate_psi(train_vals, test_vals)
            psi_scores[col] = psi_val

            if p_val < self.ks_alpha or psi_val > self.psi_threshold_moderate:
                drifted_features.append({"feature": col, "p_value": float(p_val), "psi": float(psi_val)})

        drift_ratio = len(drifted_features) / max(len(feature_cols), 1)
        mean_psi = float(np.mean(list(psi_scores.values()))) if psi_scores else 0.0

        if drift_ratio > 0.30 or mean_psi > self.psi_threshold_severe:
            status = "SEVERE_DRIFT"
        elif drift_ratio > 0.15 or mean_psi > self.psi_threshold_moderate:
            status = "MODERATE_DRIFT"
        else:
            status = "NORMAL"

        logger.info(f"DataDriftDetector Status: {status} (Drifted Features: {len(drifted_features)}/{len(feature_cols)}, Mean PSI: {mean_psi:.3f})")
        
        return {
            "status": status,
            "mean_psi": mean_psi,
            "drifted_count": len(drifted_features),
            "total_features": len(feature_cols),
            "drift_ratio": drift_ratio,
            "drifted_features": drifted_features[:10]  # Top 10 drifted features
        }
