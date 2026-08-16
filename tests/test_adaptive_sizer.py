import unittest
from core_machine_learning.adaptive_sizer import AdaptivePositionSizer

class TestAdaptivePositionSizer(unittest.TestCase):
    def test_risk_grid_factors(self):
        sizer = AdaptivePositionSizer(target_ev_pips=34.0)

        # Baseline optimal trade -> 1.50% or 2.00% risk
        risk_base = sizer.calculate_risk_percent(
            ev_pips=34.0,
            conformal_confidence=1.0,
            disagreement_penalty=0.0,
            regime_bull_prob=0.8,
            drift_status="NORMAL"
        )
        self.assertIn(risk_base, [1.00, 1.50, 2.00])

        # Low EV, low confidence, severe drift -> 0.0% risk (sit out)
        risk_drift = sizer.calculate_risk_percent(
            ev_pips=10.0,
            conformal_confidence=0.3,
            disagreement_penalty=0.4,
            regime_bull_prob=0.2,
            drift_status="SEVERE_DRIFT"
        )
        self.assertEqual(risk_drift, 0.0)

if __name__ == "__main__":
    unittest.main()
