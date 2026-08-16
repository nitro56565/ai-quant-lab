"""
=================================================================================
  🧪 STAGE 3 SPECIAL EXPERIMENT — TRIPLE ENSEMBLE RATIO SWEEP vs SINGLE CATBOOST vs FROZEN v1.0
=================================================================================
Evaluates different probability ratio distributions for the Triple Ensemble Stack
side-by-side against Single CatBoost Classifier and Frozen Baseline v1.0.

🔒 FROZEN CONTROL: EURUSD H1 | 2018-2025 OOS | 0.75% Risk | Max 1 Pos
Control Benchmark: 3,982 Trades | +841.56% Net Return | CAGR +32.38% | Sharpe 1.68 | Daily MtM MDD 21.20% | PF 1.13

Ratio Sweep Configurations Tested:
1. Frozen Baseline v1.0 Control (Equal 33.3% LGBM / 33.3% CatBoost / 33.3% XGBoost)
2. Track 2: Single CatBoost Classifier (100% CatBoost)
3. Ratio A: CatBoost Dominant (50% Cat / 25% LGB / 25% XGB)
4. Ratio B: CatBoost Heavy (60% Cat / 20% LGB / 20% XGB)
5. Ratio C: CatBoost / LGBM Heavy (45% Cat / 45% LGB / 10% XGB)
6. Ratio D: CatBoost / XGB Heavy (45% Cat / 45% XGB / 10% LGB)
7. Ratio E: Balanced Precision (40% Cat / 30% XGB / 30% LGB)
=================================================================================
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector
from production_deployment.canonical_backtest.run_canonical_production_backtest import process_fold, run_canonical_simulation

def process_fold_models(yr, df_lbl, all_feat_cols):
    warnings.filterwarnings("ignore")
    fold_seed = 42
    np.random.seed(fold_seed)

    train_end_year = yr - 1
    train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
    test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_m].copy()

    hmm_detector = HMMRegimeDetector(n_components=3, random_state=fold_seed)
    hmm_detector.fit(df_tr)
    hmm_tr = hmm_detector.predict(df_tr)
    hmm_te = hmm_detector.predict(df_te)

    tr_v = df_tr['feat_vol_atr_pct'].values; te_v = df_te['feat_vol_atr_pct'].values
    v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 33.33] = 1; v_tr[tr_v >= 66.67] = 2
    v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 33.33] = 1; v_te[te_v >= 66.67] = 2

    state_tr = (hmm_tr * 3) + v_tr; state_te = (hmm_te * 3) + v_te

    X_tr_mat = df_tr[all_feat_cols].values; X_te_mat = df_te[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values

    pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
    ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

    for s in range(9):
        mask_tr = (state_tr == s); mask_te = (state_te == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 30:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

            pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat[mask_te])[:, 1]

            ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat[mask_te])[:, 1]
        else:
            pl_lgb[mask_te] = 0.30; pl_cat[mask_te] = 0.30; pl_xgb[mask_te] = 0.30
            ps_lgb[mask_te] = 0.30; ps_cat[mask_te] = 0.30; ps_xgb[mask_te] = 0.30

    return df_te.index, pl_lgb, pl_cat, pl_xgb, ps_lgb, ps_cat, ps_xgb, hmm_te

def main():
    print("=================================================================================", flush=True)
    print("  🧪 STAGE 3 SPECIAL EXPERIMENT — TRIPLE ENSEMBLE RATIO DISTRIBUTION SWEEP", flush=True)
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

    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    years_oos = list(range(2018, 2026))

    cpu_cores = max(1, (os.cpu_count() or 8) - 1)
    print(f"▶ Step 1: Fitting Fold Models across 8-Fold OOS Walk-Forward ({cpu_cores} Cores)...", flush=True)

    results_models = Parallel(n_jobs=cpu_cores)(
        delayed(process_fold_models)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    n_bars = len(df_eval_oos)
    pl_lgb = np.zeros(n_bars); pl_cat = np.zeros(n_bars); pl_xgb = np.zeros(n_bars)
    ps_lgb = np.zeros(n_bars); ps_cat = np.zeros(n_bars); ps_xgb = np.zeros(n_bars)
    hmm_oos = np.zeros(n_bars)

    for te_indices, pl_lgb_f, pl_cat_f, pl_xgb_f, ps_lgb_f, ps_cat_f, ps_xgb_f, hmm_fold in results_models:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        pl_lgb[fold_eval_indices] = pl_lgb_f; pl_cat[fold_eval_indices] = pl_cat_f; pl_xgb[fold_eval_indices] = pl_xgb_f
        ps_lgb[fold_eval_indices] = ps_lgb_f; ps_cat[fold_eval_indices] = ps_cat_f; ps_xgb[fold_eval_indices] = ps_xgb_f
        hmm_oos[fold_eval_indices] = hmm_fold

    # 1. Control Baseline (Equal 33.3/33.3/33.3)
    results_control = Parallel(n_jobs=cpu_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )
    p_control_l = np.zeros(n_bars); p_control_s = np.zeros(n_bars); hmm_control = np.zeros(n_bars)
    for te_indices, pl_fold, ps_fold, hmm_fold in results_control:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_control_l[fold_eval_indices] = pl_fold; p_control_s[fold_eval_indices] = ps_fold; hmm_control[fold_eval_indices] = hmm_fold

    res_control = run_canonical_simulation(df_eval_oos, p_control_l, p_control_s, hmm_control)

    # 2. Single CatBoost
    res_cat = run_canonical_simulation(df_eval_oos, pl_cat, ps_cat, hmm_control)

    # 3. Ratio A: CatBoost Dominant (50% Cat / 25% LGB / 25% XGB)
    p_ratioA_l = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_ratioA_s = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)
    res_ratioA = run_canonical_simulation(df_eval_oos, p_ratioA_l, p_ratioA_s, hmm_control)

    # 4. Ratio B: CatBoost Heavy (60% Cat / 20% LGB / 20% XGB)
    p_ratioB_l = (pl_cat * 0.60) + (pl_lgb * 0.20) + (pl_xgb * 0.20)
    p_ratioB_s = (ps_cat * 0.60) + (ps_lgb * 0.20) + (ps_xgb * 0.20)
    res_ratioB = run_canonical_simulation(df_eval_oos, p_ratioB_l, p_ratioB_s, hmm_control)

    # 5. Ratio C: CatBoost / LGBM Heavy (45% Cat / 45% LGB / 10% XGB)
    p_ratioC_l = (pl_cat * 0.45) + (pl_lgb * 0.45) + (pl_xgb * 0.10)
    p_ratioC_s = (ps_cat * 0.45) + (ps_lgb * 0.45) + (ps_xgb * 0.10)
    res_ratioC = run_canonical_simulation(df_eval_oos, p_ratioC_l, p_ratioC_s, hmm_control)

    # 6. Ratio D: CatBoost / XGB Heavy (45% Cat / 45% XGB / 10% LGB)
    p_ratioD_l = (pl_cat * 0.45) + (pl_xgb * 0.45) + (pl_lgb * 0.10)
    p_ratioD_s = (ps_cat * 0.45) + (ps_xgb * 0.45) + (ps_lgb * 0.10)
    res_ratioD = run_canonical_simulation(df_eval_oos, p_ratioD_l, p_ratioD_s, hmm_control)

    # 7. Ratio E: Balanced Precision (40% Cat / 30% XGB / 30% LGB)
    p_ratioE_l = (pl_cat * 0.40) + (pl_xgb * 0.30) + (pl_lgb * 0.30)
    p_ratioE_s = (ps_cat * 0.40) + (ps_xgb * 0.30) + (ps_lgb * 0.30)
    res_ratioE = run_canonical_simulation(df_eval_oos, p_ratioE_l, p_ratioE_s, hmm_control)

    ratio_results = {
        "🔒 FROZEN BASELINE v1.0 (Equal 33/33/33)": res_control,
        "Track 2: Single CatBoost Classifier (100%)": res_cat,
        "Ratio A: CatBoost Dominant (50% Cat / 25% LGB / 25% XGB)": res_ratioA,
        "Ratio B: CatBoost Heavy (60% Cat / 20% LGB / 20% XGB)": res_ratioB,
        "Ratio C: CatBoost/LGB Heavy (45% Cat / 45% LGB / 10% XGB)": res_ratioC,
        "Ratio D: CatBoost/XGB Heavy (45% Cat / 45% XGB / 10% LGB)": res_ratioD,
        "Ratio E: Balanced Precision (40% Cat / 30% XGB / 30% LGB)": res_ratioE,
    }

    # Print Official Side-by-Side Comparative Matrix
    print("\n" + "=" * 110)
    print("  🏆 SPECIAL EXPERIMENT SCORECARD: TRIPLE ENSEMBLE RATIO SWEEP vs CATBOOST vs FROZEN v1.0")
    print("=" * 110)
    print(f"{'Ensemble Weighting Distribution':<55} | {'Trades':<8} | {'Net Return':<12} | {'CAGR (%/yr)':<12} | {'Sharpe':<8} | {'PF':<6} | {'Max DD':<8}")
    print("-" * 110)
    for name, res in ratio_results.items():
        print(f"{name:<55} | {res['trades']:<8,} | +{res['ret_pct']:<11.2f}% | +{res['cagr_pct']:<11.2f}% | {res['sharpe']:<8.2f} | {res['pf']:<6.2f} | -{res['mtm_max_dd']:<7.2f}%")
    print("=" * 110 + "\n")

if __name__ == "__main__":
    main()
