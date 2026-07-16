import pandas as pd
import numpy as np
import logging
from data_loader import DataLoader, DataRequest
from . import features as f

logger = logging.getLogger("FeatureEngine")

class FeatureEngine:
    """
    Orchestrates multi-timeframe data loading, indicator calculation,
    lookahead bias shifting, and alignment to the primary execution timeframe.
    """
    def __init__(self):
        pass

    def generate_features(self, loader: DataLoader, symbol: str, start_date: str, end_date: str, 
                          primary_timeframe: str = "1h") -> pd.DataFrame:
        """
        Loads all required historical timeframes (M15, H1, H4), calculates features,
        applies timezone-safe indices, shifts higher timeframes by 1 bar to prevent
        lookahead bias, and aligns them to the primary timeframe.
        """
        logger.info(f"Generating features for {symbol} on primary timeframe '{primary_timeframe}'...")
        
        start_dt = pd.to_datetime(start_date)
        # Load 60 days of warmup data to compute indicators properly
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        if primary_timeframe == "15m":
            # London Session Momentum primary timeframe (M15)
            req_h4 = DataRequest(symbol=symbol, timeframe="4h", start=warmup_start, end=end_date)
            req_h1 = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
            req_m15 = DataRequest(symbol=symbol, timeframe="15m", start=warmup_start, end=end_date)
            
            df_h4 = loader.load(req_h4)
            df_h1 = loader.load(req_h1)
            df_m15 = loader.load(req_m15)
            
            # --- 1. Compute H4 features ---
            h4_feats = pd.DataFrame(index=df_h4.index)
            h4_feats['feat_trend_ema50_h4'] = f.calculate_ema(df_h4, 50)
            h4_feats['feat_trend_ema200_h4'] = f.calculate_ema(df_h4, 200)
            h4_feats['feat_trend_adx_h4'], _, _ = f.calculate_adx(df_h4, 14)
            
            h4_feats_shifted = h4_feats.shift(1)
            
            # --- 2. Compute H1 features ---
            h1_feats = pd.DataFrame(index=df_h1.index)
            h1_feats['feat_trend_ema50_h1'] = f.calculate_ema(df_h1, 50)
            h1_feats['feat_trend_ema200_h1'] = f.calculate_ema(df_h1, 200)
            
            h1_feats_shifted = h1_feats.shift(1)
            
            # --- 3. Compute M15 features (Primary Execution) ---
            df_out = df_m15.copy()
            df_out['feat_vol_atr'] = f.calculate_atr(df_out, 14)
            df_out['feat_vol_atr_sma'] = df_out['feat_vol_atr'].rolling(window=20).mean()
            
            # Standard trend indicators on primary (M15) for Regime Detector
            df_out['feat_trend_ema50'] = f.calculate_ema(df_out, 50)
            df_out['feat_trend_ema200'] = f.calculate_ema(df_out, 200)
            df_out['feat_trend_ema50_slope'] = f.compute_ema_slope(df_out, 50)
            df_out['feat_trend_adx'], _, _ = f.calculate_adx(df_out, 14)
            df_out['feat_osc_rsi'] = f.calculate_rsi(df_out, 14)
            
            # Bollinger Bands on M15
            upper, lower, mid, width = f.calculate_bollinger_bands(df_out, 20)
            df_out['feat_vol_bb_upper'] = upper
            df_out['feat_vol_bb_lower'] = lower
            df_out['feat_vol_bb_mid'] = mid
            df_out['feat_vol_bb_width'] = width
            df_out['feat_vol_bb_width_sma50'] = df_out['feat_vol_bb_width'].rolling(window=50).mean()
            df_out['feat_vol_squeeze'] = df_out['feat_vol_bb_width'] < df_out['feat_vol_bb_width_sma50']
            df_out['feat_vol_atr_pct'] = f.compute_atr_percentile(df_out, 14)
            
            # Donchian Upper Channel on M15
            df_out['feat_price_channel_upper'] = df_out['high'].rolling(window=20).max()
            df_out['feat_price_channel_lower'] = df_out['low'].rolling(window=20).min()
            
            # Distance from VWAP proxy
            typical_price = (df_out['high'] + df_out['low'] + df_out['close']) / 3.0
            df_out['feat_price_vwap'] = typical_price.rolling(window=20).mean()
            df_out['feat_price_dist_vwap'] = (df_out['close'] - df_out['feat_price_vwap']) / df_out['feat_vol_atr'].replace(0, 1e-9)
            
            # Session Timing Flags
            df_out['feat_session_london_open'] = ((df_out.index.hour >= 8) & (df_out.index.hour <= 10)).astype(int)
            
            # Breakout Strength
            donchian_upper_shifted = df_out['feat_price_channel_upper'].shift(1)
            df_out['feat_price_breakout_strength'] = (df_out['close'] - donchian_upper_shifted) / df_out['feat_vol_atr'].replace(0, 1e-9)
            
            # Swings and pullback features on M15
            sh, sl = f.find_swings(df_out['high'].values, df_out['low'].values, window=5)
            df_out['feat_price_swing_high'] = sh
            df_out['feat_price_swing_low'] = sl
            
            pullback_d, breakout_d = f.compute_pullback_features(
                df_out['high'].values, df_out['low'].values, df_out['close'].values, sh, sl
            )
            df_out['feat_price_pullback_depth'] = pullback_d
            df_out['feat_price_breakout_distance'] = breakout_d
            df_out['feat_trend_ema200_slope'] = f.compute_ema_slope(df_out, 200)
            
            sh_series = pd.Series(sh, index=df_out.index)
            sh_changed = sh_series.diff() != 0
            sh_prev = sh_series.where(sh_changed).ffill()
            
            sl_series = pd.Series(sl, index=df_out.index)
            sl_changed = sl_series.diff() != 0
            sl_prev = sl_series.where(sl_changed).ffill()
            
            slope_score = (df_out['feat_trend_ema200_slope'] > 0).astype(int) * 20
            hh_score = (sh_series > sh_prev.shift(1)).astype(int) * 20
            hl_score = (sl_series > sl_prev.shift(1)).astype(int) * 20
            vol_score = ((df_out['feat_vol_atr_pct'] >= 40) & (df_out['feat_vol_atr_pct'] <= 85)).astype(int) * 20
            
            dc_upper = df_out['feat_price_channel_upper']
            dc_expansion = (dc_upper > dc_upper.shift(5)).astype(int) * 20
            
            df_out['feat_trend_score'] = slope_score + hh_score + hl_score + vol_score + dc_expansion
            
            # --- 4. Reindex and merge ---
            h4_aligned = h4_feats_shifted.reindex(df_out.index, method='ffill')
            h1_aligned = h1_feats_shifted.reindex(df_out.index, method='ffill')
            
            df_out = pd.concat([df_out, h1_aligned, h4_aligned], axis=1)
            
        else:
            # H1 strategies (AdaptiveTrend, PullbackContinuation, MeanReversion, VolatilityBreakout)
            req_h4 = DataRequest(symbol=symbol, timeframe="4h", start=warmup_start, end=end_date)
            req_h1 = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
            
            df_h4 = loader.load(req_h4)
            df_h1 = loader.load(req_h1)
            
            # --- 1. Compute H4 features ---
            h4_feats = pd.DataFrame(index=df_h4.index)
            h4_feats['feat_trend_ema50_h4'] = f.calculate_ema(df_h4, 50)
            h4_feats['feat_trend_ema200_h4'] = f.calculate_ema(df_h4, 200)
            h4_feats['feat_trend_adx_h4'], _, _ = f.calculate_adx(df_h4, 14)
            
            h4_feats_shifted = h4_feats.shift(1)
            
            # --- 2. Compute H1 features (Primary Execution) ---
            df_out = df_h1.copy()
            df_out['feat_vol_atr'] = f.calculate_atr(df_out, 14)
            df_out['feat_vol_atr_sma'] = df_out['feat_vol_atr'].rolling(window=20).mean()
            df_out['feat_vol_atr_sma5'] = df_out['feat_vol_atr'].rolling(window=5).mean()
            
            df_out['feat_trend_ema20'] = f.calculate_ema(df_out, 20)
            df_out['feat_trend_ema50'] = f.calculate_ema(df_out, 50)
            df_out['feat_trend_ema200'] = f.calculate_ema(df_out, 200)
            df_out['feat_trend_ema50_slope'] = f.compute_ema_slope(df_out, 50)
            df_out['feat_trend_adx'], _, _ = f.calculate_adx(df_out, 14)
            df_out['feat_osc_rsi'] = f.calculate_rsi(df_out, 14)
            
            # Bollinger Bands
            upper, lower, mid, width = f.calculate_bollinger_bands(df_out, 20)
            df_out['feat_vol_bb_upper'] = upper
            df_out['feat_vol_bb_lower'] = lower
            df_out['feat_vol_bb_mid'] = mid
            df_out['feat_vol_bb_width'] = width
            df_out['feat_vol_bb_width_sma50'] = df_out['feat_vol_bb_width'].rolling(window=50).mean()
            df_out['feat_vol_squeeze'] = df_out['feat_vol_bb_width'] < df_out['feat_vol_bb_width_sma50']
            
            # Donchian Channels
            df_out['feat_price_channel_upper'] = df_out['high'].rolling(window=20).max()
            df_out['feat_price_channel_lower'] = df_out['low'].rolling(window=20).min()
            
            # Breakout Strength
            donchian_upper_shifted = df_out['feat_price_channel_upper'].shift(1)
            df_out['feat_price_breakout_strength'] = (df_out['close'] - donchian_upper_shifted) / df_out['feat_vol_atr'].replace(0, 1e-9)
            
            # Volatility ranking
            df_out['feat_vol_atr_pct'] = f.compute_atr_percentile(df_out, 14)
            
            # Distance from VWAP proxy
            typical_price = (df_out['high'] + df_out['low'] + df_out['close']) / 3.0
            df_out['feat_price_vwap'] = typical_price.rolling(window=20).mean()
            df_out['feat_price_dist_vwap'] = (df_out['close'] - df_out['feat_price_vwap']) / df_out['feat_vol_atr'].replace(0, 1e-9)
            
            # Session flags
            lon, ny = f.compute_session_flags(df_out)
            df_out['feat_session_london_open'] = lon
            df_out['feat_session_ny_overlap'] = ny
            
            # Swings and pullback features on H1
            sh, sl = f.find_swings(df_out['high'].values, df_out['low'].values, window=5)
            df_out['feat_price_swing_high'] = sh
            df_out['feat_price_swing_low'] = sl
            
            pullback_d, breakout_d = f.compute_pullback_features(
                df_out['high'].values, df_out['low'].values, df_out['close'].values, sh, sl
            )
            df_out['feat_price_pullback_depth'] = pullback_d
            df_out['feat_price_breakout_distance'] = breakout_d
            df_out['feat_trend_ema200_slope'] = f.compute_ema_slope(df_out, 200)
            
            sh_series = pd.Series(sh, index=df_out.index)
            sh_changed = sh_series.diff() != 0
            sh_prev = sh_series.where(sh_changed).ffill()
            
            sl_series = pd.Series(sl, index=df_out.index)
            sl_changed = sl_series.diff() != 0
            sl_prev = sl_series.where(sl_changed).ffill()
            
            slope_score = (df_out['feat_trend_ema200_slope'] > 0).astype(int) * 20
            hh_score = (sh_series > sh_prev.shift(1)).astype(int) * 20
            hl_score = (sl_series > sl_prev.shift(1)).astype(int) * 20
            vol_score = ((df_out['feat_vol_atr_pct'] >= 40) & (df_out['feat_vol_atr_pct'] <= 85)).astype(int) * 20
            
            dc_upper = df_out['feat_price_channel_upper']
            dc_expansion = (dc_upper > dc_upper.shift(5)).astype(int) * 20
            
            df_out['feat_trend_score'] = slope_score + hh_score + hl_score + vol_score + dc_expansion
            
            # --- 3. Reindex and merge ---
            h4_aligned = h4_feats_shifted.reindex(df_out.index, method='ffill')
            df_out = pd.concat([df_out, h4_aligned], axis=1)
            
        # Backfill initial warmup values
        df_out = df_out.bfill()
        
        return df_out
