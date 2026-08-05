import numpy as np
import pandas as pd
import logging

logger = logging.getLogger("ExecutionContextEngine")

class ExecutionContextEngine:
    """
    Execution Context Engine.
    Computes normalized [0, 100] Context Scores using rolling quantile ranks:
    1. trend_alignment (0-100): Directional alignment with primary trend
    2. trend_persistence (0-100): Cleanliness & direction consistency rank
    3. volatility_state (0-100): Rolling ATR & realized volatility rank
    4. liquidity_state (0-100): Rolling volume & body ratio rank
    """
    def __init__(self, rolling_window: int = 1000) -> None:
        self.rolling_window = rolling_window

    def prepare_rolling_ranks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates rolling percentile ranks (0 to 100) across 1,000 bars
        to prevent feature saturation.
        """
        df = df.copy()
        
        # 1. Raw Feature Extraction
        adx = df.get('feat_trend_adx', pd.Series(20.0, index=df.index)).fillna(20.0)
        di_spread = abs(df.get('feat_trend_di_spread', pd.Series(0.0, index=df.index)).fillna(0.0))
        atr = df.get('feat_vol_atr', pd.Series(0.0015, index=df.index)).fillna(0.0015)
        volume = df.get('volume', pd.Series(100.0, index=df.index)).fillna(100.0)
        
        # 2. Rolling Percentile Ranks (0.0 to 100.0)
        df['rank_adx'] = adx.rolling(window=self.rolling_window, min_periods=100).apply(
            lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) * 100.0, raw=False
        ).fillna(50.0)
        
        df['rank_di_spread'] = di_spread.rolling(window=self.rolling_window, min_periods=100).apply(
            lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) * 100.0, raw=False
        ).fillna(50.0)
        
        df['rank_atr'] = atr.rolling(window=self.rolling_window, min_periods=100).apply(
            lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) * 100.0, raw=False
        ).fillna(50.0)
        
        df['rank_volume'] = volume.rolling(window=self.rolling_window, min_periods=100).apply(
            lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) * 100.0, raw=False
        ).fillna(50.0)
        
        return df

    def compute_context(self, df: pd.DataFrame, idx: int, trade_direction: str) -> dict:
        row = df.iloc[idx]
        
        adx_rank = float(row.get('rank_adx', 50.0))
        di_spread_rank = float(row.get('rank_di_spread', 50.0))
        atr_rank = float(row.get('rank_atr', 50.0))
        volume_rank = float(row.get('rank_volume', 50.0))
        
        ema_stack = float(row.get('feat_trend_ema_stack', 1.0))  # 2.0 = Bull, 0.0 = Bear
        
        # Directional Trend Alignment (0 to 100)
        if trade_direction == 'BUY':
            trend_alignment = (adx_rank * 0.5) + (ema_stack / 2.0 * 50.0)
        else:  # 'SELL'
            trend_alignment = (adx_rank * 0.5) + ((2.0 - ema_stack) / 2.0 * 50.0)
            
        trend_alignment = float(np.clip(trend_alignment, 0.0, 100.0))
        
        return {
            "trend_alignment": round(trend_alignment, 1),
            "trend_persistence": round(float(np.clip(di_spread_rank, 0.0, 100.0)), 1),
            "volatility_state": round(float(np.clip(atr_rank, 0.0, 100.0)), 1),
            "liquidity_state": round(float(np.clip(volume_rank, 0.0, 100.0)), 1)
        }
