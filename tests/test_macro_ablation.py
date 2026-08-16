import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
import unittest
from historical_data_ingestion import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from macro_engine.parser import MacroContextEngine
from execution_policy_engine.policy import ExecutionPolicyEngine
from execution_engine import ExecutionEngine

class TestMacroEngineAblation(unittest.TestCase):
    def setUp(self):
        self.loader = DataLoader()
        self.symbol = "EURUSD"
        self.start_date = "2018-01-01"
        self.end_date = "2025-12-31"
        self.strat = InstitutionalAIStrategy()

    def test_macro_context_scores(self):
        macro_engine = MacroContextEngine()
        ts = pd.Timestamp("2024-03-15 13:30:00")
        df_dummy = pd.DataFrame({
            'feat_trend_adx': [30.0],
            'feat_trend_ema_stack': [2.0],
            'feat_vol_atr_pct': [60.0],
            'feat_vol_squeeze_ratio': [1.2],
            'feat_liq_volume_ratio': [1.5],
            'feat_liq_body_ratio': [0.6]
        }, index=[ts])

        ctx = macro_engine.get_macro_context(self.symbol, ts, df_dummy, 0)
        self.assertIn("cb_divergence", ctx)
        self.assertIn("risk_sentiment", ctx)
        self.assertIn("event_risk", ctx)
        self.assertIn("market_context_index", ctx)
        self.assertIn("summary_rationale", ctx)
        self.assertTrue(ctx.get("far_certified", False))


    def test_execution_policy_defensive_capping(self):
        policy_engine = ExecutionPolicyEngine(allow_risk_expansion=False)
        state_vector = {
            "market_context_index": 85.0, # High score
            "trend_alignment": 80.0,
            "volatility_state": 70.0,
            "macro_context": {"event_risk": 10.0, "summary_rationale": "Test rationale"}
        }

        pol = policy_engine.determine_policy(state_vector)
        # Phase 1 safety check: risk_multiplier MUST NOT exceed 1.00
        self.assertLessEqual(pol['risk_multiplier'], 1.00)
        self.assertIn("explainability", pol)

    def test_level_1_event_risk_reduction(self):
        policy_engine = ExecutionPolicyEngine(allow_risk_expansion=False)
        state_vector = {
            "market_context_index": 85.0,
            "macro_context": {"event_risk": 95.0, "summary_rationale": "High news event risk"}
        }

        pol = policy_engine.determine_policy(state_vector)
        self.assertEqual(pol['action'], "EXECUTE_REDUCED")
        self.assertEqual(pol['risk_multiplier'], 0.50)
        self.assertEqual(pol['time_exit_hours'], 6)

if __name__ == '__main__':
    unittest.main()
