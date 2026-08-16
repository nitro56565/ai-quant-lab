import numpy as np
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("AdaptivePositionSizer")

class AdaptivePositionSizer:
    """
    Calibrated Risk Grid Position Sizing Engine:
    Maps multi-factor composite scores (Edge Score, Conformal Confidence, Model Disagreement, Meta-Regime, and Data Drift)
    onto a discrete, institutional risk percentage grid: {0.25%, 0.50%, 1.00%, 1.50%, 2.00%}.
    """
    def __init__(self, target_ev_pips: float = 34.0) -> None:
        self.target_ev_pips = target_ev_pips
        # Institutional Risk Percentage Grid
        self.risk_grid = [0.25, 0.50, 0.75, 1.00]

    def calculate_risk_percent(
        self,
        ev_pips: float,
        conformal_confidence: float = 1.0,
        disagreement_penalty: float = 0.0,
        regime_bull_prob: float = 0.5,
        drift_status: str = "NORMAL"
    ) -> float:
        """
        Determines target risk % from calibrated risk grid (capped at 1.0% max per trade).
        """
        # 1. Edge Score (0.0 to 2.0)
        edge_score = np.clip(ev_pips / max(self.target_ev_pips, 1.0), 0.0, 2.0)

        # 2. Confidence Score (0.0 to 1.0, reduced by disagreement and conformal width)
        conf_score = np.clip(conformal_confidence - (1.5 * disagreement_penalty), 0.1, 1.0)

        # 3. Regime Score (0.5 to 1.5)
        regime_score = 0.5 + np.clip(regime_bull_prob, 0.0, 1.0)

        # 4. Drift Penalty
        drift_penalty = 1.0
        if drift_status == "MODERATE_DRIFT":
            drift_penalty = 0.5
        elif drift_status == "SEVERE_DRIFT":
            drift_penalty = 0.0  # Disable strategy execution

        # Composite Sizing Index
        composite_index = edge_score * conf_score * regime_score * drift_penalty

        if composite_index <= 0.2:
            return 0.0  # Sit out
        elif composite_index <= 0.6:
            return 0.25
        elif composite_index <= 1.0:
            return 0.50
        elif composite_index <= 1.5:
            return 0.75
        else:
            return 1.00
