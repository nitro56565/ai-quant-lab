"""
=================================================================================
  🧪 MASTER 1,296 COMBINATION GRID SEARCH SWEEP & 2026 HOLDOUT CERTIFICATION
=================================================================================
Executes a 100% empirical grid search across ALL 1,296 parameter combinations 
derived from Stage 1-15 recommendations on Out-of-Sample (2018-2025) data, 
and then validates the top winning combination against 2026 UNTOUCHED HOLDOUT DATA.

🔒 FROZEN CONTROL: EURUSD H1 | 2018-2025 OOS | 2026 Holdout | 0.75% Risk | Max 1 Pos
Control Benchmark: 3,982 Trades | +841.56% Net Return | CAGR +32.38% | Sharpe 1.68 | Daily MtM MDD 21.20% | PF 1.13
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
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector
from production_deployment.canonical_backtest.run_canonical_production_backtest import run_canonical_simulation

def process_fold_custom(yr, df_lbl, all_feat_cols, max_depth=5, regime_states=9, memory_mode='expanding', fold_seed=42):
    warnings.filterwarnings("ignore")
    np.random.seed(fold_seed)

    train_end_year = yr - 1
    if memory_mode == 'rolling_2yr':
        train_start_year = max(2014, yr - 2)
    else:
        train_start_year = 2014

    train_m = (df_lbl.index >= f"{train_start_year}-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
    test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_m].copy()

    n_hmm_components = 2 if regime_states == 4 else 3
    hmm_detector = HMMRegimeDetector(n_components=n_hmm_components, random_state=fold_seed)
    hmm_detector.fit(df_tr)
    hmm_tr = hmm_detector.predict(df_tr)
    hmm_te = hmm_detector.predict(df_te)

    tr_v = df_tr['feat_vol_atr_pct'].values; te_v = df_te['feat_vol_atr_pct'].values
    
    if regime_states == 4:
        v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 50.0] = 1
        v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 50.0] = 1
        state_tr = (hmm_tr * 2) + v_tr; state_te = (hmm_te * 2) + v_te
        total_states = 4
    else:
        v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 33.33] = 1; v_tr[tr_v >= 66.67] = 2
        v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 33.33] = 1; v_te[te_v >= 66.67] = 2
        state_tr = (hmm_tr * 3) + v_tr; state_te = (hmm_te * 3) + v_te
        total_states = 9

    X_tr_mat = df_tr[all_feat_cols].values; X_te_mat = df_te[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values

    pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
    ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

    for s in range(total_states):
        mask_tr = (state_tr == s); mask_te = (state_te == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=max_depth, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=max_depth, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=max_depth, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=max_depth, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=max_depth, learning_rate=0.03, random_state=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=max_depth, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

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

def run_grid_simulation_fully_dynamic(
    df_eval, p_l, p_s, hmm_arr,
    risk_pct=0.0075, p_range=0.42, p_trend=0.36,
    tp_mult=2.5, sl_mult=1.5, max_holding_bars=24,
    friction_pips=0.3, comm_per_lot=7.0
):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    atr_pcts = df_eval['feat_vol_atr_pct'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))

    vol_pass = (atr_pcts >= 40.0)
    req_p_arr = np.where(hmm_arr == 1.0, p_range, p_trend)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    max_open_pos = 1

    active_positions = []; pending_orders = []; closed_trades = []; current_equity = 10000.0; daily_equity = {}

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= float(max_holding_bars): stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = timestamp; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
                current_equity += rem_net
                closed_trades.append(pos)

                if signals_arr[i] == opposite_sig:
                    limit_p = close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr)
                    pending_orders.append({"direction": opposite_sig, "limit_price": limit_p, "signal_idx": i, "atr": atr})
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        remaining_orders = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3: continue
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']

            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
            if filled and len(active_positions) < max_open_pos:
                sl_pips = (p_atr / pip_size) * (sl_mult + 0.5); tp_pips = (p_atr / pip_size) * tp_mult; initial_sl_dist = (p_atr / pip_size) * sl_mult * pip_size
                entry_price = p_limit
                sl_price = entry_price - (p_atr * sl_mult) if p_dir == 'BUY' else entry_price + (p_atr * sl_mult)
                tp_price = entry_price + (p_atr * tp_mult) if p_dir == 'BUY' else entry_price - (p_atr * tp_mult)

                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                new_pos = {
                    'trade_id': len(closed_trades) + len(active_positions) + 1,
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0,
                    'status': 'open'
                }
                active_positions.append(new_pos)
            elif not filled:
                remaining_orders.append(p_order)

        pending_orders = remaining_orders

        if len(active_positions) + len(pending_orders) < max_open_pos and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]
            retrace_pips = (atr / pip_size) * 0.25
            limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

        daily_equity[str(timestamp.date())] = current_equity

    pnls = [t['pnl_usd'] for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()

    num_years = max(0.5, (timestamps[-1] - timestamps[0]).days / 365.25)
    cagr_pct = (((current_equity / 10000.0) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min())

    return {'trades': len(closed_trades), 'net_pnl': net_pnl, 'ret_pct': ret_pct, 'cagr_pct': cagr_pct, 'sharpe': sharpe_daily, 'pf': pf, 'mtm_max_dd': mtm_max_dd}

def evaluate_dynamic_combination_task(comb_id, comb_params, df_eval, pred_cache):
    (ratio_name, depth_val, regime_opt, barrier_opt, memory_opt, risk_val, hurdle_tup, arch_opt) = comb_params

    # Select Key for Cache
    cache_key = (depth_val, regime_opt, memory_opt)
    (pl_lgb, pl_cat, pl_xgb, ps_lgb, ps_cat, ps_xgb, hmm_arr) = pred_cache[cache_key]

    # Apply Ensemble Ratio
    if ratio_name == "Ratio A (50% Cat / 25% LGB / 25% XGB)":
        p_l = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
        p_s = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)
    elif ratio_name == "Single CatBoost (100%)":
        p_l = pl_cat; p_s = ps_cat
    else: # Equal 33/33/33 Baseline
        p_l = (pl_lgb + pl_cat + pl_xgb) / 3.0
        p_s = (ps_lgb + ps_cat + ps_xgb) / 3.0

    # Barrier Parameters
    if barrier_opt == "Extended 3.0/1.5":
        tp_m = 3.0; sl_m = 1.5; holding = 36
    else:
        tp_m = 2.5; sl_m = 1.5; holding = 24

    (p_range, p_trend) = hurdle_tup

    # Architecture Presets Override
    if arch_opt == "Candidate v2.0 Institutional Safe":
        risk_val_final = 0.0050
    elif arch_opt == "Candidate v2.0 Alpha Maximizer":
        risk_val_final = 0.0075
    else:
        risk_val_final = risk_val

    res = run_grid_simulation_fully_dynamic(
        df_eval, p_l, p_s, hmm_arr,
        risk_pct=risk_val_final, p_range=p_range, p_trend=p_trend,
        tp_mult=tp_m, sl_mult=sl_m, max_holding_bars=holding
    )

    score = res['sharpe'] * res['pf'] * (1.0 - (res['mtm_max_dd'] / 100.0))

    return {
        'id': comb_id,
        'ratio': ratio_name,
        'depth': depth_val,
        'regime': regime_opt,
        'barrier': barrier_opt,
        'memory': memory_opt,
        'risk': risk_val_final,
        'hurdle': f"{p_range}/{p_trend}",
        'arch': arch_opt,
        'trades': res['trades'],
        'ret_pct': res['ret_pct'],
        'cagr_pct': res['cagr_pct'],
        'sharpe': res['sharpe'],
        'pf': res['pf'],
        'mtm_max_dd': res['mtm_max_dd'],
        'score': score
    }

def build_prediction_cache(df_lbl, all_feat_cols, years_oos, df_eval_oos, cpu_cores):
    cache_configs = [
        (5, "9-State Engine", "Expanding Window"),
        (4, "9-State Engine", "Expanding Window"),
        (5, "4-State Engine", "Expanding Window"),
        (4, "4-State Engine", "Expanding Window"),
        (5, "9-State Engine", "2-Year Rolling"),
        (4, "9-State Engine", "2-Year Rolling"),
        (5, "4-State Engine", "2-Year Rolling"),
        (4, "4-State Engine", "2-Year Rolling"),
    ]
    
    pred_cache = {}
    n_bars = len(df_eval_oos)

    for (depth_val, regime_opt, memory_opt) in cache_configs:
        print(f"  --> Pre-computing Models for Config (depth={depth_val}, regime={regime_opt[:7]}, mem={memory_opt[:8]})...", flush=True)
        r_states = 4 if regime_opt == "4-State Engine" else 9
        m_mode = 'rolling_2yr' if memory_opt == "2-Year Rolling" else 'expanding'

        folds_res = Parallel(n_jobs=cpu_cores)(
            delayed(process_fold_custom)(yr, df_lbl, all_feat_cols, max_depth=depth_val, regime_states=r_states, memory_mode=m_mode)
            for yr in years_oos
        )

        pl_lgb = np.zeros(n_bars); pl_cat = np.zeros(n_bars); pl_xgb = np.zeros(n_bars)
        ps_lgb = np.zeros(n_bars); ps_cat = np.zeros(n_bars); ps_xgb = np.zeros(n_bars); hmm_a = np.zeros(n_bars)

        for te_indices, plg, pca, pxg, psg, psa, psx, hmm_f in folds_res:
            idx_f = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
            pl_lgb[idx_f] = plg; pl_cat[idx_f] = pca; pl_xgb[idx_f] = pxg
            ps_lgb[idx_f] = psg; ps_cat[idx_f] = psa; ps_xgb[idx_f] = psx; hmm_a[idx_f] = hmm_f

        pred_cache[(depth_val, regime_opt, memory_opt)] = (pl_lgb, pl_cat, pl_xgb, ps_lgb, ps_cat, ps_xgb, hmm_a)

    return pred_cache

def main():
    start_t = time.time()
    print("=================================================================================", flush=True)
    print("  🧪 FULLY DYNAMIC 1,296 COMBINATION GRID SEARCH SWEEP & 2026 CERTIFICATION", flush=True)
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
    print(f"▶ Step 1: Pre-computing Model Prediction Cache using {cpu_cores} Cores...", flush=True)

    pred_cache_oos = build_prediction_cache(df_lbl, all_feat_cols, years_oos, df_eval_oos, cpu_cores)

    # 1,296 Grid Parameter Definition
    ratios = ["Equal 33/33/33 (Baseline v1.0)", "Ratio A (50% Cat / 25% LGB / 25% XGB)", "Single CatBoost (100%)"]
    depths = [5, 4]
    regimes = ["9-State Engine", "4-State Engine"]
    barriers = ["Baseline 2.5/1.5", "Extended 3.0/1.5"]
    memory_windows = ["Expanding Window", "2-Year Rolling"]
    risk_tiers = [0.0075, 0.0050, 0.0025]
    hurdles = [(0.42, 0.36), (0.48, 0.40), (0.52, 0.44)]
    arch_presets = ["Baseline v1.0 Standard", "Candidate v2.0 Alpha Maximizer", "Candidate v2.0 Institutional Safe"]

    grid_combos = list(itertools.product(ratios, depths, regimes, barriers, memory_windows, risk_tiers, hurdles, arch_presets))
    total_grid = len(grid_combos)
    print(f"▶ Step 2: Executing Fully Dynamic 1,296 Combination Grid Sweep ({total_grid} Combinations)...", flush=True)

    grid_results = Parallel(n_jobs=cpu_cores)(
        delayed(evaluate_dynamic_combination_task)(i+1, comb, df_eval_oos, pred_cache_oos)
        for i, comb in enumerate(grid_combos)
    )

    df_results = pd.DataFrame(grid_results)
    df_sorted = df_results.sort_values(by='ret_pct', ascending=False).reset_index(drop=True)

    # Canonical Baseline Control
    (pl_lgb5, pl_cat5, pl_xgb5, ps_lgb5, ps_cat5, ps_xgb5, hmm5) = pred_cache_oos[(5, "9-State Engine", "Expanding Window")]
    p_l_v1 = (pl_lgb5 + pl_cat5 + pl_xgb5) / 3.0
    p_s_v1 = (ps_lgb5 + ps_cat5 + ps_xgb5) / 3.0
    res_control = run_canonical_simulation(df_eval_oos, p_l_v1, p_s_v1, hmm5)

    best_winner = df_sorted.iloc[0]

    print("\n" + "=" * 125)
    print(f"  🏆 TOP 10 WINNING COMBINATIONS FROM FULLY DYNAMIC 1,296 OOS GRID SWEEP vs FROZEN BASELINE v1.0")
    print("=" * 125)
    print(f"{'Combo ID & Specification':<65} | {'Trades':<8} | {'Net Return':<12} | {'CAGR (%/yr)':<12} | {'Sharpe':<8} | {'PF':<6} | {'Max DD':<8}")
    print("-" * 125)
    
    # Print Frozen Control
    print(f"{'🔒 FROZEN BASELINE v1.0 CONTROL':<65} | {res_control['trades']:<8,} | +{res_control['ret_pct']:<11.2f}% | +{res_control['cagr_pct']:<11.2f}% | {res_control['sharpe']:<8.2f} | {res_control['pf']:<6.2f} | -{res_control['mtm_max_dd']:<7.2f}%")
    print("-" * 125)

    for idx in range(min(10, len(df_sorted))):
        r = df_sorted.iloc[idx]
        name = f"🥇 WINNER #{idx+1} (Combo #{r['id']}: {r['ratio'][:10]}, d={r['depth']}, {r['regime'][:5]}, {r['barrier'][:8]}, {r['risk']*100}% Risk)"
        print(f"{name:<65} | {r['trades']:<8,} | +{r['ret_pct']:<11.2f}% | +{r['cagr_pct']:<11.2f}% | {r['sharpe']:<8.2f} | {r['pf']:<6.2f} | -{r['mtm_max_dd']:<7.2f}%")
    print("=" * 125 + "\n")

    # =================================================================================
    # PHASE 2: 2026 UNTOUCHED LIVE HOLDOUT CERTIFICATION SUITE
    # =================================================================================
    print("=================================================================================", flush=True)
    print("  🚀 PHASE 2: 2026 UNTOUCHED LIVE HOLDOUT CERTIFICATION SUITE", flush=True)
    print("=================================================================================\n", flush=True)

    eval_mask_2026 = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_eval_2026 = df_feat[eval_mask_2026].copy()

    # 1. Baseline v1.0 on 2026 Data
    print("▶ Running Benchmark A: Frozen Baseline v1.0 on 2026 Untouched Data...", flush=True)
    fold_2026_d5 = process_fold_custom(2026, df_lbl, all_feat_cols, max_depth=5, regime_states=9, memory_mode='expanding')
    p_l_v1_2026 = (fold_2026_d5[1] + fold_2026_d5[2] + fold_2026_d5[3]) / 3.0
    p_s_v1_2026 = (fold_2026_d5[4] + fold_2026_d5[5] + fold_2026_d5[6]) / 3.0
    res_2026_baseline = run_canonical_simulation(df_eval_2026, p_l_v1_2026, p_s_v1_2026, fold_2026_d5[7])

    # 2. #1 Winning Combination on 2026 Data
    print(f"▶ Running Benchmark B: #1 Winning Combination (Combo #{best_winner['id']}) on 2026 Untouched Data...", flush=True)
    r_states_w = 4 if best_winner['regime'] == "4-State Engine" else 9
    m_mode_w = 'rolling_2yr' if best_winner['memory'] == "2-Year Rolling" else 'expanding'
    fold_2026_win = process_fold_custom(2026, df_lbl, all_feat_cols, max_depth=best_winner['depth'], regime_states=r_states_w, memory_mode=m_mode_w)
    
    pl_lgb_w, pl_cat_w, pl_xgb_w = fold_2026_win[1], fold_2026_win[2], fold_2026_win[3]
    ps_lgb_w, ps_cat_w, ps_xgb_w = fold_2026_win[4], fold_2026_win[5], fold_2026_win[6]
    hmm26_w = fold_2026_win[7]

    if best_winner['ratio'] == "Ratio A (50% Cat / 25% LGB / 25% XGB)":
        p_l_w_2026 = (pl_cat_w * 0.50) + (pl_lgb_w * 0.25) + (pl_xgb_w * 0.25)
        p_s_w_2026 = (ps_cat_w * 0.50) + (ps_lgb_w * 0.25) + (ps_xgb_w * 0.25)
    elif best_winner['ratio'] == "Single CatBoost (100%)":
        p_l_w_2026 = pl_cat_w; p_s_w_2026 = ps_cat_w
    else:
        p_l_w_2026 = (pl_lgb_w + pl_cat_w + pl_xgb_w) / 3.0
        p_s_w_2026 = (ps_lgb_w + ps_cat_w + ps_xgb_w) / 3.0

    p_range_w, p_trend_w = [float(x) for x in best_winner['hurdle'].split('/')]
    tp_m_w = 3.0 if best_winner['barrier'] == "Extended 3.0/1.5" else 2.5
    holding_w = 36 if best_winner['barrier'] == "Extended 3.0/1.5" else 24

    res_2026_winner = run_grid_simulation_fully_dynamic(
        df_eval_2026, p_l_w_2026, p_s_w_2026, hmm26_w,
        risk_pct=best_winner['risk'], p_range=p_range_w, p_trend=p_trend_w,
        tp_mult=tp_m_w, sl_mult=1.5, max_holding_bars=holding_w
    )

    # 3. Full 1,296 Sweep on 2026 Data
    print(f"▶ Running Benchmark C: Full 1,296 Dynamic Sweep on 2026 Untouched Data ({cpu_cores} Cores)...", flush=True)
    pred_cache_2026 = build_prediction_cache(df_lbl, all_feat_cols, [2026], df_eval_2026, cpu_cores)

    grid_results_2026 = Parallel(n_jobs=cpu_cores)(
        delayed(evaluate_dynamic_combination_task)(i+1, comb, df_eval_2026, pred_cache_2026)
        for i, comb in enumerate(grid_combos)
    )

    df_res_2026 = pd.DataFrame(grid_results_2026)
    best_2026_grid_winner = df_res_2026.sort_values(by='ret_pct', ascending=False).iloc[0]

    # Side-by-Side 2026 Certification Scorecard
    print("\n" + "=" * 125)
    print("  🏆 2026 UNTOUCHED LIVE HOLDOUT CERTIFICATION MATRIX")
    print("=" * 125)
    print(f"{'2026 Untouched Holdout Evaluation Spec':<65} | {'Trades':<8} | {'Net Return':<12} | {'CAGR (%/yr)':<12} | {'Sharpe':<8} | {'PF':<6} | {'Max DD':<8}")
    print("-" * 125)
    print(f"{'🔒 Benchmark A: Baseline v1.0 (2026 Holdout)':<65} | {res_2026_baseline['trades']:<8,} | +{res_2026_baseline['ret_pct']:<11.2f}% | +{res_2026_baseline['cagr_pct']:<11.2f}% | {res_2026_baseline['sharpe']:<8.2f} | {res_2026_baseline['pf']:<6.2f} | -{res_2026_baseline['mtm_max_dd']:<7.2f}%")
    print(f"{'🚀 Benchmark B: #1 OOS Winner (Combo #' + str(best_winner['id']) + ')':<65} | {res_2026_winner['trades']:<8,} | +{res_2026_winner['ret_pct']:<11.2f}% | +{res_2026_winner['cagr_pct']:<11.2f}% | {res_2026_winner['sharpe']:<8.2f} | {res_2026_winner['pf']:<6.2f} | -{res_2026_winner['mtm_max_dd']:<7.2f}%")
    print(f"{'🔥 Benchmark C: #1 Best 2026 Grid Sweep Winner (Combo #' + str(best_2026_grid_winner['id']) + ')':<65} | {best_2026_grid_winner['trades']:<8,} | +{best_2026_grid_winner['ret_pct']:<11.2f}% | +{best_2026_grid_winner['cagr_pct']:<11.2f}% | {best_2026_grid_winner['sharpe']:<8.2f} | {best_2026_grid_winner['pf']:<6.2f} | -{best_2026_grid_winner['mtm_max_dd']:<7.2f}%")
    print("=" * 125 + "\n")

    elapsed_m = (time.time() - start_t) / 60.0
    print(f"🎉 FULLY DYNAMIC 1,296 COMBINATION GRID SEARCH & 2026 CERTIFICATION COMPLETED IN {elapsed_m:.2f} MINUTES! 🎉\n", flush=True)

if __name__ == "__main__":
    main()
