"""
Future Labeler v2
=================
Redesigned to ask the RIGHT prediction problems:

  Model A: Predict MFE (regression) — "How many pips of favorable move?"
  Model B: Predict future volatility regime — "Will volatility expand?"
  Model C: Predict trade quality — "Is this a high-quality setup?"

Labels use future data BY DESIGN. They are training targets only.
They must NEVER be used as features.
"""
import pandas as pd
import numpy as np


class FutureLabeler:
    """
    Labels each candle with multiple prediction targets.
    """

    def __init__(self, horizon: int = 12, quality_threshold_atr: float = 2.0):
        """
        Args:
            horizon: Number of future bars to look forward.
            quality_threshold_atr: MFE in ATR multiples to qualify as "high quality".
        """
        self.horizon = horizon
        self.quality_threshold = quality_threshold_atr

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes multiple forward-looking targets per bar.

        Requires: close, high, low, feat_vol_atr

        Returns DataFrame with columns:
          REGRESSION TARGETS:
          - label_mfe_long_pips:  Max favorable excursion (long) in pips
          - label_mfe_short_pips: Max favorable excursion (short) in pips
          - label_mfe_best_pips:  Max of long/short MFE (direction-agnostic)
          - label_mae_pips:       Max adverse excursion (worst direction) in pips
          - label_return_12h:     Net return after horizon bars in pips
          - label_future_atr:     Average ATR of the next horizon bars

          ATR-NORMALIZED:
          - label_mfe_best_atr:   Best MFE in ATR multiples
          - label_future_vol_change: Future ATR / Current ATR ratio

          CLASSIFICATION TARGETS:
          - label_vol_regime:     HIGH / MEDIUM / LOW (future volatility)
          - label_trade_quality:  HIGH / LOW (is this a good setup?)
        """
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        atr = df['feat_vol_atr'].values
        n = len(df)
        h = self.horizon
        pip_size = 0.0001

        # Pre-allocate
        mfe_long = np.full(n, np.nan)
        mfe_short = np.full(n, np.nan)
        mae_long = np.full(n, np.nan)
        mae_short = np.full(n, np.nan)
        ret_12h = np.full(n, np.nan)
        future_atr_avg = np.full(n, np.nan)

        for i in range(n - h):
            entry = close[i]
            fh = high[i + 1: i + 1 + h]
            fl = low[i + 1: i + 1 + h]
            fc = close[i + h]

            # Long perspective
            mfe_long[i] = (np.max(fh) - entry) / pip_size
            mae_long[i] = (entry - np.min(fl)) / pip_size

            # Short perspective
            mfe_short[i] = (entry - np.min(fl)) / pip_size
            mae_short[i] = (np.max(fh) - entry) / pip_size

            # Net return
            ret_12h[i] = (fc - entry) / pip_size

            # Future volatility
            future_atr_avg[i] = np.mean(atr[i + 1: i + 1 + h])

        out = df.copy()

        # --- REGRESSION TARGETS ---
        out['label_mfe_long_pips'] = mfe_long
        out['label_mfe_short_pips'] = mfe_short
        out['label_mfe_best_pips'] = np.maximum(mfe_long, mfe_short)
        out['label_mae_pips'] = np.minimum(mae_long, mae_short)  # Worst case
        out['label_return_12h'] = ret_12h
        out['label_future_atr'] = future_atr_avg

        # --- ATR-NORMALIZED ---
        atr_pips = atr / pip_size
        atr_pips_safe = np.where(atr_pips > 0, atr_pips, 1.0)

        out['label_mfe_best_atr'] = np.maximum(mfe_long, mfe_short) / atr_pips_safe
        out['label_mfe_long_atr'] = mfe_long / atr_pips_safe
        out['label_mfe_short_atr'] = mfe_short / atr_pips_safe

        # Future vol change ratio
        out['label_future_vol_change'] = future_atr_avg / np.where(atr > 0, atr, 1e-9)

        # --- CLASSIFICATION: Volatility Regime ---
        vol_change = out['label_future_vol_change'].values
        vol_labels = np.full(n, 'MEDIUM', dtype=object)
        for i in range(n):
            if np.isnan(vol_change[i]):
                vol_labels[i] = np.nan
            elif vol_change[i] > 1.15:
                vol_labels[i] = 'HIGH'
            elif vol_change[i] < 0.85:
                vol_labels[i] = 'LOW'
        out['label_vol_regime'] = vol_labels

        # --- CLASSIFICATION: Trade Quality ---
        # HIGH = the BETTER direction has MFE >= threshold ATR AND R:R >= 2.0
        # We check each direction independently, then pick the better one
        mfe_long_atr = mfe_long / atr_pips_safe
        mfe_short_atr = mfe_short / atr_pips_safe
        mae_long_safe = np.where(mae_long > 0, mae_long, 1.0)
        mae_short_safe = np.where(mae_short > 0, mae_short, 1.0)

        long_rr = mfe_long / mae_long_safe
        short_rr = mfe_short / mae_short_safe

        quality_labels = np.full(n, 'LOW', dtype=object)
        for i in range(n):
            if np.isnan(mfe_long_atr[i]):
                quality_labels[i] = np.nan
                continue
            # Check long direction
            long_ok = (mfe_long_atr[i] >= self.quality_threshold) and (long_rr[i] >= 2.0)
            # Check short direction
            short_ok = (mfe_short_atr[i] >= self.quality_threshold) and (short_rr[i] >= 2.0)
            if long_ok or short_ok:
                quality_labels[i] = 'HIGH'

        out['label_trade_quality'] = quality_labels

        return out

    def get_label_stats(self, df: pd.DataFrame) -> dict:
        """Returns distribution statistics for all label types."""
        valid = df.dropna(subset=['label_mfe_best_pips'])
        n = len(valid)

        quality_counts = valid['label_trade_quality'].value_counts()
        vol_counts = valid['label_vol_regime'].value_counts()

        return {
            'total_bars': n,
            # Quality
            'quality_HIGH': int(quality_counts.get('HIGH', 0)),
            'quality_LOW': int(quality_counts.get('LOW', 0)),
            'quality_HIGH_pct': round(quality_counts.get('HIGH', 0) / n * 100, 1) if n > 0 else 0,
            # Volatility
            'vol_HIGH': int(vol_counts.get('HIGH', 0)),
            'vol_MEDIUM': int(vol_counts.get('MEDIUM', 0)),
            'vol_LOW': int(vol_counts.get('LOW', 0)),
            # Regression stats
            'mfe_mean': round(valid['label_mfe_best_pips'].mean(), 1),
            'mfe_median': round(valid['label_mfe_best_pips'].median(), 1),
            'mfe_p90': round(valid['label_mfe_best_pips'].quantile(0.9), 1),
            'return_mean': round(valid['label_return_12h'].mean(), 1),
        }
