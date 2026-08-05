import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from ai_engine.regime_hmm import HMMRegimeDetector

class MetaRegimeEngine:
    """
    Meta Regime Engine:
    Combines Gaussian HMM posteriors with continuous Trend Strength (ADX),
    Relative Volatility Ratio (ATR / ATR_sma200), Session Flags, and Liquidity features.
    Outputs continuous soft probabilities for 4 meta-regimes:
    - Bull Trend Prob
    - Bear Trend Prob
    - Range Chop Prob
    - Volatility Expansion Prob
    """
    def __init__(self, n_hmm_components: int = 3, random_state: int = 42) -> None:
        self.hmm_detector = HMMRegimeDetector(n_components=n_hmm_components, random_state=random_state)
        self.is_fitted = False

    def fit(self, df_train: pd.DataFrame) -> "MetaRegimeEngine":
        self.hmm_detector.fit(df_train)
        self.is_fitted = True
        return self

    def predict_regime_probabilities(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates soft probabilities for 4 meta-regimes per candle.
        """
        if not self.is_fitted:
            raise RuntimeError("MetaRegimeEngine must be fitted before predict_regime_probabilities().")

        hmm_probs = self.hmm_detector.predict_proba(df)  # (N, 3)
        
        adx = df['feat_trend_adx'].values if 'feat_trend_adx' in df.columns else np.full(len(df), 25.0)
        ema_slope = df['feat_trend_ema50_slope'].values if 'feat_trend_ema50_slope' in df.columns else np.zeros(len(df))
        atr = df['feat_vol_atr'].values if 'feat_vol_atr' in df.columns else np.full(len(df), 0.0020)
        atr_sma = pd.Series(atr).rolling(200, min_periods=1).mean().values
        vol_ratio = atr / np.maximum(atr_sma, 1e-6)

        # Soft logistic weights
        trend_weight = 1.0 / (1.0 + np.exp(-(adx - 20.0) / 5.0))  # Smooth sigmoid around ADX=20
        vol_expansion_weight = 1.0 / (1.0 + np.exp(-(vol_ratio - 1.2) / 0.2))

        bull_mask = (ema_slope > 0).astype(float)
        bear_mask = (ema_slope < 0).astype(float)

        prob_bull = trend_weight * bull_mask * (0.5 + 0.5 * hmm_probs[:, 1])
        prob_bear = trend_weight * bear_mask * (0.5 + 0.5 * hmm_probs[:, 2])
        prob_vol_exp = vol_expansion_weight * (0.5 + 0.5 * hmm_probs[:, 2])
        prob_range = (1.0 - trend_weight) * (0.5 + 0.5 * hmm_probs[:, 0])

        # Normalize to probability simplex
        sum_probs = prob_bull + prob_bear + prob_vol_exp + prob_range + 1e-9
        prob_bull /= sum_probs
        prob_bear /= sum_probs
        prob_vol_exp /= sum_probs
        prob_range /= sum_probs

        out = df.copy()
        out['meta_prob_bull_trend'] = prob_bull
        out['meta_prob_bear_trend'] = prob_bear
        out['meta_prob_range_chop'] = prob_range
        out['meta_prob_vol_expansion'] = prob_vol_exp

        return out
