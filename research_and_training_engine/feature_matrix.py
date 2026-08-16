"""
Feature Matrix Builder v2
=========================
Computes 70+ features per H1 candle including INTERACTION features.

Categories:
  - Trend (12 features)
  - Volatility (10 features)
  - Price Structure (10 features)
  - Session & Time (8 features)
  - Liquidity (4 features)
  - Momentum Oscillators (6 features)
  - Interaction Features (12+ features)
"""
import pandas as pd
import numpy as np
from core_feature_engineering import features as f
from core_feature_engineering.frac_diff import FractionalDifferentiation


class FeatureMatrixBuilder:
    """
    Builds a dense feature matrix from raw OHLCV data.
    Every feature uses only past data (no lookahead bias).
    """

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes a DataFrame with columns: open, high, low, close, volume
        Returns: same DataFrame with 70+ feat_* columns appended.
        """
        out = df.copy()
        close = out['close']
        high = out['high']
        low = out['low']
        atr = f.calculate_atr(out, 14)
        atr_safe = atr.replace(0, 1e-9)

        # Fractional Differentiation (De Prado)
        out['feat_frac_diff_d04'] = FractionalDifferentiation.frac_diff_fixed_width(close, d=0.40)

        # =================================================================
        # TREND FEATURES (12)
        # =================================================================
        ema20 = f.calculate_ema(out, 20)
        ema50 = f.calculate_ema(out, 50)
        ema200 = f.calculate_ema(out, 200)

        out['feat_trend_ema20_slope'] = f.compute_ema_slope(out, 20)
        out['feat_trend_ema50_slope'] = f.compute_ema_slope(out, 50)
        out['feat_trend_ema200_slope'] = f.compute_ema_slope(out, 200)

        out['feat_trend_dist_ema20'] = (close - ema20) / atr_safe
        out['feat_trend_dist_ema50'] = (close - ema50) / atr_safe
        out['feat_trend_dist_ema200'] = (close - ema200) / atr_safe

        out['feat_trend_ema_stack'] = (
            (ema20 > ema50).astype(int) + (ema50 > ema200).astype(int)
        )

        adx, plus_di, minus_di = f.calculate_adx(out, 14)
        out['feat_trend_adx'] = adx
        out['feat_trend_di_spread'] = plus_di - minus_di

        out['feat_trend_persistence'] = f.compute_trend_persistence(out, 20)

        hh, hl = f.compute_higher_highs_lows(out, 10)
        out['feat_trend_higher_highs'] = hh.rolling(window=20).sum()
        out['feat_trend_higher_lows'] = hl.rolling(window=20).sum()

        # =================================================================
        # VOLATILITY FEATURES (10)
        # =================================================================
        out['feat_vol_atr'] = atr
        out['feat_vol_atr_pct'] = f.compute_atr_percentile(out, 14)
        out['feat_vol_atr_ratio'] = atr / atr.rolling(window=50).mean().replace(0, 1e-9)

        bb_upper, bb_lower, bb_mid, bb_width = f.calculate_bollinger_bands(out, 20)
        out['feat_vol_bb_width'] = bb_width
        out['feat_vol_bb_position'] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, 1e-9)

        out['feat_vol_squeeze_ratio'] = f.compute_volatility_squeeze(out, 20, 100)

        log_returns = np.log(close / close.shift(1))
        out['feat_vol_realized_20'] = log_returns.rolling(window=20).std() * np.sqrt(252 * 24)
        out['feat_vol_realized_5'] = log_returns.rolling(window=5).std() * np.sqrt(252 * 24)

        daily_range = (high - low) / atr_safe
        out['feat_vol_range_ratio'] = daily_range
        out['feat_vol_range_pct'] = daily_range.rolling(window=252).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
            raw=True
        )

        # =================================================================
        # PRICE STRUCTURE FEATURES (10)
        # =================================================================
        out['feat_struct_pullback_depth'] = f.compute_pullback_depth(out, 20)
        out['feat_struct_breakout_strength'] = f.compute_breakout_strength(out, 20)

        sh, sl = f.find_swings(high.values, low.values, window=5)
        out['feat_struct_swing_high'] = sh
        out['feat_struct_swing_low'] = sl

        out['feat_struct_dist_swing_high'] = (close - pd.Series(sh, index=out.index)) / atr_safe
        out['feat_struct_dist_swing_low'] = (close - pd.Series(sl, index=out.index)) / atr_safe

        pb_d, bo_d = f.compute_pullback_features(high.values, low.values, close.values, sh, sl)
        out['feat_struct_swing_pullback'] = pb_d
        out['feat_struct_swing_breakout'] = pd.Series(bo_d, index=out.index) / atr_safe

        dc_upper = high.rolling(window=20).max()
        dc_lower = low.rolling(window=20).min()
        dc_range = (dc_upper - dc_lower).replace(0, 1e-9)
        out['feat_struct_dc_position'] = (close - dc_lower) / dc_range

        typical = (high + low + close) / 3.0
        vwap = typical.rolling(window=20).mean()
        out['feat_struct_dist_vwap'] = (close - vwap) / atr_safe

        # =================================================================
        # SESSION & TIME FEATURES (8)
        # =================================================================
        hours = out.index.hour
        out['feat_time_hour_sin'] = np.sin(2 * np.pi * hours / 24)
        out['feat_time_hour_cos'] = np.cos(2 * np.pi * hours / 24)

        dow = out.index.dayofweek
        out['feat_time_dow_sin'] = np.sin(2 * np.pi * dow / 5)
        out['feat_time_dow_cos'] = np.cos(2 * np.pi * dow / 5)

        out['feat_time_month'] = out.index.month

        lon, ny = f.compute_session_flags(out)
        out['feat_session_london'] = lon
        out['feat_session_ny_overlap'] = ny
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

        body = (close - out['open']).abs()
        full_range = (high - low).replace(0, 1e-9)
        out['feat_liq_body_ratio'] = body / full_range

        # =================================================================
        # MOMENTUM OSCILLATORS (6)
        # =================================================================
        out['feat_osc_rsi'] = f.calculate_rsi(out, 14)
        out['feat_osc_rsi_5'] = f.calculate_rsi(out, 5)
        out['feat_osc_roc_5'] = close.pct_change(5) * 100
        out['feat_osc_roc_12'] = close.pct_change(12) * 100
        out['feat_osc_roc_24'] = close.pct_change(24) * 100
        out['feat_osc_momentum_5'] = (close / close.shift(5) - 1) * 100

        # =================================================================
        # INTERACTION FEATURES (12) — The edge comes from combinations
        # =================================================================
        out['feat_ix_atr_x_ema50_slope'] = out['feat_vol_atr_pct'] * out['feat_trend_ema50_slope']
        out['feat_ix_atr_x_ema200_slope'] = out['feat_vol_atr_pct'] * out['feat_trend_ema200_slope']
        out['feat_ix_dist_ema200_x_atr_pct'] = out['feat_trend_dist_ema200'] * out['feat_vol_atr_pct']
        out['feat_ix_dist_ema50_x_atr_pct'] = out['feat_trend_dist_ema50'] * out['feat_vol_atr_pct']
        out['feat_ix_swing_dist_x_vol'] = out['feat_struct_dist_swing_low'] * out['feat_vol_realized_20']
        out['feat_ix_pullback_x_adx'] = out['feat_struct_swing_pullback'] * out['feat_trend_adx']
        out['feat_ix_breakout_x_squeeze'] = out['feat_struct_breakout_strength'] * out['feat_vol_squeeze_ratio']
        out['feat_ix_rsi_x_atr_ratio'] = out['feat_osc_rsi'] * out['feat_vol_atr_ratio']
        out['feat_ix_persistence_x_vol'] = out['feat_trend_persistence'] * out['feat_vol_realized_20']
        out['feat_ix_hh_x_vol'] = out['feat_trend_higher_highs'] * out['feat_vol_atr_pct']
        out['feat_ix_bb_pos_x_squeeze'] = out['feat_vol_bb_position'] * out['feat_vol_squeeze_ratio']
        out['feat_ix_adx_x_di_spread'] = out['feat_trend_adx'] * out['feat_trend_di_spread']

        return out

    def get_feature_columns(self, df: pd.DataFrame) -> list:
        """Returns list of all feat_* columns, excluding raw swing prices."""
        exclude = {'feat_struct_swing_high', 'feat_struct_swing_low', 'feat_time_month'}
        return [c for c in df.columns if c.startswith('feat_') and c not in exclude]
