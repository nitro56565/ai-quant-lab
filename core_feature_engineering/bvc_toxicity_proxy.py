import numpy as np
import pandas as pd
from scipy.stats import norm
import logging

logger = logging.getLogger("BVCToxicityProxyCalculator")

class BVCToxicityProxyCalculator:
    """
    Bulk Volume Classification (BVC) Order Flow Toxicity Proxy Calculator for H1 Candle Data.
    
    Uses Bulk Volume Classification (BVC) to estimate buyer-initiated vs. seller-initiated volume:
    V_buy  = Volume * Phi(Delta_P / sigma_P)
    V_sell = Volume - V_buy
    
    Computes rolling toxicity imbalance ratio over window w:
    Toxicity(w) = Sum(|V_buy - V_sell|) / Sum(Volume)
    
    Returns normalized percentile score (0-100): feat_bvc_toxicity_proxy.
    """

    def compute_bvc_toxicity_proxy(self, df: pd.DataFrame, window: int = 24) -> pd.Series:
        """
        Computes BVC Toxicity Proxy for a given window horizon w (e.g. 12, 24, 36, 48 hours).
        """
        if 'close' not in df.columns or 'open' not in df.columns:
            logger.warning("Missing required OHLC columns for BVC Toxicity Proxy calculation.")
            return pd.Series(50.0, index=df.index)

        close = df['close']
        open_p = df['open']
        high = df['high'] if 'high' in df.columns else close
        low = df['low'] if 'low' in df.columns else close

        # Volume proxy (tick volume or range proxy if volume absent)
        if 'volume' in df.columns and (df['volume'] > 0).any():
            volume = df['volume'].astype(float)
        elif 'tick_volume' in df.columns and (df['tick_volume'] > 0).any():
            volume = df['tick_volume'].astype(float)
        else:
            volume = (high - low) / 0.0001 # Pip range proxy for volume

        # Price change Delta P
        delta_p = close - open_p
        sigma_p = delta_p.rolling(window=window, min_periods=5).std().replace(0, 0.0001).fillna(0.0001)

        # Standardized price change z-score
        z_score = (delta_p / sigma_p).clip(-3.0, 3.0)

        # Bulk Volume Classification (BVC) volume split using normal CDF Phi(z)
        prob_buy = norm.cdf(z_score)
        v_buy = volume * prob_buy
        v_sell = volume * (1.0 - prob_buy)

        v_imbalance = (v_buy - v_sell).abs()

        # Rolling toxicity over window w
        rolling_imbalance = v_imbalance.rolling(window=window, min_periods=5).sum()
        rolling_total_vol = volume.rolling(window=window, min_periods=5).sum().replace(0, 1.0)

        raw_toxicity = rolling_imbalance / rolling_total_vol

        # Rolling Percentile Rank Normalization (0 - 100)
        norm_score = raw_toxicity.rolling(window=250, min_periods=20).apply(
            lambda s: (s.rank(pct=True).iloc[-1] * 100.0) if len(s) > 0 else 50.0,
            raw=False
        ).fillna(50.0)

        return norm_score.rename(f"feat_bvc_toxicity_proxy_{window}h")
