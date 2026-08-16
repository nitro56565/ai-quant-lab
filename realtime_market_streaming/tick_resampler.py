import pandas as pd
import numpy as np
from typing import Dict

class TickResamplerEngine:
    """
    Multi-Timeframe OHLCV Resampler Engine.
    Resamples raw tick or sub-minute price feeds into standard timeframes:
      • 1m, 5m, 15m, 30m, 1h, 4h, 1d
    Guarantees 100% internal timeframe consistency across all resolutions.
    """
    TIMEFRAME_MAP = {
        '1m': '1min',
        '5m': '5min',
        '15m': '15min',
        '30m': '30min',
        '1h': '1h',
        '4h': '4h',
        '1d': '1D'
    }

    def resample_ticks_to_ohlcv(self, df_ticks: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        Resample tick DataFrame (with 'bid'/'ask' or 'price') to specified timeframe.
        """
        tf_code = self.TIMEFRAME_MAP.get(timeframe.lower(), timeframe)
        
        # Calculate mid price if bid/ask present
        if 'price' not in df_ticks.columns:
            if 'bid' in df_ticks.columns and 'ask' in df_ticks.columns:
                df_ticks['price'] = (df_ticks['bid'] + df_ticks['ask']) / 2.0
            elif 'ask' in df_ticks.columns:
                df_ticks['price'] = df_ticks['ask']
            elif 'bid' in df_ticks.columns:
                df_ticks['price'] = df_ticks['bid']
            else:
                raise ValueError("DataFrame must contain 'price', 'bid', or 'ask' column for resampling.")

        if 'volume' not in df_ticks.columns:
            if 'ask_vol' in df_ticks.columns and 'bid_vol' in df_ticks.columns:
                df_ticks['volume'] = df_ticks['ask_vol'] + df_ticks['bid_vol']
            else:
                df_ticks['volume'] = 1.0

        ohlc = df_ticks['price'].resample(tf_code).ohlc()
        vol = df_ticks['volume'].resample(tf_code).sum()
        
        df_res = pd.concat([ohlc, vol], axis=1).dropna(subset=['open', 'high', 'low', 'close'])
        df_res.index.name = 'timestamp'
        return df_res

    def resample_all_timeframes(self, df_ticks: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Resample tick DataFrame into all standard timeframes (1m to 1d).
        """
        results = {}
        for tf in self.TIMEFRAME_MAP.keys():
            results[tf] = self.resample_ticks_to_ohlcv(df_ticks.copy(), tf)
        return results
