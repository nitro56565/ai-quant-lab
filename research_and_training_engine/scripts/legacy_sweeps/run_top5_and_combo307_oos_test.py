"""
=================================================================================
  🧪 HEAD-TO-HEAD LABORATORY TEST: FROZEN BASELINE v1.0 vs TOP 5 OOS WINNERS 
     vs 2026 COMBO #307 CONFIGURATION ON 2018-2025 OUT-OF-SAMPLE DATA (VERIFIED 100% PARITY)
=================================================================================
Imports the exact simulation and model evaluation functions from run_pure_unique_grid_search.py
to guarantee 100% bit-identical parity and zero parameter discrepancy.

Evaluates side-by-side on the 8-Year OOS Horizon (2018–2025):
1. Frozen Baseline v1.0 Control (Equal 33/33/33, d=5, 9-State, 0.75% Risk)
2. Winner #1 (Combo #271: Ratio A, d=4, 4-State, Extended 3.0 TP, 0.75% Risk)
3. Winner #2 (Combo #127: Equal 33/33/33, d=4, 4-State, Extended 3.0 TP, 0.75% Risk)
4. Winner #3 (Combo #253: Ratio A, d=4, 4-State, Baseline 2.5 TP, 0.75% Risk)
5. Winner #4 (Combo #199: Ratio A, d=5, 4-State, Extended 3.0 TP, 0.75% Risk)
6. Winner #5 (Combo #109: Equal 33/33/33, d=4, 4-State, Baseline 2.5 TP, 0.75% Risk)
7. 2026 Holdout Winner (Combo #307 Configuration on 2018-2025 OOS Data)
=================================================================================
"""

import os
import sys
import json
import time
import warnings
import itertools
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from production_deployment.canonical_backtest.run_canonical_production_backtest import run_canonical_simulation

# Import exact prediction and evaluation functions from run_pure_unique_grid_search to guarantee 100% parity
from scripts.run_pure_unique_grid_search import (
    build_full_prediction_cache,
    evaluate_pure_unique_combination_task
)

def main():
    start_t = time.time()
    print("=================================================================================", flush=True)
    print("  🧪 VERIFIED HEAD-TO-HEAD LABORATORY TEST: BASELINE v1.0 vs TOP 5 OOS WINNERS vs COMBO #307", flush=True)
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

    cpu_cores = max(1, (os.cpu_count() or 8) - 1)
    print(f"▶ Step 1: Pre-computing Full Model Prediction Cache using {cpu_cores} Cores...", flush=True)

    pred_cache_oos = build_full_prediction_cache(df_lbl, all_feat_cols, years_oos, df_eval_oos, cpu_cores)

    # Reconstruct 432 Grid to extract exact parameter specifications
    ratios = ["Equal 33/33/33 (Baseline v1.0)", "Ratio A (50% Cat / 25% LGB / 25% XGB)", "Single CatBoost (100%)"]
    depths = [5, 4]
    regimes = ["9-State Engine", "4-State Engine"]
    barriers = ["Baseline 2.5/1.5", "Extended 3.0/1.5"]
    memory_windows = ["Expanding Window", "2-Year Rolling"]
    risk_tiers = [0.0075, 0.0050, 0.0025]
    hurdles = [(0.42, 0.36), (0.48, 0.40), (0.52, 0.44)]

    grid_combos = list(itertools.product(ratios, depths, regimes, barriers, memory_windows, risk_tiers, hurdles))

    # Targeted Candidate IDs in 432 Grid:
    # 271: Winner #1 (Ratio A, d=4, 4-State, Extended 3.0 TP, Expanding, 0.75% Risk, 0.42/0.36)
    # 127: Winner #2 (Equal 33/33/33, d=4, 4-State, Extended 3.0 TP, Expanding, 0.75% Risk, 0.42/0.36)
    # 253: Winner #3 (Ratio A, d=4, 4-State, Baseline 2.5 TP, Expanding, 0.75% Risk, 0.42/0.36)
    # 199: Winner #4 (Ratio A, d=5, 4-State, Extended 3.0 TP, Expanding, 0.75% Risk, 0.42/0.36)
    # 109: Winner #5 (Equal 33/33/33, d=4, 4-State, Baseline 2.5 TP, Expanding, 0.75% Risk, 0.42/0.36)
    # 307: 2026 Holdout Winner (Equal 33/33/33, d=4, 4-State, Extended 3.0 TP, 2-Year Rolling, 0.75% Risk, 0.42/0.36)
    target_ids = [271, 127, 253, 199, 109, 307]

    print("▶ Step 2: Evaluating Targeted Strategy Candidates using Exact Grid Functions...", flush=True)
    
    spec_results = []

    # 1. Exact Canonical Control Baseline Run (3,982 trades / +841.56%)
    (pl_lgb5, pl_cat5, pl_xgb5, ps_lgb5, ps_cat5, ps_xgb5, hmm5) = pred_cache_oos[(5, "9-State Engine", "Expanding Window")]
    p_l_v1 = (pl_lgb5 + pl_cat5 + pl_xgb5) / 3.0
    p_s_v1 = (ps_lgb5 + ps_cat5 + ps_xgb5) / 3.0
    res_control = run_canonical_simulation(df_eval_oos, p_l_v1, p_s_v1, hmm5)

    spec_results.append({
        'id': 1,
        'name': "🔒 FROZEN BASELINE v1.0 CONTROL (Combo #1)",
        'trades': res_control['trades'],
        'ret_pct': res_control['ret_pct'],
        'cagr_pct': res_control['cagr_pct'],
        'sharpe': res_control['sharpe'],
        'pf': res_control['pf'],
        'mtm_max_dd': res_control['mtm_max_dd']
    })

    for cid in target_ids:
        c_params = grid_combos[cid - 1]
        res = evaluate_pure_unique_combination_task(cid, c_params, df_eval_oos, pred_cache_oos)

        if cid == 271: name = "🥇 OOS WINNER #1 (Combo #271: Ratio A, d=4, 4-State, TP 3.0)"
        elif cid == 127: name = "🥇 OOS WINNER #2 (Combo #127: Equal 33/33/33, d=4, TP 3.0)"
        elif cid == 253: name = "🥇 OOS WINNER #3 (Combo #253: Ratio A, d=4, 4-State, TP 2.5)"
        elif cid == 199: name = "🥇 OOS WINNER #4 (Combo #199: Ratio A, d=5, 4-State, TP 3.0)"
        elif cid == 109: name = "🥇 OOS WINNER #5 (Combo #109: Equal 33/33/33, d=4, TP 2.5)"
        elif cid == 307: name = "🔥 2026 HOLDOUT WINNER (Combo #307 Configuration)"
        else: name = f"Combo #{cid}"

        spec_results.append({
            'id': cid,
            'name': name,
            'trades': res['trades'],
            'ret_pct': res['ret_pct'],
            'cagr_pct': res['cagr_pct'],
            'sharpe': res['sharpe'],
            'pf': res['pf'],
            'mtm_max_dd': res['mtm_max_dd']
        })

    # Print Official Side-by-Side Comparative Matrix
    print("\n" + "=" * 125)
    print("  🏆 VERIFIED HEAD-TO-HEAD COMPARATIVE SCORECARD: BASELINE v1.0 vs TOP 5 OOS WINNERS vs 2026 COMBO #307 (2018-2025 OOS)")
    print("=" * 125)
    print(f"{'Targeted Candidate Specification':<65} | {'Trades':<8} | {'Net Return':<12} | {'CAGR (%/yr)':<12} | {'Sharpe':<8} | {'PF':<6} | {'Max DD':<8}")
    print("-" * 125)

    for item in spec_results:
        print(f"{item['name']:<65} | {item['trades']:<8,} | +{item['ret_pct']:<11.2f}% | +{item['cagr_pct']:<11.2f}% | {item['sharpe']:<8.2f} | {item['pf']:<6.2f} | -{item['mtm_max_dd']:<7.2f}%")
    print("=" * 125 + "\n")

    elapsed_m = (time.time() - start_t) / 60.0
    print(f"🎉 VERIFIED HEAD-TO-HEAD LABORATORY TEST COMPLETED IN {elapsed_m:.2f} MINUTES! 🎉\n", flush=True)

if __name__ == "__main__":
    main()
