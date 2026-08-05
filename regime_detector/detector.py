import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("RegimeDetector")

# Define Regime constants
REGIME_TRENDING_BULLISH = "TRENDING_BULLISH"
REGIME_TRENDING_BEARISH = "TRENDING_BEARISH"
REGIME_MEAN_REVERSION = "MEAN_REVERSION"
REGIME_CHOP_LOW_VOL = "CHOP_LOW_VOL"
REGIME_CHOP_HIGH_VOL = "CHOP_HIGH_VOL"

class RegimeDetector:
    """
    Classifies the current market environment based on calculated features.
    """
    def __init__(self, adx_threshold: float = 20.0, overbought_rsi: float = 70.0, oversold_rsi: float = 30.0):
        self.adx_threshold = adx_threshold
        self.overbought_rsi = overbought_rsi
        self.oversold_rsi = oversold_rsi

    def detect_regimes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Processes a featured DataFrame and appends a 'regime' column.
        Returns a copy of the DataFrame.
        """
        logger.info("Classifying market regimes...")
        df_out = df.copy()
        
        # Initialize default regime as high-vol chop
        regimes = np.full(len(df_out), REGIME_CHOP_HIGH_VOL, dtype=object)
        
        # Read relevant feature arrays
        close = df_out['close'].values
        # Compute EMAs on the fly to avoid depending on specific builder columns
        ema50 = df_out['close'].ewm(span=50, adjust=False).mean().values
        ema200 = df_out['close'].ewm(span=200, adjust=False).mean().values
        ema50_slope = df_out['feat_trend_ema50_slope'].values
        adx = df_out['feat_trend_adx'].values
        rsi = df_out['feat_osc_rsi'].values
        # Map correctly to FeatureMatrixBuilder column names
        dist_vwap = df_out['feat_struct_dist_vwap'].values if 'feat_struct_dist_vwap' in df_out.columns else np.zeros(len(df_out))
        atr_pct = df_out['feat_vol_atr_pct'].values
        squeeze = df_out['feat_vol_squeeze_ratio'].values if 'feat_vol_squeeze_ratio' in df_out.columns else np.ones(len(df_out))
        
        for i in range(len(df_out)):
            # 1. Check for extreme overextensions (Mean Reversion setup)
            if abs(dist_vwap[i]) > 2.5 or rsi[i] > self.overbought_rsi or rsi[i] < self.oversold_rsi:
                if adx[i] < self.adx_threshold:
                    regimes[i] = REGIME_MEAN_REVERSION
                    continue
                    
            # 2. Check for strong trending regimes
            if adx[i] >= self.adx_threshold:
                if close[i] > ema200[i] and ema50[i] > ema200[i] and ema50_slope[i] > 0.0:
                    regimes[i] = REGIME_TRENDING_BULLISH
                    continue
                elif close[i] < ema200[i] and ema50[i] < ema200[i] and ema50_slope[i] < 0.0:
                    regimes[i] = REGIME_TRENDING_BEARISH
                    continue
                    
            # 3. If not trending, classify consolidation type
            if squeeze[i] < 0.85 or atr_pct[i] < 30.0:
                regimes[i] = REGIME_CHOP_LOW_VOL
            else:
                regimes[i] = REGIME_CHOP_HIGH_VOL
                
        df_out['regime'] = regimes
        return df_out
