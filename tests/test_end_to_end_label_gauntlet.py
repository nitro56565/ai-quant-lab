import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from scripts.run_end_to_end_label_research_gauntlet import evaluate_6_certification_gates

class TestEndToEndLabelGauntlet(unittest.TestCase):
    def test_evaluate_6_certification_gates(self):
        m = {'pf': 1.27, 'sharpe': 1.08}
        gates = evaluate_6_certification_gates(
            m=m, dsr=0.02, yoy_positive_years=7, max_single_yr_pct=24.0, rs_conf=0.60, baseline_pf=1.17, baseline_sharpe=0.80
        )
        self.assertTrue(gates['certified_production_candidate'])

        m_bad = {'pf': 1.05, 'sharpe': 0.40}
        gates_bad = evaluate_6_certification_gates(
            m=m_bad, dsr=-0.01, yoy_positive_years=3, max_single_yr_pct=50.0, rs_conf=0.20, baseline_pf=1.17, baseline_sharpe=0.80
        )
        self.assertFalse(gates_bad['certified_production_candidate'])

if __name__ == '__main__':
    unittest.main()
