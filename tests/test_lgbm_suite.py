import numpy as np
import pandas as pd
import unittest
from core_machine_learning.lgbm_suite import LightGBMModelSuite

class TestLightGBMModelSuite(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 400
        self.X = pd.DataFrame({
            "feat_1": np.random.randn(n),
            "feat_2": np.random.randn(n),
            "feat_3": np.random.uniform(0, 10, n)
        })
        self.targets = {
            "dir_long": np.random.choice([0, 1], size=n),
            "mfe_long": np.abs(np.random.randn(n) * 20.0) + 5.0,
            "mae_long": np.abs(np.random.randn(n) * 10.0) + 2.0,
            "dir_short": np.random.choice([0, 1], size=n),
            "mfe_short": np.abs(np.random.randn(n) * 20.0) + 5.0,
            "mae_short": np.abs(np.random.randn(n) * 10.0) + 2.0,
        }

    def test_fit_and_predict(self):
        suite = LightGBMModelSuite(n_estimators=20, max_depth=3, random_state=42)
        suite.fit(self.X, self.targets)
        self.assertTrue(suite.is_fitted)

        preds = suite.predict(self.X)
        self.assertIn("prob_long", preds)
        self.assertIn("ev_long", preds)
        self.assertIn("mae_long_90", preds)

        # Check probability bounds
        self.assertTrue(np.all((preds["prob_long"] >= 0.0) & (preds["prob_long"] <= 1.0)))
        # Check quantile constraint: MAE 90 >= MAE 50
        self.assertTrue(np.all(preds["mae_long_90"] >= preds["mae_long_50"]))
        self.assertTrue(np.all(preds["mae_short_90"] >= preds["mae_short_50"]))

if __name__ == "__main__":
    unittest.main()
