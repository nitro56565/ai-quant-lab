"""
Comparison of 100% Untouched 2026 Holdout (Jan 1 - Aug 11, 2026) under:
1. 0.50% Risk per Trade (1st Preference Baseline)
2. 0.75% Risk per Trade (2nd Preference High-Growth)
"""

import os, sys, time, warnings
warnings.filterwarnings("ignore")

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

def run_2026_risk_comparison():
    print("=================================================================================", flush=True)
    print("  🔬 2026 HOLDOUT RISK ALLOCATION COMPARISON (0.50% VS 0.75% RISK/TRADE)", flush=True)
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

    # Fit Model on Full Historical 2014-2025 Data
    df_tr_full = df_lbl[(df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")].dropna(subset=['label_dir_long']).copy()
    mask_2026 = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_2026 = df_feat[mask_2026].copy()
    h1_2026 = len(df_2026)

    fold_seed = 42
    np.random.seed(fold_seed)
    hmm_detector = HMMRegimeDetector(n_components=3, random_state=fold_seed)
    hmm_detector.fit(df_tr_full)
    hmm_tr_f = hmm_detector.predict(df_tr_full)
    hmm_2026 = hmm_detector.predict(df_2026)

    tr_v_f = df_tr_full['feat_vol_atr_pct'].values; te_v_26 = df_2026['feat_vol_atr_pct'].values
    v_tr_f = np.zeros(len(tr_v_f), dtype=int); v_tr_f[tr_v_f >= 33.33] = 1; v_tr_f[tr_v_f >= 66.67] = 2
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 33.33] = 1; v_te_26[te_v_26 >= 66.67] = 2

    state_tr_f = (hmm_tr_f * 3) + v_tr_f
    state_te_26 = (hmm_2026 * 3) + v_te_26

    X_tr_f_mat = df_tr_full[all_feat_cols].values
    y_l_tr_f = df_tr_full['label_dir_long'].values; y_s_tr_f = df_tr_full['label_dir_short'].values
    X_2026_mat = df_2026[all_feat_cols].values

    pl_lgb_26 = np.zeros(h1_2026); pl_cat_26 = np.zeros(h1_2026); pl_xgb_26 = np.zeros(h1_2026)
    ps_lgb_26 = np.zeros(h1_2026); ps_cat_26 = np.zeros(h1_2026); ps_xgb_26 = np.zeros(h1_2026)

    for s in range(9):
        mask_tr = (state_tr_f == s); mask_te = (state_te_26 == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 30:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_f_mat[mask_tr], y_l_tr_f[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_f_mat[mask_tr], y_l_tr_f[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_f_mat[mask_tr], y_l_tr_f[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_f_mat[mask_tr], y_s_tr_f[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_f_mat[mask_tr], y_s_tr_f[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_f_mat[mask_tr], y_s_tr_f[mask_tr])

            pl_lgb_26[mask_te] = ml_lgb.predict_proba(X_2026_mat[mask_te])[:, 1]
            pl_cat_26[mask_te] = ml_cat.predict_proba(X_2026_mat[mask_te])[:, 1]
            pl_xgb_26[mask_te] = ml_xgb.predict_proba(X_2026_mat[mask_te])[:, 1]

            ps_lgb_26[mask_te] = ms_lgb.predict_proba(X_2026_mat[mask_te])[:, 1]
            ps_cat_26[mask_te] = ms_cat.predict_proba(X_2026_mat[mask_te])[:, 1]
            ps_xgb_26[mask_te] = ms_xgb.predict_proba(X_2026_mat[mask_te])[:, 1]

    p_stack_l_26 = (pl_lgb_26 + pl_cat_26 + pl_xgb_26) / 3.0
    p_stack_s_26 = (ps_lgb_26 + ps_cat_26 + ps_xgb_26) / 3.0

    pip_size = 0.0001
    ts_26 = df_2026.index; cl_26 = df_2026['close'].values; hi_26 = df_2026['high'].values; lo_26 = df_2026['low'].values; atr_26 = df_2026['feat_vol_atr'].values
    hr_26 = np.array([ts.hour for ts in ts_26])
    tw_26 = ~((hr_26 >= 13) & (hr_26 <= 16))
    vp_26 = (df_2026['feat_vol_atr_pct'].values >= 40.0)
    req_p_26 = np.where(hmm_2026 == 1.0, 0.42, 0.36)

    sig_b_26 = (p_stack_l_26 >= req_p_26) & vp_26 & tw_26
    sig_s_26 = (p_stack_s_26 >= req_p_26) & tw_26

    def run_sim_2026(risk_pct):
        trades_26 = []; in_trade_26 = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; current_equity_26 = 10000.0; pending_order = None
        signals_arr_26 = np.full(h1_2026, "NONE", dtype=object)
        for i in range(h1_2026):
            if sig_b_26[i]: signals_arr_26[i] = "BUY"
            elif sig_s_26[i]: signals_arr_26[i] = "SELL"

        for i in range(h1_2026):
            timestamp = ts_26[i]; close = cl_26[i]; high = hi_26[i]; low = lo_26[i]; atr = atr_26[i] if not np.isnan(atr_26[i]) else 0.0012

            if in_trade_26:
                t_log = trades_26[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                if not t_log['partial_taken'] and r_floating >= 1.5:
                    partial_lots = t_log['initial_lots'] * 0.5; t_log['active_lots'] -= partial_lots; t_log['partial_taken'] = True
                    partial_pips = (initial_sl_dist / pip_size) * 1.5
                    partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = 7.0 * partial_lots; partial_net = partial_gross - partial_comm
                    t_log['partial_pnl_usd'] = partial_net; current_equity_26 += partial_net

                if signals_arr_26[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
                elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
                elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (0.3 * pip_size); exit_reason = 'stop_loss'
                elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (0.3 * pip_size); exit_reason = 'stop_loss'
                elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
                elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

                if stop_out:
                    in_trade_26 = False
                    rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    rem_lots = t_log['active_lots']; rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = 7.0 * rem_lots; rem_net = rem_gross - rem_comm
                    total_trade_net = rem_net + t_log.get('partial_pnl_usd', 0.0)
                    t_log['exit_time'] = timestamp; t_log['exit_price'] = exit_price; t_log['exit_reason'] = exit_reason; t_log['pnl_pips'] = rem_pips; t_log['pnl_usd'] = total_trade_net; t_log['status'] = 'closed'
                    current_equity_26 += rem_net

                    if signals_arr_26[i] == opposite_sig:
                        pending_order = {"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr}

            if not in_trade_26 and pending_order is not None:
                p_dir = pending_order["direction"]; p_limit = pending_order["limit_price"]; p_atr = pending_order["atr"]; sig_idx = pending_order["signal_idx"]
                if (i - sig_idx) > 3: pending_order = None
                else:
                    filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                    if filled:
                        in_trade_26 = True; direction = p_dir; entry_time = timestamp; entry_price = p_limit; pending_order = None
                        sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5; initial_sl_dist = sl_pips * pip_size
                        if direction == 'BUY': sl_price = entry_price - initial_sl_dist; tp_price = entry_price + (tp_pips * pip_size)
                        else: sl_price = entry_price + initial_sl_dist; tp_price = entry_price - (tp_pips * pip_size)
                        risk_amt = current_equity_26 * risk_pct; lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)
                        trades_26.append({'trade_id': len(trades_26) + 1, 'symbol': 'EURUSD', 'direction': direction, 'entry_time': entry_time, 'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'})

        if not in_trade_26 and pending_order is None and signals_arr_26[i] in ('BUY', 'SELL'):
            sig = signals_arr_26[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

        closed_26 = [t for t in trades_26 if t['status'] == 'closed']
        pnls_26 = [t['pnl_usd'] for t in closed_26]
        wins_26 = [p for p in pnls_26 if p > 0]; losses_26 = [p for p in pnls_26 if p < 0]
        net_pnl_26 = sum(pnls_26); ret_pct_26 = (net_pnl_26 / 10000.0) * 100.0
        gross_win_26 = sum(wins_26) if wins_26 else 0.0; gross_loss_26 = abs(sum(losses_26)) if losses_26 else 1.0; pf_26 = gross_win_26 / gross_loss_26

        eq_curve_26 = [10000.0]
        for p in pnls_26: eq_curve_26.append(eq_curve_26[-1] + p)
        eq_arr_26 = np.array(eq_curve_26); peaks_26 = np.maximum.accumulate(eq_arr_26); dds_26 = (eq_arr_26 - peaks_26) / peaks_26 * 100.0; max_dd_26 = abs(np.min(dds_26))
        returns_26 = np.diff(eq_arr_26) / eq_arr_26[:-1]
        sharpe_26 = (np.mean(returns_26) / np.std(returns_26)) * np.sqrt(252 * 24) if np.std(returns_26) > 0 else 0.0
        return {"trades": len(closed_26), "net_pnl": net_pnl_26, "ret_pct": ret_pct_26, "sharpe": sharpe_26, "max_dd": max_dd_26, "pf": pf_26}

    m_2026_050 = run_sim_2026(0.0050)
    m_2026_075 = run_sim_2026(0.0075)

    total_elapsed = time.time() - t0

    print("=========================================================================================================================================")
    print(f"  🏆 2026 HOLDOUT RISK COMPARISON SCORECARD (TOTAL TIME: {total_elapsed:.1f}s)")
    print("=========================================================================================================================================")
    print(f"{'2026 Holdout Risk Allocation Tier':<52} | {'Trades':<7} | {'Net Return (%)':<15} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6}")
    print("-" * 115)
    print(f"{'0.50% Risk per Trade (1st Preference Champion)':<52} | {m_2026_050['trades']:<7} | +{m_2026_050['ret_pct']:<14.2f}% | {m_2026_050['sharpe']:<8.2f} | {m_2026_050['max_dd']:<7.2f}% | {m_2026_050['pf']:<6.2f}")
    print(f"{'0.75% Risk per Trade (2nd Preference High-Growth)':<52} | {m_2026_075['trades']:<7} | +{m_2026_075['ret_pct']:<14.2f}% | {m_2026_075['sharpe']:<8.2f} | {m_2026_075['max_dd']:<7.2f}% | {m_2026_075['pf']:<6.2f}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_2026_risk_comparison()
