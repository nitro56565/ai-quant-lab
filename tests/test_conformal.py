import numpy as np
import unittest
from ai_engine.conformal import ConformalPredictor

class TestConformalPredictor(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 300
        self.y_val = np.random.uniform(10, 50, size=n)
        self.y_pred_val = self.y_val + np.random.normal(0, 3, size=n)
        self.y_test = np.random.uniform(10, 50, size=50)

    def test_calibration_and_interval(self):
        cp = ConformalPredictor(alpha=0.10)
        cp.calibrate(self.y_val, self.y_pred_val)
        self.assertTrue(cp.is_calibrated)
        self.assertGreater(cp.q_hat, 0.0)

        lower, upper = cp.predict_interval(self.y_test)
        self.assertEqual(len(lower), 50)
        self.assertEqual(len(upper), 50)
        self.assertTrue(np.all(upper >= lower))

    def test_uncertainty_score(self):
        cp = ConformalPredictor(alpha=0.10)
        cp.calibrate(self.y_val, self.y_pred_val)
        atr = np.full(50, 15.0)
        u_ratio, conf = cp.calculate_uncertainty_score(self.y_test, atr)
        self.assertTrue(np.all(conf >= 0.2))
        self.assertTrue(np.all(conf <= 1.0))

if __name__ == "__main__":
    unittest.main()
