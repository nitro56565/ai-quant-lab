import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
import numpy as np
import pandas as pd
from execution_engine import ExecutionEngine

class TestEmpiricallyCalibratedExecution(unittest.TestCase):
    def setUp(self):
        self.engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
        
        # Build 100-bar dummy DataFrame
        dates = pd.date_range("2024-01-01", periods=100, freq="1h")
        self.df = pd.DataFrame({
            "open": 1.0800 + np.sin(np.linspace(0, 10, 100)) * 0.0050,
            "high": 1.0810 + np.sin(np.linspace(0, 10, 100)) * 0.0050,
            "low": 1.0790 + np.sin(np.linspace(0, 10, 100)) * 0.0050,
            "close": 1.0805 + np.sin(np.linspace(0, 10, 100)) * 0.0050,
            "atr": np.full(100, 0.0020),
            "feat_vol_atr": np.full(100, 0.0020)
        }, index=dates)
        
        self.signals = np.full(100, None, dtype=object)
        self.signals[10] = "BUY"
        self.signals[30] = "SELL"
        self.signals[50] = "BUY"
        self.signals[70] = "SELL"
        
        self.config = {"sl_multiplier": 2.0, "tp_multiplier": 3.6}

    def test_latency_and_asymmetric_slippage(self):
        trades = self.engine.run_simulation(
            df=self.df,
            signals=self.signals,
            config=self.config,
            symbol="EURUSD",
            pip_size=0.0001,
            strategy_name="BaseStrategy",
            limit_retrace_atr_mult=0.25,
            latency_ms=300,
            asymmetric_slippage_pips=0.30,
            last_look_rejection_rate=0.0, # Zero rejection for deterministic test
            commission_per_lot_usd=7.00
        )
        
        closed = [t for t in trades if t['status'] == 'closed']
        self.assertGreater(len(closed), 0, "Should execute at least 1 trade")
        
        # Verify entry price includes adverse slippage drag
        t0 = closed[0]
        base_limit = self.df['close'].iloc[10] - (0.0020 * 0.25)
        # Entry price should be higher than base limit for BUY due to adverse slippage penalty
        self.assertGreaterEqual(t0['entry_price'], base_limit)

    def test_lp_last_look_rejections(self):
        # With 100% rejection rate, 0 trades should execute
        trades = self.engine.run_simulation(
            df=self.df,
            signals=self.signals,
            config=self.config,
            symbol="EURUSD",
            pip_size=0.0001,
            strategy_name="BaseStrategy",
            limit_retrace_atr_mult=0.25,
            latency_ms=300,
            asymmetric_slippage_pips=0.30,
            last_look_rejection_rate=1.00, # 100% rejection
            commission_per_lot_usd=7.00
        )
        closed = [t for t in trades if t['status'] == 'closed']
        self.assertEqual(len(closed), 0, "100% rejection rate should result in 0 closed trades")

if __name__ == '__main__':
    unittest.main()
