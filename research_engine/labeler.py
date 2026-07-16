"""
Future Labeler
==============
For every H1 candle, looks forward N bars and computes:
  - Maximum Favorable Excursion (MFE): best price reached in our favor
  - Maximum Adverse Excursion (MAE): worst price reached against us
  - Return after N bars

Then labels each bar: BUY, SELL, or NO_TRADE
based on objective risk/reward criteria.

IMPORTANT: This module is ONLY used in research/training.
           Labels use future data by design.
           They must NEVER be used as features in live trading.
"""
import pandas as pd
import numpy as np


class FutureLabeler:
    """
    Labels each candle with the future outcome for supervised learning.
    """

    def __init__(self, horizon: int = 12, min_rr: float = 1.5, min_move_atr: float = 1.0):
        """
        Args:
            horizon: Number of future bars to look forward (e.g. 12 = 12 hours on H1).
            min_rr: Minimum reward-to-risk ratio to qualify as BUY or SELL.
            min_move_atr: Minimum MFE in ATR multiples to qualify as a trade.
        """
        self.horizon = horizon
        self.min_rr = min_rr
        self.min_move_atr = min_move_atr

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes forward-looking labels for each bar.

        Requires columns: close, high, low, feat_vol_atr

        Returns DataFrame with added columns:
          - label_mfe_pips: Maximum favorable excursion (BUY direction) in pips
          - label_mae_pips: Maximum adverse excursion (BUY direction) in pips
          - label_return_pips: Close-to-close return after horizon bars in pips
          - label_mfe_atr: MFE normalized by ATR
          - label_mae_atr: MAE normalized by ATR
          - label_return_atr: Return normalized by ATR
          - label: BUY / SELL / NO_TRADE
        """
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        atr = df['feat_vol_atr'].values
        n = len(df)
        h = self.horizon

        pip_size = 0.0001  # EURUSD

        # Pre-allocate arrays
        mfe_buy = np.full(n, np.nan)
        mae_buy = np.full(n, np.nan)
        mfe_sell = np.full(n, np.nan)
        mae_sell = np.full(n, np.nan)
        ret = np.full(n, np.nan)

        for i in range(n - h):
            entry = close[i]
            future_highs = high[i + 1: i + 1 + h]
            future_lows = low[i + 1: i + 1 + h]
            future_close = close[i + h]

            # BUY perspective
            mfe_buy[i] = (np.max(future_highs) - entry) / pip_size
            mae_buy[i] = (entry - np.min(future_lows)) / pip_size

            # SELL perspective
            mfe_sell[i] = (entry - np.min(future_lows)) / pip_size
            mae_sell[i] = (np.max(future_highs) - entry) / pip_size

            # Close-to-close return
            ret[i] = (future_close - entry) / pip_size

        out = df.copy()

        # BUY-direction metrics
        out['label_mfe_buy_pips'] = mfe_buy
        out['label_mae_buy_pips'] = mae_buy
        out['label_mfe_sell_pips'] = mfe_sell
        out['label_mae_sell_pips'] = mae_sell
        out['label_return_pips'] = ret

        # ATR-normalized versions
        atr_pips = atr / pip_size
        atr_pips_safe = np.where(atr_pips > 0, atr_pips, 1.0)
        out['label_mfe_buy_atr'] = mfe_buy / atr_pips_safe
        out['label_mae_buy_atr'] = mae_buy / atr_pips_safe
        out['label_mfe_sell_atr'] = mfe_sell / atr_pips_safe
        out['label_mae_sell_atr'] = mae_sell / atr_pips_safe
        out['label_return_atr'] = ret / atr_pips_safe

        # Classification labels
        labels = np.full(n, 'NO_TRADE', dtype=object)
        for i in range(n - h):
            a = atr_pips_safe[i]
            if a <= 0:
                continue

            buy_mfe = mfe_buy[i]
            buy_mae = mae_buy[i]
            sell_mfe = mfe_sell[i]
            sell_mae = mae_sell[i]

            buy_rr = (buy_mfe / buy_mae) if buy_mae > 0 else 999.0
            sell_rr = (sell_mfe / sell_mae) if sell_mae > 0 else 999.0

            buy_move_atr = buy_mfe / a
            sell_move_atr = sell_mfe / a

            is_buy = (buy_rr >= self.min_rr) and (buy_move_atr >= self.min_move_atr)
            is_sell = (sell_rr >= self.min_rr) and (sell_move_atr >= self.min_move_atr)

            if is_buy and is_sell:
                # Both qualify — pick the stronger direction
                if buy_rr > sell_rr:
                    labels[i] = 'BUY'
                else:
                    labels[i] = 'SELL'
            elif is_buy:
                labels[i] = 'BUY'
            elif is_sell:
                labels[i] = 'SELL'

        out['label'] = labels

        return out

    def get_label_stats(self, df: pd.DataFrame) -> dict:
        """Returns distribution statistics for the labels."""
        counts = df['label'].value_counts()
        total = len(df.dropna(subset=['label_return_pips']))
        return {
            'total_labeled_bars': total,
            'BUY': int(counts.get('BUY', 0)),
            'SELL': int(counts.get('SELL', 0)),
            'NO_TRADE': int(counts.get('NO_TRADE', 0)),
            'buy_pct': round(counts.get('BUY', 0) / total * 100, 2) if total > 0 else 0,
            'sell_pct': round(counts.get('SELL', 0) / total * 100, 2) if total > 0 else 0,
            'no_trade_pct': round(counts.get('NO_TRADE', 0) / total * 100, 2) if total > 0 else 0,
        }
