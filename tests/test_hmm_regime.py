import numpy as np
import pandas as pd
import unittest
from core_machine_learning.regime_hmm import HMMRegimeDetector

class TestHMMRegimeDetector(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 500
        dates = pd.date_range("2020-01-01", periods=n, freq="1h")
        self.df = pd.DataFrame({
            "feat_trend_ema50_slope": np.random.randn(n) * 0.001,
            "feat_vol_atr_pct": np.abs(np.random.randn(n) * 0.01) + 0.005,
            "feat_trend_adx": np.random.uniform(10, 50, size=n),
            "feat_osc_rsi": np.random.uniform(30, 70, size=n),
            "close": 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
        }, index=dates)

    def test_fit_and_predict(self):
        detector = HMMRegimeDetector(n_components=3, random_state=42)
        detector.fit(self.df)
        self.assertTrue(detector.is_fitted)

        probs = detector.predict_proba(self.df)
        self.assertEqual(probs.shape, (len(self.df), 3))
        # Verify row sums equal 1.0
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, rtol=1e-5)

        states = detector.predict(self.df)
        self.assertEqual(len(states), len(self.df))
        self.assertTrue(set(states).issubset({0, 1, 2}))

    def test_transform_dataframe(self):
        detector = HMMRegimeDetector(n_components=3, random_state=42)
        detector.fit(self.df)
        df_out = detector.transform_dataframe(self.df)
        self.assertIn("hmm_state", df_out.columns)
        self.assertIn("hmm_prob_0", df_out.columns)
        self.assertIn("hmm_prob_1", df_out.columns)
        self.assertIn("hmm_prob_2", df_out.columns)

if __name__ == "__main__":
    unittest.main()
