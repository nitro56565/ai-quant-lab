"""
Feature Matrix Builder
======================
Computes 50+ features per H1 candle for quantitative research.
No strategy logic. Pure feature engineering.

Categories:
  - Trend (12 features)
  - Volatility (10 features)
  - Price Structure (10 features)
  - Session & Time (8 features)
  - Liquidity (4 features)
  - Momentum Oscillators (6 features)
"""
import pandas as pd
import numpy as np
from feature_engine import features as f


class FeatureMatrixBuilder:
    """
    Builds a dense feature matrix from raw OHLCV data.
    Every feature is computed using only past data (no lookahead bias).
    """

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes a DataFrame with columns: open, high, low, close, volume
        Returns: same DataFrame with 50+ feat_* columns appended.
        """
        out = df.copy()
        close = out['close']
        high = out['high']
        low = out['low']
        atr = f.calculate_atr(out, 14)
        atr_safe = atr.replace(0, 1e-9)

        # =================================================================
        # TREND FEATURES (12)
        # =================================================================
        ema20 = f.calculate_ema(out, 20)
        ema50 = f.calculate_ema(out, 50)
        ema200 = f.calculate_ema(out, 200)

        out['feat_trend_ema20_slope'] = f.compute_ema_slope(out, 20)
        out['feat_trend_ema50_slope'] = f.compute_ema_slope(out, 50)
        out['feat_trend_ema200_slope'] = f.compute_ema_slope(out, 200)

        # Distance from EMAs (ATR-normalized)
        out['feat_trend_dist_ema20'] = (close - ema20) / atr_safe
        out['feat_trend_dist_ema50'] = (close - ema50) / atr_safe
        out['feat_trend_dist_ema200'] = (close - ema200) / atr_safe

        # EMA alignment (bullish stack: 20 > 50 > 200)
        out['feat_trend_ema_stack'] = (
            (ema20 > ema50).astype(int) + (ema50 > ema200).astype(int)
        )

        # ADX and DI spread
        adx, plus_di, minus_di = f.calculate_adx(out, 14)
        out['feat_trend_adx'] = adx
        out['feat_trend_di_spread'] = plus_di - minus_di

        # Trend persistence (Kaufman Efficiency Ratio)
        out['feat_trend_persistence'] = f.compute_trend_persistence(out, 20)

        # Higher highs / higher lows count over rolling window
        hh, hl = f.compute_higher_highs_lows(out, 10)
        out['feat_trend_higher_highs'] = hh.rolling(window=20).sum()
        out['feat_trend_higher_lows'] = hl.rolling(window=20).sum()

        # =================================================================
        # VOLATILITY FEATURES (10)
        # =================================================================
        out['feat_vol_atr'] = atr
        out['feat_vol_atr_pct'] = f.compute_atr_percentile(out, 14)
        out['feat_vol_atr_ratio'] = atr / atr.rolling(window=50).mean().replace(0, 1e-9)

        # Bollinger Bands
        bb_upper, bb_lower, bb_mid, bb_width = f.calculate_bollinger_bands(out, 20)
        out['feat_vol_bb_width'] = bb_width
        out['feat_vol_bb_position'] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, 1e-9)

        # Volatility squeeze
        out['feat_vol_squeeze_ratio'] = f.compute_volatility_squeeze(out, 20, 100)

        # Realized volatility (std of log returns, annualized)
        log_returns = np.log(close / close.shift(1))
        out['feat_vol_realized_20'] = log_returns.rolling(window=20).std() * np.sqrt(252 * 24)
        out['feat_vol_realized_5'] = log_returns.rolling(window=5).std() * np.sqrt(252 * 24)

        # Daily range percentile
        daily_range = (high - low) / atr_safe
        out['feat_vol_range_ratio'] = daily_range
        out['feat_vol_range_pct'] = daily_range.rolling(window=252).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
            raw=True
        )

        # =================================================================
        # PRICE STRUCTURE FEATURES (10)
        # =================================================================
        # Pullback depth (rolling)
        out['feat_struct_pullback_depth'] = f.compute_pullback_depth(out, 20)
        out['feat_struct_breakout_strength'] = f.compute_breakout_strength(out, 20)

        # Swing-based features
        sh, sl = f.find_swings(high.values, low.values, window=5)
        out['feat_struct_swing_high'] = sh
        out['feat_struct_swing_low'] = sl

        # Distance to swing levels (ATR-normalized)
        out['feat_struct_dist_swing_high'] = (close - pd.Series(sh, index=out.index)) / atr_safe
        out['feat_struct_dist_swing_low'] = (close - pd.Series(sl, index=out.index)) / atr_safe

        # Swing-based pullback depth
        pb_d, bo_d = f.compute_pullback_features(high.values, low.values, close.values, sh, sl)
        out['feat_struct_swing_pullback'] = pb_d
        out['feat_struct_swing_breakout'] = pd.Series(bo_d, index=out.index) / atr_safe

        # Donchian channel position
        dc_upper = high.rolling(window=20).max()
        dc_lower = low.rolling(window=20).min()
        dc_range = (dc_upper - dc_lower).replace(0, 1e-9)
        out['feat_struct_dc_position'] = (close - dc_lower) / dc_range

        # Distance from VWAP proxy
        typical = (high + low + close) / 3.0
        vwap = typical.rolling(window=20).mean()
        out['feat_struct_dist_vwap'] = (close - vwap) / atr_safe

        # =================================================================
        # SESSION & TIME FEATURES (8)
        # =================================================================
        hours = out.index.hour
        out['feat_time_hour'] = hours
        out['feat_time_hour_sin'] = np.sin(2 * np.pi * hours / 24)
        out['feat_time_hour_cos'] = np.cos(2 * np.pi * hours / 24)

        dow = out.index.dayofweek
        out['feat_time_dow'] = dow
        out['feat_time_dow_sin'] = np.sin(2 * np.pi * dow / 5)
        out['feat_time_dow_cos'] = np.cos(2 * np.pi * dow / 5)

        out['feat_time_month'] = out.index.month

        # Session flags
        lon, ny = f.compute_session_flags(out)
        out['feat_session_london'] = lon
        out['feat_session_ny_overlap'] = ny

        # Minutes since London open (08:00 UTC)
        out['feat_session_minutes_since_london'] = np.clip((hours - 8) * 60, 0, None)

        # =================================================================
        # LIQUIDITY FEATURES (4)
        # =================================================================
        out['feat_liq_tick_density'] = f.compute_tick_density(out, 20)

        if 'volume' in out.columns:
            vol = out['volume']
            vol_sma = vol.rolling(window=20).mean().replace(0, 1e-9)
            out['feat_liq_volume_ratio'] = vol / vol_sma
            out['feat_liq_volume_pct'] = vol.rolling(window=252).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
                raw=True
            )
        else:
            out['feat_liq_volume_ratio'] = 1.0
            out['feat_liq_volume_pct'] = 50.0

        # Candle body ratio (measure of conviction)
        body = (close - out['open']).abs()
        full_range = (high - low).replace(0, 1e-9)
        out['feat_liq_body_ratio'] = body / full_range

        # =================================================================
        # MOMENTUM OSCILLATORS (6)
        # =================================================================
        out['feat_osc_rsi'] = f.calculate_rsi(out, 14)
        out['feat_osc_rsi_5'] = f.calculate_rsi(out, 5)

        # Rate of change (multiple periods)
        out['feat_osc_roc_5'] = close.pct_change(5) * 100
        out['feat_osc_roc_12'] = close.pct_change(12) * 100
        out['feat_osc_roc_24'] = close.pct_change(24) * 100

        # Cumulative return over last 5 bars (momentum)
        out['feat_osc_momentum_5'] = (close / close.shift(5) - 1) * 100

        # =================================================================
        # COMPOSITE / TREND SCORE (1)
        # =================================================================
        sh_series = pd.Series(sh, index=out.index)
        sl_series = pd.Series(sl, index=out.index)
        sh_prev = sh_series.where(sh_series.diff() != 0).ffill()
        sl_prev = sl_series.where(sl_series.diff() != 0).ffill()

        score = pd.Series(0.0, index=out.index)
        score += (out['feat_trend_ema200_slope'] > 0).astype(int) * 20
        score += (sh_series > sh_prev.shift(1)).astype(int) * 20
        score += (sl_series > sl_prev.shift(1)).astype(int) * 20
        score += ((out['feat_vol_atr_pct'] >= 40) & (out['feat_vol_atr_pct'] <= 85)).astype(int) * 20
        score += (dc_upper > dc_upper.shift(5)).astype(int) * 20
        out['feat_trend_score'] = score

        return out

    def get_feature_columns(self, df: pd.DataFrame) -> list:
        """Returns list of all feat_* column names."""
        return [c for c in df.columns if c.startswith('feat_')]
