"""
=================================================================================
  FROZEN BASELINE v3.2 MASTER PRODUCTION MODEL TRAINING & EXPORT SCRIPT
=================================================================================
Trains Combo #271 on the entire 2014-2026 historical dataset.
Architecture: 4-State Engine, Ratio A (50% Cat, 25% LGB, 25% XGB), max_depth=4.
Exports weights to models/production_deployment/model_suite.joblib for Live Engine use.
=================================================================================
"""

import os
import sys
import json
import warnings
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector

def main():
    print("=================================================================================", flush=True)
    print("  🚀 TRAINING FROZEN BASELINE v3.2 MASTER PRODUCTION MODEL", flush=True)
    print("=================================================================================\n", flush=True)

    loader = DataLoader()
    symbol = "EURUSD"
    req_full = DataRequest(symbol=symbol, timeframe="1h", start="2014-01-01", end="2026-08-11")
    df_full = loader.load(req_full)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_full.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    df_tr = df_lbl.dropna(subset=['label_dir_long']).copy()

    print(f"▶ Fitting 4-State Regime Engine on {len(df_tr)} bars...", flush=True)
    fold_seed = 42
    hmm_detector = HMMRegimeDetector(n_components=2, random_state=fold_seed)
    hmm_detector.fit(df_tr)
    hmm_tr = hmm_detector.predict(df_tr)

    tr_v = df_tr['feat_vol_atr_pct'].values
    v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 50.0] = 1
    state_tr = (hmm_tr * 2) + v_tr

    X_tr_mat = df_tr[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values

    models_long = {}
    models_short = {}

    for s in range(4):
        mask_tr = (state_tr == s)
        print(f"▶ Training Baseline v3.2 Ensembles for Regime State {s} (N={np.sum(mask_tr)})...", flush=True)
        if np.sum(mask_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=-1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=-1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

            models_long[s] = {'lgb': ml_lgb, 'cat': ml_cat, 'xgb': ml_xgb}
            models_short[s] = {'lgb': ms_lgb, 'cat': ms_cat, 'xgb': ms_xgb}
        else:
            print(f"⚠️ Regime State {s} has insufficient samples.")

    production_suite = {
        "architecture": "FourStateRegimeEnsemble_v3",
        "hmm_detector": hmm_detector,
        "models_long": models_long,
        "models_short": models_short,
        "feat_cols": all_feat_cols
    }

    model_dir = "trained_model_artifacts/production_deployment"
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(production_suite, os.path.join(model_dir, "model_suite.joblib"))

    metadata = {
        "model_id": "CERTIFIED_BASELINE_V3_MASTER",
        "version": "3.2.0",
        "symbol": "EURUSD",
        "timeframe": "1h",
        "architecture": "FourStateRegimeEnsemble_v3 (Combo #271)",
        "features": len(all_feat_cols)
    }

    with open(os.path.join(model_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=4)

    print(f"✅ Frozen Baseline v3.2 Master weights successfully saved to {model_dir}/model_suite.joblib")

if __name__ == "__main__":
    main()
