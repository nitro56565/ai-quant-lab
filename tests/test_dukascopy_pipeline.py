import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'realtime_market_streaming')))

import unittest
import pandas as pd
import numpy as np
from realtime_market_streaming.data_validator import DataValidatorEngine
from realtime_market_streaming.tick_resampler import TickResamplerEngine

class TestDukascopyPipeline(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidatorEngine()
        self.resampler = TickResamplerEngine()

        dates = pd.date_range("2024-01-01 00:00:00", periods=1000, freq="1s", tz="UTC")
        self.df_ticks = pd.DataFrame({
            "bid": 2000.0 + np.sin(np.linspace(0, 10, 1000)) * 5.0,
            "ask": 2000.2 + np.sin(np.linspace(0, 10, 1000)) * 5.0,
            "bid_vol": 1.0,
            "ask_vol": 1.0
        }, index=dates)

    def test_tick_validation(self):
        res = self.validator.validate_ticks(self.df_ticks)
        self.assertTrue(res['is_valid'], f"Validation failed with issues: {res.get('issues')}")

    def test_tick_resampling(self):
        df_1m = self.resampler.resample_ticks_to_ohlcv(self.df_ticks.copy(), "1m")
        c_res = self.validator.validate_candles(df_1m)
        self.assertTrue(c_res['is_valid'], f"Candle validation failed: {c_res.get('issues')}")
        self.assertGreater(len(df_1m), 0, "Resampled 1m candles should not be empty")

if __name__ == '__main__':
    unittest.main()
