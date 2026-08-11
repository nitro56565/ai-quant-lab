"""
Monte Carlo Trade Reshuffling & Risk-of-Ruin Stress Testing Protocol.
Runs 1,000 Monte Carlo trade permutations on actual out-of-sample trade sequences (4,020 trades)
for 0.50%, 0.75%, 1.00%, and 1.50% Risk per Trade to quantify path-dependency, worst-case losing streaks,
and probabilities of 10%, 15%, 20%, 25%, 30%, and 50% Drawdowns.
"""

import os, sys, time, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector

def process_fold(yr, df_lbl, all_feat_cols):
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

    tr_v = df_tr['feat_vol_atr_pct'].values
    te_v = df_te['feat_vol_atr_pct'].values

    v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 33.33] = 1; v_tr[tr_v >= 66.67] = 2
    v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 33.33] = 1; v_te[te_v >= 66.67] = 2

    state_tr = (hmm_tr * 3) + v_tr
    state_te = (hmm_te * 3) + v_te

    X_tr_mat = df_tr[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values
    X_te_mat = df_te[all_feat_cols].values

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

    p_stack_l = (pl_lgb + pl_cat + pl_xgb) / 3.0
    p_stack_s = (ps_lgb + ps_cat + ps_xgb) / 3.0
    return df_te.index, p_stack_l, p_stack_s, hmm_te

def run_monte_carlo():
    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("=================================================================================", flush=True)
    print("  🔬 MONTE CARLO TRADE RESHUFFLING & RISK-OF-RUIN STRESS LABORATORY", flush=True)
    print("=================================================================================", flush=True)
    print(f"  • Multi-Core Accelerator: Safe Parallelization across {safe_cores} CPU Cores")
    print("  • 1,000 Monte Carlo Path Permutations per Risk Level (0.50%, 0.75%, 1.00%, 1.50%)\n", flush=True)

    t0 = time.time()
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

    eval_mask = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval = df_feat[eval_mask].copy()
    total_h1_bars = len(df_eval)
    years_oos = list(range(2018, 2026))

    print("Extracting OOS Predictions across 8 Walk-Forward Years...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l = np.zeros(total_h1_bars)
    p_stack_s = np.zeros(total_h1_bars)
    hmm_oos = np.zeros(total_h1_bars)

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in te_indices if idx in df_eval.index]
        p_stack_l[fold_eval_indices] = pl_fold
        p_stack_s[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    pip_size = 0.0001
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    req_p_arr = np.where(hmm_oos == 1.0, 0.42, 0.36)

    signals_buy = (p_stack_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_stack_s >= req_p_arr) & trading_window

    # Extract Base Normalized Trade R-Multiples (or raw pips) from Backtest
    trades = []; in_trade = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; pending_order = None
    signals_arr = np.full(total_h1_bars, "NONE", dtype=object)
    for i in range(total_h1_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_h1_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        if in_trade:
            t_log = trades[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not t_log['partial_taken'] and r_floating >= 1.5:
                t_log['partial_taken'] = True

            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (0.3 * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (0.3 * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                in_trade = False
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                sl_pips = initial_sl_dist / pip_size
                # Calculate Net Trade R-Multiple (accounting for 50% partial exit at +1.5R and commission)
                if t_log['partial_taken']:
                    partial_r = 1.5 * 0.5
                    remaining_r = (rem_pips / sl_pips) * 0.5
                    comm_r = (0.7 * pip_size / initial_sl_dist)  # Approx commission in R
                    trade_r = partial_r + remaining_r - comm_r
                else:
                    trade_r = (rem_pips / sl_pips) - (0.7 * pip_size / initial_sl_dist)

                t_log['trade_r'] = trade_r; t_log['status'] = 'closed'

                if signals_arr[i] == opposite_sig:
                    pending_order = {"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr}

        if not in_trade and pending_order is not None:
            p_dir = pending_order["direction"]; p_limit = pending_order["limit_price"]; p_atr = pending_order["atr"]; sig_idx = pending_order["signal_idx"]
            if (i - sig_idx) > 3: pending_order = None
            else:
                filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                if filled:
                    in_trade = True; direction = p_dir; entry_time = timestamp; entry_price = p_limit; pending_order = None
                    sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5; initial_sl_dist = sl_pips * pip_size
                    if direction == 'BUY': sl_price = entry_price - initial_sl_dist; tp_price = entry_price + (tp_pips * pip_size)
                    else: sl_price = entry_price + initial_sl_dist; tp_price = entry_price - (tp_pips * pip_size)
                    trades.append({'trade_id': len(trades) + 1, 'symbol': 'EURUSD', 'direction': direction, 'entry_time': entry_time, 'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'partial_taken': False, 'status': 'open'})

        if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

    closed_r = np.array([t['trade_r'] for t in trades if t['status'] == 'closed'])
    num_trades = len(closed_r)
    print(f"  ✓ Extracted {num_trades} OOS Trade R-Multiples (Mean R = {np.mean(closed_r):+.4f}R, Win Rate = {np.mean(closed_r > 0)*100:.1f}%)\n", flush=True)

    risk_levels = [0.0050, 0.0075, 0.0100, 0.0150]
    num_mc = 1000

    def simulate_mc_path(r_arr, risk_pct, path_seed):
        rng = np.random.RandomState(path_seed)
        shuffled_r = rng.permutation(r_arr)
        
        equity = 10000.0
        eq_curve = [equity]
        
        for r in shuffled_r:
            risk_usd = equity * risk_pct
            pnl_usd = risk_usd * r
            equity = max(10.0, equity + pnl_usd)
            eq_curve.append(equity)
            
        eq_arr = np.array(eq_curve)
        peaks = np.maximum.accumulate(eq_arr)
        dds = (eq_arr - peaks) / peaks * 100.0
        max_dd = abs(np.min(dds))
        net_ret = (eq_arr[-1] - 10000.0) / 10000.0 * 100.0
        return net_ret, max_dd

    mc_results = {}

    for r_pct in risk_levels:
        r_label = f"{r_pct*100:.2f}% Risk per Trade"
        print(f"▶ Running 1,000 Monte Carlo Reshuffling Paths for {r_label}...", flush=True)
        
        paths = Parallel(n_jobs=safe_cores)(
            delayed(simulate_mc_path)(closed_r, r_pct, seed) for seed in range(1000, 1000 + num_mc)
        )
        
        rets = np.array([p[0] for p in paths])
        dds = np.array([p[1] for p in paths])
        
        p_dd_10 = np.mean(dds >= 10.0) * 100.0
        p_dd_15 = np.mean(dds >= 15.0) * 100.0
        p_dd_20 = np.mean(dds >= 20.0) * 100.0
        p_dd_25 = np.mean(dds >= 25.0) * 100.0
        p_dd_30 = np.mean(dds >= 30.0) * 100.0
        p_ruin = np.mean(dds >= 50.0) * 100.0
        
        mc_results[r_label] = {
            "median_ret": np.median(rets), "p5_ret": np.percentile(rets, 5), "p95_ret": np.percentile(rets, 95),
            "median_dd": np.median(dds), "p95_dd": np.percentile(dds, 95),
            "p_dd_10": p_dd_10, "p_dd_15": p_dd_15, "p_dd_20": p_dd_20,
            "p_dd_25": p_dd_25, "p_dd_30": p_dd_30, "p_ruin": p_ruin
        }
        print(f"  ✓ {r_label} Complete: Median Return = +{np.median(rets):.1f}%, Median DD = {np.median(dds):.2f}%, 95th Percentile DD = {np.percentile(dds, 95):.2f}%, Ruin (50% DD) = {p_ruin:.1f}%\n", flush=True)

    total_elapsed = time.time() - t0

    print("=========================================================================================================================================", flush=True)
    print(f"  🏆 MONTE CARLO RISK-OF-RUIN & DRAWDOWN PROBABILITY SCORECARD (1,000 PATHS - TOTAL TIME: {total_elapsed:.1f}s)", flush=True)
    print("=========================================================================================================================================", flush=True)
    print(f"{'Risk Allocation':<22} | {'Median Net Ret':<15} | {'Median DD':<10} | {'95th %ile DD':<12} | {'P(DD>10%)':<10} | {'P(DD>15%)':<10} | {'P(DD>20%)':<10} | {'P(DD>25%)':<10} | {'P(DD>30%)':<10} | {'Ruin (≥50%)':<11}", flush=True)
    print("-" * 145, flush=True)

    for r_label, res in mc_results.items():
        print(f"{r_label:<22} | +{res['median_ret']:<14.1f}% | {res['median_dd']:<9.2f}% | {res['p95_dd']:<11.2f}% | {res['p_dd_10']:<9.1f}% | {res['p_dd_15']:<9.1f}% | {res['p_dd_20']:<9.1f}% | {res['p_dd_25']:<9.1f}% | {res['p_dd_30']:<9.1f}% | {res['p_ruin']:<10.1f}%", flush=True)

    print("=========================================================================================================================================", flush=True)

if __name__ == "__main__":
    run_monte_carlo()
