import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from scripts.run_master_ablation_scoreboard import run_stage_simulation
from historical_data_ingestion import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
import numpy as np

class TestMasterAblationScoreboard(unittest.TestCase):
    def test_run_stage_simulation(self):
        loader = DataLoader()
        symbol = "EURUSD"
        start_date = "2018-01-01"
        end_date = "2025-12-31"

        strat = InstitutionalAIStrategy()
        df_signals = strat.prepare_data(loader, symbol, start_date, end_date)
        n_rows = len(df_signals)
        signals = df_signals['signal'].values.copy()

        m = run_stage_simulation(
            df_signals, signals, np.ones(n_rows), np.ones(n_rows), symbol, loader, start_date, end_date
        )

        self.assertIn("return_pct", m)
        self.assertIn("pf", m)
        self.assertIn("sharpe", m)
        self.assertIn("max_dd", m)
        self.assertGreaterEqual(m["trades"], 0)

if __name__ == '__main__':
    unittest.main()
