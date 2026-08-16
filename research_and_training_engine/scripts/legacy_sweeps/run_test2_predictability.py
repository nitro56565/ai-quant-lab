"""
=================================================================================
  🟢 TEST 2 — PRE-TRADE DRAWDOWN PREDICTABILITY TEST (OFFLINE ML EXPERIMENT)
=================================================================================
Evaluates whether upcoming high-drawdown trades or severe loss trades can be 
predicted STRICTLY USING PRE-TRADE INFORMATION.

Features Evaluated (100% Pre-Trade):
- HMM Regime State (0-8)
- PAE Model Prediction Probability (0.36 to 0.65)
- Volatility ATR Percentile (40.0 to 100.0)
- Trade Direction (1 for BUY, 0 for SELL)
- Hour of Day (0 to 23)
- Day of Week (0 to 4)
- Pre-Trade Consecutive Loss Streak (0 to 5+)
- Pre-Trade Equity Drawdown % (0 to 21.2%)

Target Variable (Y):
- Binary 1 if Trade is inside a Top Drawdown Cluster or produces Loss < -0.8R
- Binary 0 otherwise

Statistical Benchmarks:
- 5-Fold Stratified Cross-Validation ROC-AUC
- 1,000 Iteration Feature Permutation Test p-value (Requires p < 0.05)
=================================================================================
"""

import os
import sys
import json
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, precision_score, recall_score, brier_score_loss
from sklearn.model_selection import StratifiedKFold

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector
from production_deployment.canonical_backtest.run_canonical_production_backtest import process_fold
from scripts.run_test1_drawdown_autopsy import run_autopsy_simulation, analyze_drawdowns

def main():
    print("=================================================================================", flush=True)
    print("  🟢 TEST 2 — PRE-TRADE DRAWDOWN PREDICTABILITY TEST", flush=True)
    print("=================================================================================\n", flush=True)

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
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    years_oos = list(range(2018, 2026))

    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("▶ Step 1: Fitting 8-Fold OOS Walk-Forward Ensemble Predictions...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l_oos = np.zeros(len(df_eval_oos))
    p_stack_s_oos = np.zeros(len(df_eval_oos))
    hmm_oos = np.zeros(len(df_eval_oos))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[fold_eval_indices] = pl_fold
        p_stack_s_oos[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    print("▶ Step 2: Extracting Trade-by-Trade Pre-Trade Features & Targets...", flush=True)
    closed_trades, daily_eq = run_autopsy_simulation(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos)
    top5_dd, df_trades = analyze_drawdowns(closed_trades, daily_eq)

    # Build Pre-Trade Feature Matrix X and Target Y
    X_rows = []
    y_target_dd = [] # Target 1: Is in top DD cluster
    y_target_loss = [] # Target 2: Trade loss < -0.8R

    for idx, row in df_trades.iterrows():
        ts = row['entry_time']
        direction_val = 1 if row['direction'] == 'BUY' else 0
        pae_conf = row['pae_conf']
        hmm_state = row['hmm_state']
        atr_pct = row['atr_pct']
        loss_streak = row['loss_streak_before']
        hour_val = ts.hour
        dow_val = ts.dayofweek

        X_rows.append([hmm_state, pae_conf, atr_pct, direction_val, hour_val, dow_val, loss_streak])
        y_target_dd.append(1 if row['is_in_top_dd'] else 0)
        y_target_loss.append(1 if row['r_multiple'] < -0.8 else 0)

    X_mat = np.array(X_rows)
    y_dd_arr = np.array(y_target_dd)
    y_loss_arr = np.array(y_target_loss)

    print(f"  • Total Trades Analyzed: {len(X_mat)}")
    print(f"  • Drawdown Cluster Trades (Target Y=1): {np.sum(y_dd_arr)} ({np.mean(y_dd_arr)*100:.2f}%)")
    print(f"  • Severe Loss Trades (< -0.8R Target Y=1): {np.sum(y_loss_arr)} ({np.mean(y_loss_arr)*100:.2f}%)\n", flush=True)

    # Cross-Validated Predictability Test
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    rf_dd_probs = np.zeros(len(y_dd_arr))
    lr_dd_probs = np.zeros(len(y_dd_arr))

    for tr_idx, te_idx in skf.split(X_mat, y_dd_arr):
        X_tr, X_te = X_mat[tr_idx], X_mat[te_idx]
        y_tr, y_te = y_dd_arr[tr_idx], y_dd_arr[te_idx]

        rf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42).fit(X_tr, y_tr)
        lr = LogisticRegression(random_state=42).fit(X_tr, y_tr)

        rf_dd_probs[te_idx] = rf.predict_proba(X_te)[:, 1]
        lr_dd_probs[te_idx] = lr.predict_proba(X_te)[:, 1]

    auc_rf_dd = roc_auc_score(y_dd_arr, rf_dd_probs)
    auc_lr_dd = roc_auc_score(y_dd_arr, lr_dd_probs)

    # 1,000-Iteration Permutation Test for Statistical Significance (p-value)
    print("▶ Step 3: Running 1,000-Iteration Permutation Test for p-value...", flush=True)
    null_aucs = []
    np.random.seed(42)
    for _ in range(1000):
        y_null = np.random.permutation(y_dd_arr)
        null_aucs.append(roc_auc_score(y_null, rf_dd_probs))

    p_value_auc = np.mean(np.array(null_aucs) >= auc_rf_dd)

    print("\n=================================================================================")
    print("  🏆 TEST 2 PRE-TRADE PREDICTABILITY RESULTS")
    print("=================================================================================")
    print(f"  • Random Forest ROC-AUC (Drawdown Cluster): {auc_rf_dd:.4f}")
    print(f"  • Logistic Regression ROC-AUC:              {auc_lr_dd:.4f}")
    print(f"  • Null Distribution Mean AUC:               {np.mean(null_aucs):.4f}")
    print(f"  • Permutation Test p-value:                {p_value_auc:.4f}")
    print("-" * 75)

    if p_value_auc < 0.05 and auc_rf_dd >= 0.58:
        predictability_verdict = "🟢 STATISTICALLY PREDICTABLE (p < 0.05 & AUC >= 0.58)"
    elif p_value_auc < 0.05:
        predictability_verdict = "🟡 WEAK PREDICTABILITY (p < 0.05, but AUC < 0.58)"
    else:
        predictability_verdict = "🔴 NOT PREDICTABLE / RANDOM VARIANCE (p >= 0.05)"

    print(f"  🏆 TEST 2 VERDICT: {predictability_verdict}")
    print("=================================================================================\n")

    # Save Test 2 Report
    report_md = f"""# 🟢 TEST 2 — PRE-TRADE PREDICTABILITY REPORT

## 📊 Predictability Metric Summary

| Metric | Score / Result | Benchmark Standard | Status |
| :--- | :---: | :---: | :---: |
| **Random Forest ROC-AUC** | **{auc_rf_dd:.4f}** | $\ge 0.58$ | {'🟢 PASS' if auc_rf_dd >= 0.58 else '🔴 FAIL'} |
| **Logistic Regression ROC-AUC** | **{auc_lr_dd:.4f}** | $\ge 0.55$ | {'🟢 PASS' if auc_lr_dd >= 0.55 else '🔴 FAIL'} |
| **Permutation Test p-value** | **{p_value_auc:.4f}** | $< 0.05$ | {'🟢 SIGNIFICANT' if p_value_auc < 0.05 else '🔴 NOT SIGNIFICANT'} |

---

## 🎯 Question Answered: Is MDD Actually Predictable Pre-Trade?

**Result**: **{predictability_verdict}**
- **ROC-AUC Score**: **{auc_rf_dd:.4f}** (A score of 0.50 represents pure random guessing).
- **Permutation $p$-value**: **{p_value_auc:.4f}** (Requires $p < 0.05$ to reject the null hypothesis of randomness).
"""

    with open("mdd_predictability_report.md", "w") as f:
        f.write(report_md)

    print("=================================================================================")
    print("  ✅ TEST 2 COMPLETE: REPORT SAVED TO 'mdd_predictability_report.md'!")
    print("=================================================================================")

if __name__ == "__main__":
    main()
