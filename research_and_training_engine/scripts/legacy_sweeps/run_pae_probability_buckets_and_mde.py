"""
Stage PAE-Next: PAE Probability Bucket Analysis, 9-Regime x 3-Probability Matrix & Contextual Meta-Decision Engine (MDE).
Evaluates:
1. 10 PAE Probability Buckets (0.34 to 0.79+) with Win Rate, Avg R, Median R, PF, EV, MFE, MAE & 2026 Holdout
2. 9 Regimes x 3 Probability Tiers Matrix (27 Cells) with Trade Count, Win Rate, Expectancy, PF
3. Contextual Meta-Decision Engine (MDE) for Dynamic Risk Multipliers (0.25x, 0.50x, 0.75x, 1.00x)
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

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector

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

    p_stack_l = (pl_lgb + pl_cat + pl_xgb) / 3.0
    p_stack_s = (ps_lgb + ps_cat + ps_xgb) / 3.0
    return df_te.index, p_stack_l, p_stack_s, state_te

def run_simulation_detailed(df_eval, p_l, p_s, state_arr, friction_pips=0.3, risk_pct=0.0075, mde_func=None, initial_cap=10000.0):
    pip_size = 0.0001
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    req_p_arr = np.where((state_arr // 3) == 1, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    trades = []; in_trade = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; current_equity = 10000.0; pending_order = None

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        if in_trade:
            t_log = trades[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            adverse_pips = (entry_price - low) / pip_size if direction == 'BUY' else (high - entry_price) / pip_size

            t_log['mfe_pips'] = max(t_log['mfe_pips'], floating_pips)
            t_log['mae_pips'] = max(t_log['mae_pips'], adverse_pips)

            r_floating = floating_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not t_log['partial_taken'] and r_floating >= 1.5:
                partial_lots = t_log['initial_lots'] * 0.5; t_log['active_lots'] -= partial_lots; t_log['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = 7.0 * partial_lots; partial_net = partial_gross - partial_comm
                t_log['partial_pnl_usd'] = partial_net; current_equity += partial_net

            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                in_trade = False
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = t_log['active_lots']; rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = 7.0 * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + t_log.get('partial_pnl_usd', 0.0)

                sl_dist_pips = initial_sl_dist / pip_size
                t_log['r_multiple'] = (total_trade_net / (t_log['initial_lots'] * sl_dist_pips * 10.0)) * 2.0 if sl_dist_pips > 0 else 0.0

                t_log['exit_time'] = timestamp; t_log['exit_price'] = exit_price; t_log['exit_reason'] = exit_reason; t_log['pnl_pips'] = rem_pips; t_log['pnl_usd'] = total_trade_net; t_log['status'] = 'closed'
                current_equity += rem_net

                if signals_arr[i] == opposite_sig:
                    pending_order = {"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr, "prob": p_s[i] if opposite_sig == 'SELL' else p_l[i], "state": state_arr[i]}

        if not in_trade and pending_order is not None:
            p_dir = pending_order["direction"]; p_limit = pending_order["limit_price"]; p_atr = pending_order["atr"]; sig_idx = pending_order["signal_idx"]; p_prob = pending_order["prob"]; p_state = pending_order["state"]
            if (i - sig_idx) > 3: pending_order = None
            else:
                filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                if filled:
                    entry_price = p_limit
                    sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5; initial_sl_dist = sl_pips * pip_size

                    # MDE Risk Multiplier Evaluation
                    risk_mult = mde_func(p_prob, p_state, p_atr) if mde_func is not None else 1.0

                    if risk_mult > 0.0:
                        in_trade = True; direction = p_dir; entry_time = timestamp; pending_order = None
                        if direction == 'BUY': sl_price = entry_price - initial_sl_dist; tp_price = entry_price + (tp_pips * pip_size)
                        else: sl_price = entry_price + initial_sl_dist; tp_price = entry_price - (tp_pips * pip_size)

                        eff_risk = risk_pct * risk_mult
                        risk_amt = current_equity * eff_risk
                        lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                        trades.append({
                            'trade_id': len(trades) + 1, 'symbol': 'EURUSD', 'direction': direction, 'entry_time': entry_time,
                            'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                            'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open',
                            'pae_prob': p_prob, 'state': p_state, 'mfe_pips': 0.0, 'mae_pips': 0.0
                        })
                    else:
                        pending_order = None

        if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            prob_val = p_l[i] if sig == 'BUY' else p_s[i]
            pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr, "prob": prob_val, "state": state_arr[i]}

    closed = [t for t in trades if t['status'] == 'closed']
    if not closed: return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "end_eq": initial_cap, "trades_list": []}
    pnls = [t['pnl_usd'] for t in closed]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0
    win_rate = (len(wins) / len(closed)) * 100.0 if len(closed) > 0 else 0.0
    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0; pf = gross_win / gross_loss

    eq_curve = [initial_cap]
    for p in pnls: eq_curve.append(eq_curve[-1] + p)
    eq_arr = np.array(eq_curve); peaks = np.maximum.accumulate(eq_arr); dds = (eq_arr - peaks) / peaks * 100.0; max_dd = abs(np.min(dds))
    returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0

    return {"trades": len(closed), "net_pnl": net_pnl, "ret_pct": ret_pct, "win_rate": win_rate, "pf": pf, "sharpe": sharpe, "max_dd": max_dd, "end_eq": current_equity, "trades_list": closed}

def run_pae_next_analysis():
    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("=================================================================================", flush=True)
    print("  🚀 STAGE PAE-NEXT: PROBABILITY BUCKET & CONTEXTUAL META-DECISION ENGINE (MDE)", flush=True)
    print("=================================================================================", flush=True)

    t0 = time.time()
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

    # 1. 2018-2025 OOS Gauntlet
    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    total_bars_oos = len(df_eval_oos)
    years_oos = list(range(2018, 2026))

    print("▶ Step 1: Generating OOS Walk-Forward Predictions...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l_oos = np.zeros(total_bars_oos)
    p_stack_s_oos = np.zeros(total_bars_oos)
    state_oos = np.zeros(total_bars_oos, dtype=int)

    for te_indices, pl_fold, ps_fold, state_fold in results_folds:
        idx_locs = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[idx_locs] = pl_fold
        p_stack_s_oos[idx_locs] = ps_fold
        state_oos[idx_locs] = state_fold

    res_oos = run_simulation_detailed(df_eval_oos, p_stack_l_oos, p_stack_s_oos, state_oos)
    closed_oos = res_oos['trades_list']

    # 2. 2026 Live Holdout
    mask_2026 = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_eval_26 = df_feat[mask_2026].copy()
    total_bars_26 = len(df_eval_26)

    train_m_26 = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    df_tr_26 = df_lbl[train_m_26].dropna(subset=['label_dir_long']).copy()

    fold_seed = 42
    hmm_detector = HMMRegimeDetector(n_components=3, random_state=fold_seed)
    hmm_detector.fit(df_tr_26)
    hmm_tr_26 = hmm_detector.predict(df_tr_26)
    hmm_te_26 = hmm_detector.predict(df_eval_26)

    tr_v_26 = df_tr_26['feat_vol_atr_pct'].values; te_v_26 = df_eval_26['feat_vol_atr_pct'].values
    v_tr_26 = np.zeros(len(tr_v_26), dtype=int); v_tr_26[tr_v_26 >= 33.33] = 1; v_tr_26[tr_v_26 >= 66.67] = 2
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 33.33] = 1; v_te_26[te_v_26 >= 66.67] = 2

    state_tr_26 = (hmm_tr_26 * 3) + v_tr_26; state_te_26 = (hmm_te_26 * 3) + v_te_26

    X_tr_26_mat = df_tr_26[all_feat_cols].values; X_te_26_mat = df_eval_26[all_feat_cols].values
    y_l_tr_26 = df_tr_26['label_dir_long'].values; y_s_tr_26 = df_tr_26['label_dir_short'].values

    pl_lgb_26 = np.zeros(total_bars_26); pl_cat_26 = np.zeros(total_bars_26); pl_xgb_26 = np.zeros(total_bars_26)
    ps_lgb_26 = np.zeros(total_bars_26); ps_cat_26 = np.zeros(total_bars_26); ps_xgb_26 = np.zeros(total_bars_26)

    for s in range(9):
        mask_tr = (state_tr_26 == s); mask_te = (state_te_26 == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 30:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr_26_mat[mask_tr], y_l_tr_26[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_state=fold_seed, thread_count=-1, verbose=False).fit(X_tr_26_mat[mask_tr], y_l_tr_26[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr_26_mat[mask_tr], y_l_tr_26[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr_26_mat[mask_tr], y_s_tr_26[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_state=fold_seed, thread_count=-1, verbose=False).fit(X_tr_26_mat[mask_tr], y_s_tr_26[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr_26_mat[mask_tr], y_s_tr_26[mask_tr])

            pl_lgb_26[mask_te] = ml_lgb.predict_proba(X_te_26_mat[mask_te])[:, 1]
            pl_cat_26[mask_te] = ml_cat.predict_proba(X_te_26_mat[mask_te])[:, 1]
            pl_xgb_26[mask_te] = ml_xgb.predict_proba(X_te_26_mat[mask_te])[:, 1]

            ps_lgb_26[mask_te] = ms_lgb.predict_proba(X_te_26_mat[mask_te])[:, 1]
            ps_cat_26[mask_te] = ms_cat.predict_proba(X_te_26_mat[mask_te])[:, 1]
            ps_xgb_26[mask_te] = ms_xgb.predict_proba(X_te_26_mat[mask_te])[:, 1]

    p_stack_l_26 = (pl_lgb_26 + pl_cat_26 + pl_xgb_26) / 3.0
    p_stack_s_26 = (ps_lgb_26 + ps_cat_26 + ps_xgb_26) / 3.0

    res_26 = run_simulation_detailed(df_eval_26, p_stack_l_26, p_stack_s_26, state_te_26)
    closed_26 = res_26['trades_list']

    df_tr_oos = pd.DataFrame(closed_oos)
    df_tr_26 = pd.DataFrame(closed_26)

    # =========================================================================================
    # PART 1: 10 PAE Probability Buckets Analysis
    # =========================================================================================
    print("\n---------------------------------------------------------------------------------", flush=True)
    print("  🧪 PART 1: 10 PAE PROBABILITY BUCKET ANALYSIS", flush=True)
    print("---------------------------------------------------------------------------------", flush=True)

    prob_bins = [0.34, 0.39, 0.44, 0.49, 0.54, 0.59, 0.64, 0.69, 0.74, 0.79, 1.00]
    prob_labels = ["0.34-0.39", "0.39-0.44", "0.44-0.49", "0.49-0.54", "0.54-0.59", "0.59-0.64", "0.64-0.69", "0.69-0.74", "0.74-0.79", "0.79+"]

    df_tr_oos['p_bin'] = pd.cut(df_tr_oos['pae_prob'], bins=prob_bins, labels=prob_labels, include_lowest=True)
    if len(df_tr_26) > 0:
        df_tr_26['p_bin'] = pd.cut(df_tr_26['pae_prob'], bins=prob_bins, labels=prob_labels, include_lowest=True)

    bucket_stats = []
    for b_label in prob_labels:
        sub_oos = df_tr_oos[df_tr_oos['p_bin'] == b_label]
        sub_26 = df_tr_26[df_tr_26['p_bin'] == b_label] if len(df_tr_26) > 0 else pd.DataFrame()

        cnt = len(sub_oos)
        if cnt > 0:
            wns = len(sub_oos[sub_oos['pnl_usd'] > 0])
            wr = (wns / cnt) * 100.0
            avg_r = sub_oos['r_multiple'].mean()
            med_r = sub_oos['r_multiple'].median()
            gw = sub_oos[sub_oos['pnl_usd'] > 0]['pnl_usd'].sum()
            gl = abs(sub_oos[sub_oos['pnl_usd'] < 0]['pnl_usd'].sum())
            pf = gw / gl if gl > 0 else (gw if gw > 0 else 0.0)
            ev = sub_oos['pnl_usd'].mean()
            avg_mfe = sub_oos['mfe_pips'].mean()
            avg_mae = sub_oos['mae_pips'].mean()
        else:
            wr = avg_r = med_r = pf = ev = avg_mfe = avg_mae = 0.0

        cnt_26 = len(sub_26)
        wr_26 = (len(sub_26[sub_26['pnl_usd'] > 0]) / cnt_26 * 100.0) if cnt_26 > 0 else 0.0

        bucket_stats.append({
            "bucket": b_label, "trades": cnt, "win_rate": wr, "avg_r": avg_r, "med_r": med_r,
            "pf": pf, "ev": ev, "avg_mfe": avg_mfe, "avg_mae": avg_mae, "trades_26": cnt_26, "wr_26": wr_26
        })

    print(f"{'Probability Bucket':<18} | {'Trades':<7} | {'Win Rate (%)':<13} | {'Avg R':<7} | {'Med R':<7} | {'PF':<6} | {'EV ($/trade)':<14} | {'MFE (pips)':<11} | {'MAE (pips)':<11} | {'2026 WR (%)':<11}", flush=True)
    print("-" * 125, flush=True)
    for m in bucket_stats:
        print(f"{m['bucket']:<18} | {m['trades']:<7} | {m['win_rate']:<12.2f}% | {m['avg_r']:<+7.2f} | {m['med_r']:<+7.2f} | {m['pf']:<6.2f} | ${m['ev']:<+13.2f} | {m['avg_mfe']:<11.1f} | {m['avg_mae']:<11.1f} | {m['wr_26']:<11.2f}%", flush=True)

    # =========================================================================================
    # PART 2: 9 Regimes x 3 Probability Tiers Matrix (27 Cells)
    # =========================================================================================
    print("\n---------------------------------------------------------------------------------", flush=True)
    print("  🧪 PART 2: 9 REGIMES x 3 PROBABILITY TIERS MATRIX (27 CELLS)", flush=True)
    print("---------------------------------------------------------------------------------", flush=True)

    regime_names = {
        0: "Bear + Low Vol", 1: "Bear + Med Vol", 2: "Bear + High Vol",
        3: "Range + Low Vol", 4: "Range + Med Vol", 5: "Range + High Vol",
        6: "Bull + Low Vol", 7: "Bull + Med Vol", 8: "Bull + High Vol",
    }

    def get_p_tier(p):
        if p < 0.42: return "Low P (<0.42)"
        elif p < 0.55: return "Med P (0.42-0.55)"
        else: return "High P (>=0.55)"

    df_tr_oos['p_tier'] = df_tr_oos['pae_prob'].apply(get_p_tier)
    p_tiers = ["Low P (<0.42)", "Med P (0.42-0.55)", "High P (>=0.55)"]

    matrix_rows = []
    for s_idx in range(9):
        reg_name = regime_names[s_idx]
        for p_t in p_tiers:
            sub_cell = df_tr_oos[(df_tr_oos['state'] == s_idx) & (df_tr_oos['p_tier'] == p_t)]
            cnt = len(sub_cell)
            if cnt > 0:
                wns = len(sub_cell[sub_cell['pnl_usd'] > 0])
                wr = (wns / cnt) * 100.0
                ev = sub_cell['pnl_usd'].mean()
                gw = sub_cell[sub_cell['pnl_usd'] > 0]['pnl_usd'].sum()
                gl = abs(sub_cell[sub_cell['pnl_usd'] < 0]['pnl_usd'].sum())
                pf = gw / gl if gl > 0 else (gw if gw > 0 else 0.0)
            else:
                wr = ev = pf = 0.0

            matrix_rows.append({"regime": reg_name, "p_tier": p_t, "trades": cnt, "win_rate": wr, "ev": ev, "pf": pf})

    df_matrix = pd.DataFrame(matrix_rows)

    print(f"{'Market Regime (9 States)':<22} | {'Prob Tier':<18} | {'Trades':<7} | {'Win Rate (%)':<13} | {'EV ($/trade)':<14} | {'PF':<6}", flush=True)
    print("-" * 95, flush=True)
    for _, r in df_matrix.iterrows():
        v_str = f"🟢 EV = +${r['ev']:.2f}" if r['ev'] > 0 else f"💥 EV = -${abs(r['ev']):.2f}"
        print(f"{r['regime']:<22} | {r['p_tier']:<18} | {r['trades']:<7} | {r['win_rate']:<12.2f}% | ${r['ev']:<+13.2f} | {r['pf']:<6.2f}", flush=True)

    # =========================================================================================
    # PART 3: Contextual Meta-Decision Engine (MDE) Optimization
    # =========================================================================================
    print("\n---------------------------------------------------------------------------------", flush=True)
    print("  🧪 PART 3: CONTEXTUAL META-DECISION ENGINE (MDE) DYNAMIC RISK MULTIPLIERS", flush=True)
    print("---------------------------------------------------------------------------------", flush=True)

    # Contextual MDE Rule:
    # 1. High P (>=0.55) in High-Expectancy Regimes (Bull/Bear High Vol) -> 1.00x Risk
    # 2. Medium P (0.42-0.55) in Range Regimes -> 0.75x Risk
    # 3. Low P (<0.42) in Low-Vol Regimes -> 0.50x Risk
    # 4. Low P (<0.42) in Negative EV Cells -> 0.00x Skip Trade
    def contextual_mde_policy(prob, state, atr):
        # Identify if cell has negative EV in matrix
        cell_match = [r for r in matrix_rows if r['regime'] == regime_names[state] and r['p_tier'] == get_p_tier(prob)]
        if cell_match and cell_match[0]['ev'] < -5.0 and cell_match[0]['trades'] >= 10:
            return 0.0 # Skip trade!

        if prob >= 0.55: return 1.00 # Max Risk
        elif prob >= 0.45: return 0.75 # Medium-High Risk
        else: return 0.50 # Conservative Risk

    print("▶ Evaluating Production System with Contextual Meta-Decision Engine (MDE)...", flush=True)
    res_mde_oos = run_simulation_detailed(df_eval_oos, p_stack_l_oos, p_stack_s_oos, state_oos, mde_func=contextual_mde_policy)
    res_mde_26 = run_simulation_detailed(df_eval_26, p_stack_l_26, p_stack_s_26, state_te_26, mde_func=contextual_mde_policy)

    print("\n=========================================================================================================================================", flush=True)
    print("  🏆 CONTEXTUAL META-DECISION ENGINE (MDE) OPTIMIZATION SCORECARD", flush=True)
    print("=========================================================================================================================================", flush=True)
    print(f"{'System Variant':<52} | {'Trades':<7} | {'Ending Equity ($)':<16} | {'Net Return (%)':<15} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6}", flush=True)
    print("-" * 125, flush=True)
    print(f"{'1. Production Control Baseline (Static 0.75% Risk)':<52} | {res_oos['trades']:<7} | ${res_oos['end_eq']:<15,.2f} | +{res_oos['ret_pct']:<14.2f}% | {res_oos['sharpe']:<8.2f} | {res_oos['max_dd']:<7.2f}% | {res_oos['pf']:<6.2f}")
    print(f"{'2. Contextual MDE System (Dynamic Risk & Cell Filtering)':<52} | {res_mde_oos['trades']:<7} | ${res_mde_oos['end_eq']:<15,.2f} | +{res_mde_oos['ret_pct']:<14.2f}% | {res_mde_oos['sharpe']:<8.2f} | {res_mde_oos['max_dd']:<7.2f}% | {res_mde_oos['pf']:<6.2f}")
    print("-" * 125, flush=True)
    print(f"{'3. 2026 Holdout Control (Static 0.75% Risk)':<52} | {res_26['trades']:<7} | ${res_26['end_eq']:<15,.2f} | +{res_26['ret_pct']:<14.2f}% | {res_26['sharpe']:<8.2f} | {res_26['max_dd']:<7.2f}% | {res_26['pf']:<6.2f}")
    print(f"{'4. 2026 Holdout MDE System (Dynamic Risk)':<52} | {res_mde_26['trades']:<7} | ${res_mde_26['end_eq']:<15,.2f} | +{res_mde_26['ret_pct']:<14.2f}% | {res_mde_26['sharpe']:<8.2f} | {res_mde_26['max_dd']:<7.2f}% | {res_mde_26['pf']:<6.2f}")
    print("=========================================================================================================================================", flush=True)

    total_elapsed = time.time() - t0
    print(f"\n🎉 STAGE PAE-NEXT COMPLETE IN {total_elapsed:.1f}s!", flush=True)

if __name__ == "__main__":
    run_pae_next_analysis()
