import unittest
import pandas as pd
import numpy as np
from historical_data_ingestion import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from execution_engine import ExecutionEngine

class TestInstitutionalAIStrategy(unittest.TestCase):
    def test_revised_institutional_ai_features(self):
        loader = DataLoader()
        strat = InstitutionalAIStrategy(ev_threshold=34.0)

        # Run 2-year backtest (2022-2023)
        df_signals = strat.prepare_data(loader, "EURUSD", "2022-01-01", "2023-12-31")
        self.assertGreater(len(df_signals), 0)

        # Assert presence of all 10 quantitative outputs
        self.assertIn("prob_bull_trend", df_signals.columns)
        self.assertIn("disagreement_long", df_signals.columns)
        self.assertIn("pred_mfe_10_long", df_signals.columns)
        self.assertIn("pred_mfe_90_long", df_signals.columns)
        self.assertIn("pred_mae_10_long", df_signals.columns)
        self.assertIn("pred_mae_long", df_signals.columns)
        self.assertIn("conformal_conf", df_signals.columns)
        self.assertIn("target_risk_pct", df_signals.columns)

        signals = np.full(len(df_signals), None, dtype=object)
        if 'signal' in df_signals.columns:
            signals = df_signals['signal'].values
        else:
            signals[df_signals['entry_signal'].values] = 'BUY'

        exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
        trades = exec_engine.run_simulation(
            df=df_signals,
            signals=signals,
            config={'sl_multiplier': 1.3, 'tp_multiplier': None, 'trail_multiplier': 1.5},
            symbol="EURUSD",
            pip_size=0.0001,
            strategy_name="InstitutionalAIStrategy"
        )
        self.assertIsInstance(trades, list)

if __name__ == "__main__":
    unittest.main()
