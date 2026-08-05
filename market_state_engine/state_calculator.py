import numpy as np
import pandas as pd
import logging

logger = logging.getLogger("MarketStateEngine")

class MarketStateEngine:
    """
    AI 2 — Quantitative Market State Engine.
    Transforms raw OHLCV and feature matrix indicators into normalized [0, 100] market state scores:
    1. Trend Strength (0-100)
    2. Trend Quality / Cleanliness (0-100)
    3. Volatility Score (0-100)
    4. Liquidity Score (0-100)
    """
    def __init__(self) -> None:
        pass

    def compute_market_state(self, df: pd.DataFrame, idx: int) -> dict:
        row = df.iloc[idx]
        
        # 1. Trend Strength (0-100): ADX & EMA Stack Alignment
        adx = float(row.get('feat_trend_adx', 20.0)) if not pd.isna(row.get('feat_trend_adx', 20.0)) else 20.0
        ema_stack = float(row.get('feat_trend_ema_stack', 1)) if not pd.isna(row.get('feat_trend_ema_stack', 1)) else 1.0
        trend_strength = float(np.clip((adx / 50.0 * 60.0) + (ema_stack * 20.0), 0.0, 100.0))
        
        # 2. Trend Quality / Cleanliness (0-100): DI Spread & Persistence
        di_spread = abs(float(row.get('feat_trend_di_spread', 0.0))) if not pd.isna(row.get('feat_trend_di_spread', 0.0)) else 0.0
        persistence = float(row.get('feat_trend_persistence', 0.5)) if not pd.isna(row.get('feat_trend_persistence', 0.5)) else 0.5
        trend_quality = float(np.clip((di_spread / 40.0 * 50.0) + (persistence * 50.0), 0.0, 100.0))
        
        # 3. Volatility Score (0-100): ATR Percentile & Vol Squeeze Ratio
        atr_pct = float(row.get('feat_vol_atr_pct', 0.5)) if not pd.isna(row.get('feat_vol_atr_pct', 0.5)) else 0.5
        vol_squeeze = float(row.get('feat_vol_squeeze_ratio', 1.0)) if not pd.isna(row.get('feat_vol_squeeze_ratio', 1.0)) else 1.0
        volatility_score = float(np.clip((atr_pct * 70.0) + (min(vol_squeeze, 2.0) / 2.0 * 30.0), 0.0, 100.0))
        
        # 4. Liquidity Score (0-100): Volume Ratio & Body-to-Range Ratio
        vol_ratio = float(row.get('feat_liq_volume_ratio', 1.0)) if not pd.isna(row.get('feat_liq_volume_ratio', 1.0)) else 1.0
        body_ratio = float(row.get('feat_liq_body_ratio', 0.5)) if not pd.isna(row.get('feat_liq_body_ratio', 0.5)) else 0.5
        liquidity_score = float(np.clip((min(vol_ratio, 2.0) / 2.0 * 60.0) + (body_ratio * 40.0), 0.0, 100.0))
        
        return {
            "trend_strength": round(trend_strength, 1),
            "trend_quality": round(trend_quality, 1),
            "volatility_score": round(volatility_score, 1),
            "liquidity_score": round(liquidity_score, 1)
        }
