"""
PAE Decision Engine Guard Component.
Evaluates model ensemble predictions against production thresholds:
1. High-Confidence Valid Signal Evaluation (PAE_PASS)
2. Low Probability Rejection (LOW_PROBABILITY)
3. Negative EV Rejection (NEGATIVE_EV)
4. EV Passes but Low Probability Rejection (LOW_PROBABILITY)
5. Long/Short Conflict Handling
6. Multi-Model Ensemble Voting & Disagreement Resolution
"""

import numpy as np
from typing import Tuple, Dict, Any, Optional, List

class PAEDecisionGuard:
    def __init__(self, default_long_threshold: float = 0.38, default_short_threshold: float = 0.38):
        self.default_long_threshold = default_long_threshold
        self.default_short_threshold = default_short_threshold

    def evaluate_model_disagreement(self, p_lgb: float, p_cat: float, p_xgb: float) -> Tuple[float, float]:
        """
        Ensemble aggregation rule:
        Calculates simple arithmetic mean across LGBM, CatBoost, XGBoost.
        Returns:
            (ensemble_p, disagreement_std)
        """
        model_probs = [p_lgb, p_cat, p_xgb]
        ensemble_p = float(np.mean(model_probs))
        disagreement_std = float(np.std(model_probs))
        return ensemble_p, disagreement_std

    def compute_expected_value(self, prob: float, win_reward_r: float = 2.0, loss_risk_r: float = 1.0, friction_r: float = 0.15) -> float:
        """
        Expected Value (EV) calculation in R-multiples:
        EV = (P * Win_R) - ((1 - P) * Loss_R) - Friction_R
        """
        return (prob * win_reward_r) - ((1.0 - prob) * loss_risk_r) - friction_r

    def evaluate_decision(
        self,
        p_long_lgb: float, p_long_cat: float, p_long_xgb: float,
        p_short_lgb: float, p_short_cat: float, p_short_xgb: float,
        regime_state_9: int,
        custom_threshold: Optional[float] = None,
        win_reward_r: float = 2.0, loss_risk_r: float = 1.0, friction_r: float = 0.15,
        vol_rank_pct: float = 50.0
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Full PAE / Model Decision Engine evaluation.
        """
        # Determine regime threshold
        # Regimes 3, 4, 5 (Range regimes) require P >= 0.42, others require 0.38
        regime_group = regime_state_9 // 3
        required_p = custom_threshold if custom_threshold is not None else (0.42 if regime_group == 1 else 0.38)

        # Ensemble calculations
        ens_long_p, long_std = self.evaluate_model_disagreement(p_long_lgb, p_long_cat, p_long_xgb)
        ens_short_p, short_std = self.evaluate_model_disagreement(p_short_lgb, p_short_cat, p_short_xgb)

        long_ev = self.compute_expected_value(ens_long_p, win_reward_r, loss_risk_r, friction_r)
        short_ev = self.compute_expected_value(ens_short_p, win_reward_r, loss_risk_r, friction_r)

        vol_pass = (vol_rank_pct >= 40.0)

        pass_long = (ens_long_p >= required_p) and vol_pass
        pass_short = (ens_short_p >= required_p) and vol_pass

        # 1. Long/Short Conflict Handling
        if pass_long and pass_short:
            if ens_long_p > ens_short_p and long_ev > 0.0:
                pass_short = False
            elif ens_short_p > ens_long_p and short_ev > 0.0:
                pass_long = False
            else:
                return False, "REJECT_LONG_SHORT_CONFLICT", None

        # 2. Rejection Logic Check
        if not pass_long and not pass_short:
            # Determine primary rejection reason
            if not vol_pass:
                return False, "LOW_VOLATILITY", {
                    'vol_rank_pct': vol_rank_pct, 'required_vol': 40.0
                }
            elif max(ens_long_p, ens_short_p) < required_p:
                return False, "LOW_PROBABILITY", {
                    'ens_long_p': ens_long_p, 'ens_short_p': ens_short_p,
                    'required_p': required_p, 'long_ev': long_ev, 'short_ev': short_ev
                }
            else:
                return False, "NEGATIVE_EV", {
                    'ens_long_p': ens_long_p, 'ens_short_p': ens_short_p,
                    'required_p': required_p, 'long_ev': long_ev, 'short_ev': short_ev
                }

        # Long decision path
        if pass_long:
            if long_ev <= 0.0:
                return False, "NEGATIVE_EV", {'ens_long_p': ens_long_p, 'long_ev': long_ev, 'required_p': required_p}
            decision_info = {
                'direction': 'BUY', 'ensemble_prob': ens_long_p, 'expected_value_r': long_ev,
                'disagreement_std': long_std, 'required_p': required_p, 'regime_state_9': regime_state_9
            }
            return True, "PAE_PASS", decision_info

        # Short decision path
        if pass_short:
            if short_ev <= 0.0:
                return False, "NEGATIVE_EV", {'ens_short_p': ens_short_p, 'short_ev': short_ev, 'required_p': required_p}
            decision_info = {
                'direction': 'SELL', 'ensemble_prob': ens_short_p, 'expected_value_r': short_ev,
                'disagreement_std': short_std, 'required_p': required_p, 'regime_state_9': regime_state_9
            }
            return True, "PAE_PASS", decision_info

        return False, "LOW_PROBABILITY", None
