import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from scripts.run_4_track_research_suite import compute_robustness_score

class TestFourTrackResearchSuite(unittest.TestCase):
    def test_compute_robustness_score(self):
        s1 = compute_robustness_score(pf=1.35, sharpe=1.15, max_dd=8.0, dsr=0.05, cpcv_stability=0.90, ece=0.035)
        self.assertGreater(s1, 0.0)
        self.assertLess(s1, 10.0)

if __name__ == '__main__':
    unittest.main()
