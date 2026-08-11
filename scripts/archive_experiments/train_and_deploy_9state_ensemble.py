"""
Train and Deploy 9-State Market Regime Architecture Production Suite.
Trains 9 specialized LightGBM long & short sub-models (3 Direction HMM x 3 Volatility Quantiles)
on clean H1 history and exports to models/production/model_suite.joblib.
"""

import os, sys, joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector

def train_and_deploy():
    print("=================================================================================")
    print("  🚀 TRAINING & DEPLOYING CERTIFIED 9-STATE REGIME PRODUCTION SUITE v10")
    print("=================================================================================")

    loader = DataLoader()
    symbol = "EURUSD"
    req_full = DataRequest(symbol=symbol, timeframe="1h", start="2014-01-01", end="2025-12-31")
    df_full = loader.load(req_full)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_full.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_feat)
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_clean = df_lbl.dropna(subset=['label_dir_long']).copy()
    df_clean[feat_cols] = df_clean[feat_cols].bfill().ffill().fillna(0.0)

    # 1. Fit Directional HMM
    hmm_detector = HMMRegimeDetector()
    hmm_detector.fit(df_clean)
    hmm_dir_states = hmm_detector.predict(df_clean)

    # 2. Fit Volatility Quantiles (33.33 / 66.67)
    tr_vol_pct = df_clean['feat_vol_atr_pct'].values
    v_state = np.zeros(len(tr_vol_pct), dtype=int)
    v_state[tr_vol_pct >= 33.33] = 1
    v_state[tr_vol_pct >= 66.67] = 2

    # 3. Combine 3 Direction x 3 Volatility -> 9 Regime States (0..8)
    state_9 = (hmm_dir_states * 3) + v_state
    df_clean['regime_state_9'] = state_9

    print(f"  • Total Dataset Samples: {len(df_clean)} bars")
    print(f"  • Fitting 9 Specialized Sub-Models across 9 Regime States...\n")

    models_long = {}
    models_short = {}
    X_mat = df_clean[feat_cols].values
    y_long = df_clean['label_dir_long'].values
    y_short = df_clean['label_dir_short'].values

    for s in range(9):
        mask = (state_9 == s)
        cnt = np.sum(mask)
        print(f"    - State {s} (HMM {s//3}, Vol {s%3}): {cnt} samples")
        if cnt >= 30:
            m_l = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
            m_s = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
            m_l.fit(X_mat[mask], y_long[mask])
            m_s.fit(X_mat[mask], y_short[mask])
            models_long[s] = m_l
            models_short[s] = m_s

    production_bundle = {
        "architecture": "NineStateRegimeEnsemble",
        "version": "10.0.0",
        "hmm_detector": hmm_detector,
        "feature_cols": feat_cols,
        "models_long": models_long,
        "models_short": models_short,
        "vol_low_thresh": 33.33,
        "vol_high_thresh": 66.67
    }

    os.makedirs("models/production", exist_ok=True)
    export_path = "models/production/model_suite.joblib"
    joblib.dump(production_bundle, export_path)
    print(f"\n✅ Production model suite successfully trained and saved to '{export_path}'")

if __name__ == "__main__":
    train_and_deploy()
