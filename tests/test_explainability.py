import numpy as np
import pandas as pd
import unittest
from lightgbm import LGBMClassifier
from ai_engine.explainability import SignalExplainer

class TestSignalExplainer(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 200
        self.X = pd.DataFrame({
            "feat_trend_adx": np.random.uniform(10, 50, n),
            "feat_vol_atr": np.random.uniform(0.001, 0.005, n),
            "feat_osc_rsi": np.random.uniform(30, 70, n)
        })
        self.y = np.random.choice([0, 1], size=n)

        self.model = LGBMClassifier(n_estimators=10, max_depth=3, random_state=42, verbose=-1)
        self.model.fit(self.X, self.y)

    def test_explain_instance(self):
        explainer = SignalExplainer(self.model)
        sample = self.X.iloc[[0]]
        exp = explainer.explain_instance(sample, top_k=2)

        self.assertIn("top_attributions", exp)
        self.assertEqual(len(exp["top_attributions"]), 2)
        self.assertIn("feature", exp["top_attributions"][0])
        self.assertIn("shap_value", exp["top_attributions"][0])

if __name__ == "__main__":
    unittest.main()
