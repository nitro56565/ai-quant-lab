"""
Online Model Inference Runner Module.
Computes real-time feature matrix vectors and generates LightGBM + CatBoost predictions.
"""

import numpy as np
import pandas as pd
import logging
from research_engine.feature_matrix import FeatureMatrixBuilder
from ai_engine.ensemble import LightGBMCatBoostEnsemble

logger = logging.getLogger(__name__)

class OnlineModelRunner:
    def __init__(self):
        self.feature_builder = FeatureMatrixBuilder()
        self.ensemble = LightGBMCatBoostEnsemble()
        self.is_trained = False

    def train_online(self, historical_df: pd.DataFrame):

        """
        Trains model ensemble on rolling historical bar data.
        """
        logger.info("⚡ Building Feature Matrix & Labels for Online Model Warmup...")
        df_feat = self.feature_builder.build(historical_df.copy())
        
        # Simple ATR calculation
        close = df_feat['close'].values
        high = df_feat['high'].values
        low = df_feat['low'].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values
        df_feat['feat_vol_atr'] = atr
        df_feat['feat_vol_atr_pct'] = df_feat['feat_vol_atr'].rank(pct=True) * 100.0

        from research_engine.labeler import TripleBarrierLabeler
        tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
        df_lbl = tb_lab.label(df_feat)
        df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
        df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

        feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
        df_lbl[feat_cols] = df_lbl[feat_cols].bfill().ffill().fillna(0.0)
        df_clean = df_lbl.dropna(subset=['label_dir_long'])

        X_train = df_clean[feat_cols]

        targets = {
            'dir_long': df_clean['label_dir_long'],
            'dir_short': df_clean['label_dir_short'],
            'mfe_long': df_clean['label_mfe_long_pips'],
            'mfe_short': df_clean['label_mfe_short_pips'],
            'mae_long': df_clean['label_mae_long_pips'],
            'mae_short': df_clean['label_mae_short_pips']
        }


        self.ensemble.fit(X_train=X_train, targets=targets)
        self.is_trained = True
        logger.info("✅ Online Model Warmup Training Complete.")

    def predict_latest_bar(self, recent_bars_df: pd.DataFrame) -> dict:
        """
        Generates real-time predictions for the most recent completed bar.
        """
        if not self.is_trained:
            self.train_online(recent_bars_df)

        df_feat = self.feature_builder.build(recent_bars_df.copy())
        close = df_feat['close'].values
        high = df_feat['high'].values
        low = df_feat['low'].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values
        df_feat['feat_vol_atr'] = atr
        df_feat['feat_vol_atr_pct'] = df_feat['feat_vol_atr'].rank(pct=True) * 100.0

        feat_cols = [c for c in df_feat.columns if c.startswith('feat_')]
        latest_row = df_feat.iloc[[-1]][feat_cols]

        preds = self.ensemble.predict(latest_row)
        prob_long = preds['prob_long'][0]
        prob_short = preds['prob_short'][0]
        mfe_long = preds['mfe_50_long'][0]
        mfe_short = preds['mfe_50_short'][0]
        mae_long = preds['mae_50_long'][0]
        mae_short = preds['mae_50_short'][0]

        latest_atr = df_feat['feat_vol_atr'].iloc[-1]
        vol_rank = df_feat['feat_vol_atr_pct'].iloc[-1]

        cost_drag = 1.50
        net_ev_long = (prob_long * mfe_long) - ((1.0 - prob_long) * mae_long) - cost_drag
        net_ev_short = (prob_short * mfe_short) - ((1.0 - prob_short) * mae_short) - cost_drag

        signal = None
        if prob_long >= 0.35 and net_ev_long > 0:
            signal = 'BUY'
        elif prob_short >= 0.34 and net_ev_short > 0:
            signal = 'SELL'

        return {
            "signal": signal,
            "prob_long": round(prob_long, 4),
            "prob_short": round(prob_short, 4),
            "net_ev_long": round(net_ev_long, 2),
            "net_ev_short": round(net_ev_short, 2),
            "atr": round(latest_atr, 5),
            "vol_rank_pct": round(vol_rank, 1)
        }

ModelRunner = OnlineModelRunner

