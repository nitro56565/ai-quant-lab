"""
Future Labeler v3 — López de Prado Triple-Barrier Dynamic Labeling Engine
========================================================================

Implements path-dependent Triple Barrier labeling:
  1. Upper Barrier: +2.5 * ATR_14 (Take Profit Touch -> +1)
  2. Lower Barrier: -1.5 * ATR_14 (Stop Loss Touch -> -1)
  3. Vertical Barrier: Max 24 hours (Expiration -> 0)
"""
import pandas as pd
import numpy as np

class TripleBarrierLabeler:
    """
    Computes path-dependent Triple Barrier labels using ATR-based upper/lower price barriers
    and a vertical expiration horizon.
    """
    def __init__(self, tp_atr_mult: float = 2.5, sl_atr_mult: float = 1.5, max_holding_bars: int = 24):
        self.tp_mult = tp_atr_mult
        self.sl_mult = sl_atr_mult
        self.max_h = max_holding_bars

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        n = len(df)
        pip_size = 0.0001

        # Compute ATR 14
        if 'feat_vol_atr' in df.columns:
            atr = df['feat_vol_atr'].values
        else:
            tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
            atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values

        tb_target_long = np.zeros(n, dtype=int)
        tb_target_short = np.zeros(n, dtype=int)

        mfe_long_pips = np.zeros(n)
        mfe_short_pips = np.zeros(n)
        mae_long_pips = np.zeros(n)
        mae_short_pips = np.zeros(n)
        ret_12h_pips = np.zeros(n)

        for i in range(n - self.max_h):
            entry_p = close[i]
            curr_atr = atr[i]
            if curr_atr <= 0:
                continue

            fh = high[i + 1: i + 1 + self.max_h]
            fl = low[i + 1: i + 1 + self.max_h]
            fc = close[i + min(12, self.max_h)]

            mfe_long_pips[i] = (np.max(fh) - entry_p) / pip_size
            mae_long_pips[i] = (entry_p - np.min(fl)) / pip_size
            mfe_short_pips[i] = (entry_p - np.min(fl)) / pip_size
            mae_short_pips[i] = (np.max(fh) - entry_p) / pip_size
            ret_12h_pips[i] = (fc - entry_p) / pip_size

            # Long Perspective Barriers
            tp_long = entry_p + (self.tp_mult * curr_atr)
            sl_long = entry_p - (self.sl_mult * curr_atr)

            for h in range(1, self.max_h + 1):
                c_h = high[i + h]
                c_l = low[i + h]

                if c_l <= sl_long:
                    tb_target_long[i] = -1
                    break
                elif c_h >= tp_long:
                    tb_target_long[i] = 1
                    break

            # Short Perspective Barriers
            tp_short = entry_p - (self.tp_mult * curr_atr)
            sl_short = entry_p + (self.sl_mult * curr_atr)

            for h in range(1, self.max_h + 1):
                c_h = high[i + h]
                c_l = low[i + h]

                if c_h >= sl_short:
                    tb_target_short[i] = -1
                    break
                elif c_l <= tp_short:
                    tb_target_short[i] = 1
                    break

        out = df.copy()
        out['label_tb_target_long'] = tb_target_long
        out['label_tb_target_short'] = tb_target_short
        out['label_mfe_long_pips'] = mfe_long_pips
        out['label_mfe_short_pips'] = mfe_short_pips
        out['label_mae_long_pips'] = mae_long_pips
        out['label_mae_short_pips'] = mae_short_pips
        out['label_mae_pips'] = np.minimum(mae_long_pips, mae_short_pips)
        out['label_return_12h'] = ret_12h_pips
        out['label_mfe_best_atr'] = np.maximum(mfe_long_pips, mfe_short_pips) / np.where(atr > 0, atr / pip_size, 1.0)
        out['label_trade_quality'] = np.where(tb_target_long == 1, 'HIGH', 'LOW')
        out['label_target_long'] = np.where(tb_target_long == 1, 1, 0)
        out['label_target_short'] = np.where(tb_target_short == 1, 1, 0)
        return out




class FutureLabeler:
    """
    Standard Future Labeler with backward compatibility.
    """
    def __init__(self, horizon: int = 12, quality_threshold_atr: float = 2.0):
        self.horizon = horizon
        self.quality_threshold = quality_threshold_atr
        self.tb_labeler = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        out = self.tb_labeler.label(df)
        return out
