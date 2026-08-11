"""
Weight-Space Bucketing Research Protocol.
Categorizes weight combinations into 4 structural weight-space buckets:
1. LGBM-heavy (>=50%)
2. CatBoost-heavy (>=50%)
3. XGBoost-heavy (>=50%)
4. Balanced (25%-45% each)

Calculates Median Return, Mean Return, Median Sharpe, Median MDD for each bucket
across BOTH Historical 2018-2025 OOS Gauntlet and Untouched 2026 Forward Holdout.
"""

import os, sys, time
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector

def run_bucket_analysis():
    print("=================================================================================", flush=True)
    print("  🧪 WEIGHT-SPACE BUCKETING RESEARCH PROTOCOL (HISTORICAL OOS vs 2026 HOLDOUT)")
    print("=================================================================================", flush=True)
    print("  • Evaluating 4 Weight Buckets: LGBM-heavy, Cat-heavy, XGB-heavy, Balanced", flush=True)
    print("  • Comparing Median Return, Sharpe, MDD across 2018-2025 and 2026 Untouched Data\n", flush=True)

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
    df_lbl = tb_lab.label(df_feat)
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    eval_hist_m = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_hist = df_feat[eval_hist_m].copy()
    total_hist_bars = len(df_hist)

    eval_2026_m = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_2026 = df_feat[eval_2026_m].copy()
    total_2026_bars = len(df_2026)

    years_oos = list(range(2018, 2026))

    # Containers for Historical 2018-2025 OOS predictions
    p_lgb_hist_l = np.zeros(total_hist_bars); p_cat_hist_l = np.zeros(total_hist_bars); p_xgb_hist_l = np.zeros(total_hist_bars)
    p_lgb_hist_s = np.zeros(total_hist_bars); p_cat_hist_s = np.zeros(total_hist_bars); p_xgb_hist_s = np.zeros(total_hist_bars)
    hmm_hist = np.zeros(total_hist_bars)

    print("Generating Historical 2018-2025 Walk-Forward OOS predictions...", flush=True)

    for yr in years_oos:
        train_end_year = yr - 1
        train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
        test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

        df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
        df_te = df_lbl[test_m].copy()

        hmm_detector = HMMRegimeDetector()
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
                ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
                ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=42, thread_count=-1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
                ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

                ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
                ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=42, thread_count=-1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
                ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

                pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
                pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat[mask_te])[:, 1]
                pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat[mask_te])[:, 1]

                ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
                ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat[mask_te])[:, 1]
                ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat[mask_te])[:, 1]
            else:
                pl_lgb[mask_te] = 0.30; pl_cat[mask_te] = 0.30; pl_xgb[mask_te] = 0.30
                ps_lgb[mask_te] = 0.30; ps_cat[mask_te] = 0.30; ps_xgb[mask_te] = 0.30

        fold_eval_indices = [df_hist.index.get_loc(idx) for idx in df_te.index if idx in df_hist.index]
        p_lgb_hist_l[fold_eval_indices] = pl_lgb; p_cat_hist_l[fold_eval_indices] = pl_cat; p_xgb_hist_l[fold_eval_indices] = pl_xgb
        p_lgb_hist_s[fold_eval_indices] = ps_lgb; p_cat_hist_s[fold_eval_indices] = ps_cat; p_xgb_hist_s[fold_eval_indices] = ps_xgb
        hmm_hist[fold_eval_indices] = hmm_te

    # Containers for 2026 Untouched Holdout predictions
    print("Generating 2026 Untouched Holdout predictions...", flush=True)
    train_m_2026 = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    test_2026_m = (df_lbl.index >= "2026-01-01") & (df_lbl.index <= "2026-08-11")

    df_tr_26 = df_lbl[train_m_2026].dropna(subset=['label_dir_long']).copy()
    df_te_26 = df_lbl[test_2026_m].copy()

    hmm_detector_26 = HMMRegimeDetector()
    hmm_detector_26.fit(df_tr_26)
    hmm_tr_26 = hmm_detector_26.predict(df_tr_26)
    hmm_te_26 = hmm_detector_26.predict(df_te_26)

    tr_v_26 = df_tr_26['feat_vol_atr_pct'].values
    te_v_26 = df_te_26['feat_vol_atr_pct'].values

    v_tr_26 = np.zeros(len(tr_v_26), dtype=int); v_tr_26[tr_v_26 >= 33.33] = 1; v_tr_26[tr_v_26 >= 66.67] = 2
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 33.33] = 1; v_te_26[te_v_26 >= 66.67] = 2

    state_tr_26 = (hmm_tr_26 * 3) + v_tr_26
    state_te_26 = (hmm_te_26 * 3) + v_te_26

    X_tr_mat_26 = df_tr_26[all_feat_cols].values
    y_l_tr_26 = df_tr_26['label_dir_long'].values; y_s_tr_26 = df_tr_26['label_dir_short'].values
    X_te_mat_26 = df_te_26[all_feat_cols].values

    p_lgb_2026_l = np.zeros(total_2026_bars); p_cat_2026_l = np.zeros(total_2026_bars); p_xgb_2026_l = np.zeros(total_2026_bars)
    p_lgb_2026_s = np.zeros(total_2026_bars); p_cat_2026_s = np.zeros(total_2026_bars); p_xgb_2026_s = np.zeros(total_2026_bars)

    for s in range(9):
        mask_tr = (state_tr_26 == s); mask_te = (state_te_26 == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 30:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=42, thread_count=-1, verbose=False).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=42, thread_count=-1, verbose=False).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, n_jobs=-1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])

            p_lgb_2026_l[mask_te] = ml_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            p_cat_2026_l[mask_te] = ml_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            p_xgb_2026_l[mask_te] = ml_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]

            p_lgb_2026_s[mask_te] = ms_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            p_cat_2026_s[mask_te] = ms_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            p_xgb_2026_s[mask_te] = ms_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
        else:
            p_lgb_2026_l[mask_te] = 0.30; p_cat_2026_l[mask_te] = 0.30; p_xgb_2026_l[mask_te] = 0.30
            p_lgb_2026_s[mask_te] = 0.30; p_cat_2026_s[mask_te] = 0.30; p_xgb_2026_s[mask_te] = 0.30

    # Trade Simulator Helper
    pip_size = 0.0001
    def run_generic_sim(df_target, hmm_target, p_l, p_s):
        timestamps = df_target.index
        closes = df_target['close'].values; highs = df_target['high'].values; lows = df_target['low'].values; atrs = df_target['feat_vol_atr'].values
        hours = np.array([ts.hour for ts in timestamps])
        trading_window = ~((hours >= 13) & (hours <= 16))
        vol_pass = (df_target['feat_vol_atr_pct'].values >= 40.0)
        req_p_arr = np.where(hmm_target == 1.0, 0.42, 0.36)

        signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
        signals_sell = (p_s >= req_p_arr) & trading_window

        n_bars = len(df_target)
        trades = []; in_trade = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; current_equity = 10000.0; pending_order = None
        signals_arr = np.full(n_bars, "NONE", dtype=object)
        for i in range(n_bars):
            if signals_buy[i]: signals_arr[i] = "BUY"
            elif signals_sell[i]: signals_arr[i] = "SELL"

        for i in range(n_bars):
            timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

            if in_trade:
                t_log = trades[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                if not t_log['partial_taken'] and r_floating >= 1.5:
                    partial_lots = t_log['initial_lots'] * 0.5; t_log['active_lots'] -= partial_lots; t_log['partial_taken'] = True
                    partial_pips = (initial_sl_dist / pip_size) * 1.5
                    partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = 7.0 * partial_lots; partial_net = partial_gross - partial_comm
                    t_log['partial_pnl_usd'] = partial_net; current_equity += partial_net

                if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
                elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
                elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (0.3 * pip_size); exit_reason = 'stop_loss'
                elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (0.3 * pip_size); exit_reason = 'stop_loss'
                elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
                elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

                if stop_out:
                    in_trade = False
                    rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    rem_lots = t_log['active_lots']; rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = 7.0 * rem_lots; rem_net = rem_gross - rem_comm
                    total_trade_net = rem_net + t_log.get('partial_pnl_usd', 0.0)
                    t_log['exit_time'] = timestamp; t_log['exit_price'] = exit_price; t_log['exit_reason'] = exit_reason; t_log['pnl_pips'] = rem_pips; t_log['pnl_usd'] = total_trade_net; t_log['status'] = 'closed'
                    current_equity += rem_net

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
                        risk_amt = current_equity * 0.005; lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)
                        trades.append({'trade_id': len(trades) + 1, 'symbol': 'EURUSD', 'direction': direction, 'entry_time': entry_time, 'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'})

            if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
                sig = signals_arr[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
                pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

        closed = [t for t in trades if t['status'] == 'closed']
        if not closed: return 0.0, 0.0, 0.0, 0
        pnls = [t['pnl_usd'] for t in closed]
        net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0
        eq_curve = [10000.0]
        for p in pnls: eq_curve.append(eq_curve[-1] + p)
        eq_arr = np.array(eq_curve); peaks = np.maximum.accumulate(eq_arr); dds = (eq_arr - peaks) / peaks * 100.0; max_dd = abs(np.min(dds))
        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0
        return ret_pct, sharpe, max_dd, len(closed)

    # Generate 500 Random Weights on 3D Simplex
    np.random.seed(42)
    weights_matrix = np.random.dirichlet(np.ones(3), size=500)

    def classify_bucket(w1, w2, w3):
        if w1 >= 0.50: return "LGBM-heavy (>=50%)"
        elif w2 >= 0.50: return "CatBoost-heavy (>=50%)"
        elif w3 >= 0.50: return "XGBoost-heavy (>=50%)"
        elif (0.25 <= w1 <= 0.45) and (0.25 <= w2 <= 0.45) and (0.25 <= w3 <= 0.45): return "Balanced (25-45% each)"
        else: return "Other Mixed"

    records_hist = []
    records_2026 = []

    print("Running Bucket Simulations across 500 Weight Combinations...", flush=True)

    for idx, (w1, w2, w3) in enumerate(weights_matrix):
        b_name = classify_bucket(w1, w2, w3)

        # Historical 2018-2025 OOS
        p_hist_l = (w1 * p_lgb_hist_l) + (w2 * p_cat_hist_l) + (w3 * p_xgb_hist_l)
        p_hist_s = (w1 * p_lgb_hist_s) + (w2 * p_cat_hist_s) + (w3 * p_xgb_hist_s)
        ret_h, sh_h, dd_h, n_h = run_generic_sim(df_hist, hmm_hist, p_hist_l, p_hist_s)
        records_hist.append({"bucket": b_name, "return": ret_h, "sharpe": sh_h, "mdd": dd_h, "trades": n_h})

        # 2026 Untouched Holdout
        p_26_l = (w1 * p_lgb_2026_l) + (w2 * p_cat_2026_l) + (w3 * p_xgb_2026_l)
        p_26_s = (w1 * p_lgb_2026_s) + (w2 * p_cat_2026_s) + (w3 * p_xgb_2026_s)
        ret_26, sh_26, dd_26, n_26 = run_generic_sim(df_2026, hmm_te_26, p_26_l, p_26_s)
        records_2026.append({"bucket": b_name, "return": ret_26, "sharpe": sh_26, "mdd": dd_26, "trades": n_26})

    df_res_hist = pd.DataFrame(records_hist)
    df_res_2026 = pd.DataFrame(records_2026)

    buckets_order = ["Balanced (25-45% each)", "LGBM-heavy (>=50%)", "CatBoost-heavy (>=50%)", "XGBoost-heavy (>=50%)", "Other Mixed"]

    total_elapsed = time.time() - t0

    print("\n=========================================================================================================================================", flush=True)
    print(f"  🏆 WEIGHT-SPACE BUCKET RESEARCH SCORECARD (TOTAL TIME: {total_elapsed:.1f}s)", flush=True)
    print("=========================================================================================================================================", flush=True)
    print(f"PART 1: HISTORICAL 8-YEAR OOS GAUNTLET (2018-2025 EURUSD H1):", flush=True)
    print(f"{'Weight-Space Bucket':<26} | {'Count':<5} | {'Median Return (%)':<18} | {'Mean Return (%)':<16} | {'Median Sharpe':<14} | {'Median MDD (%)':<14}", flush=True)
    print("-" * 105, flush=True)

    for b in buckets_order:
        sub = df_res_hist[df_res_hist['bucket'] == b]
        if len(sub) == 0: continue
        med_r = sub['return'].median(); mean_r = sub['return'].mean(); med_s = sub['sharpe'].median(); med_dd = sub['mdd'].median()
        print(f"{b:<26} | {len(sub):<5} | +{med_r:<17.2f}% | +{mean_r:<15.2f}% | {med_s:<14.2f} | {med_dd:<14.2f}%", flush=True)

    print("\n" + "=" * 105, flush=True)
    print(f"PART 2: UNTOUCHED 2026 FORWARD HOLDOUT (JAN 1 - AUG 11, 2026):", flush=True)
    print(f"{'Weight-Space Bucket':<26} | {'Count':<5} | {'Median Return (%)':<18} | {'Mean Return (%)':<16} | {'Median Sharpe':<14} | {'Median MDD (%)':<14}", flush=True)
    print("-" * 105, flush=True)

    for b in buckets_order:
        sub = df_res_2026[df_res_2026['bucket'] == b]
        if len(sub) == 0: continue
        med_r = sub['return'].median(); mean_r = sub['return'].mean(); med_s = sub['sharpe'].median(); med_dd = sub['mdd'].median()
        print(f"{b:<26} | {len(sub):<5} | +{med_r:<17.2f}% | +{mean_r:<15.2f}% | {med_s:<14.2f} | {med_dd:<14.2f}%", flush=True)

    print("=========================================================================================================================================", flush=True)

if __name__ == "__main__":
    run_bucket_analysis()
