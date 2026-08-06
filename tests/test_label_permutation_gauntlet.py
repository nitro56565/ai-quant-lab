import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from scripts.run_label_permutation_gauntlet import compute_composite_institutional_score

class TestLabelPermutationGauntlet(unittest.TestCase):
    def test_composite_institutional_score_calc(self):
        s1 = compute_composite_institutional_score(pf=1.50, sharpe=1.20, max_dd=8.0, dsr=0.05, yoy_positive_years=7)
        self.assertGreater(s1, 0.0)

        s2 = compute_composite_institutional_score(pf=0.90, sharpe=-0.20, max_dd=40.0, dsr=0.0, yoy_positive_years=2)
        self.assertEqual(s2, 0.0)

if __name__ == '__main__':
    unittest.main()
