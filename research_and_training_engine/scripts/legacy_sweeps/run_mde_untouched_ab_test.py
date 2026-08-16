"""
Master MDE Untouched Data A/B Test & Equity Curve Mechanics Audit.
Compares:
Variant A: Master Production Control (PAE + HMM + Static 0.75% Risk)
Variant B: Contextual MDE System (PAE + HMM + MDE Dynamic Risk & Cell Filtering)
on 100% Untouched Live Holdout Data & 8-Year OOS Walk-Forward Gauntlet.

Calculates:
- Cumulative Return & CAGR (%)
- Sharpe & Sortino Ratios
- Max Drawdown (MDD %) & Calmar Ratio
- Profit Factor & Average R
- Worst Month & Worst Year
- % Time Spent in Drawdown
- 95th & 99th Percentile Drawdown boundaries
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
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_state=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
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

def run_simulation_institutional(df_eval, p_l, p_s, state_arr, friction_pips=0.3, risk_pct=0.0075, mde_func=None, initial_cap=10000.0, years_count=8.0):
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

    trades = []; in_trade = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; current_equity = initial_cap; pending_order = None
    daily_equity = {}

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        if in_trade:
            t_log = trades[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
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

                    # MDE Evaluation
                    risk_mult = mde_func(p_prob, p_state) if mde_func is not None else 1.0

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
                            'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'
                        })
                    else:
                        pending_order = None

        if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            prob_val = p_l[i] if sig == 'BUY' else p_s[i]
            pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr, "prob": prob_val, "state": state_arr[i]}

        daily_equity[str(timestamp.date())] = current_equity

    closed = [t for t in trades if t['status'] == 'closed']
    if not closed: return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "cagr": 0.0, "sharpe": 0.0, "sortino": 0.0, "max_dd": 0.0, "calmar": 0.0, "pf": 0.0, "avg_r": 0.0, "worst_month": 0.0, "worst_year": 0.0, "pct_in_dd": 0.0, "dd_95": 0.0, "dd_99": 0.0, "end_eq": initial_cap}

    pnls = [t['pnl_usd'] for t in closed]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0
    cagr = (((current_equity / initial_cap) ** (1.0 / max(0.1, years_count))) - 1.0) * 100.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0; pf = gross_win / gross_loss
    avg_r = np.mean([t['r_multiple'] for t in closed])

    # Detailed Daily Equity Curve & Drawdown Analysis
    df_daily = pd.DataFrame(list(daily_equity.items()), columns=['date', 'equity'])
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    df_daily = df_daily.set_index('date')

    daily_returns = df_daily['equity'].pct_change().dropna().values
    ann_std = np.std(daily_returns) * np.sqrt(252)
    sharpe = (np.mean(daily_returns) * 252 / ann_std) if ann_std > 0 else 0.0

    neg_rets = daily_returns[daily_returns < 0]
    downside_std = np.std(neg_rets) * np.sqrt(252) if len(neg_rets) > 0 else 1e-6
    sortino = (np.mean(daily_returns) * 252 / downside_std) if downside_std > 0 else 0.0

    eq_arr = df_daily['equity'].values
    peaks = np.maximum.accumulate(eq_arr)
    dds = (eq_arr - peaks) / peaks * 100.0
    max_dd = abs(np.min(dds))
    calmar = cagr / max_dd if max_dd > 0 else 0.0

    pct_in_dd = (np.sum(dds < 0.0) / len(dds)) * 100.0
    dd_95 = abs(np.percentile(dds, 5)) # 95th percentile worst drawdown
    dd_99 = abs(np.percentile(dds, 1)) # 99th percentile worst drawdown

    # Monthly & Yearly Breakdown
    monthly_ret = df_daily['equity'].resample('M').last().pct_change().dropna() * 100.0
    worst_month = monthly_ret.min() if len(monthly_ret) > 0 else 0.0

    yearly_ret = df_daily['equity'].resample('A').last().pct_change().dropna() * 100.0
    worst_year = yearly_ret.min() if len(yearly_ret) > 0 else 0.0

    return {
        "trades": len(closed), "net_pnl": net_pnl, "ret_pct": ret_pct, "cagr": cagr,
        "sharpe": sharpe, "sortino": sortino, "max_dd": max_dd, "calmar": calmar,
        "pf": pf, "avg_r": avg_r, "worst_month": worst_month, "worst_year": worst_year,
        "pct_in_dd": pct_in_dd, "dd_95": dd_95, "dd_99": dd_99, "end_eq": current_equity
    }

def run_mde_untouched_ab_test():
    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("=================================================================================", flush=True)
    print("  🚀 INSTITUTIONAL MDE A/B TEST ON TRULY UNTOUCHED HOLDOUT & OOS GAUNTLET", flush=True)
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

    # 1. 8-Year OOS Walk-Forward Gauntlet (2018-2025)
    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    total_bars_oos = len(df_eval_oos)
    years_oos = list(range(2018, 2026))

    print("▶ Step 1: Generating 8-Year OOS Walk-Forward Predictions (2018-2025 EURUSD)...", flush=True)
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

    # 2. 100% Untouched 2026 Live Holdout (Jan 1 - Aug 11, 2026)
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

    # Contextual MDE Dynamic Policy Function
    def contextual_mde_policy(prob, state):
        if state == 6 and prob < 0.42: return 0.0 # Filter Bull + Low Vol cell with negative EV
        if prob >= 0.55: return 1.00 # Max Risk
        elif prob >= 0.45: return 0.75 # Medium Risk
        else: return 0.50 # Conservative Risk

    print("▶ Step 2: Running Variant A (Current Production Control: Static 0.75% Risk)...", flush=True)
    res_a_oos = run_simulation_institutional(df_eval_oos, p_stack_l_oos, p_stack_s_oos, state_oos, mde_func=None, years_count=8.0)
    res_a_26 = run_simulation_institutional(df_eval_26, p_stack_l_26, p_stack_s_26, state_te_26, mde_func=None, years_count=0.62)

    print("▶ Step 3: Running Variant B (Contextual MDE System: Dynamic Risk & Cell Filtering)...", flush=True)
    res_b_oos = run_simulation_institutional(df_eval_oos, p_stack_l_oos, p_stack_s_oos, state_oos, mde_func=contextual_mde_policy, years_count=8.0)
    res_b_26 = run_simulation_institutional(df_eval_26, p_stack_l_26, p_stack_s_26, state_te_26, mde_func=contextual_mde_policy, years_count=0.62)

    total_elapsed = time.time() - t0

    # Institutional Scorecard Reporting
    print("\n=========================================================================================================================================")
    print("  🏆 INSTITUTIONAL MDE A/B RECONCILIATION SCORECARD: CONTROL VS MDE DYNAMIC SYSTEM")
    print("=========================================================================================================================================")
    print(f"\n📊 1. 8-YEAR OUT-OF-SAMPLE GAUNTLET (2018-2025 H1 EURUSD):")
    print("-" * 115)
    print(f"{'Performance Metric':<35} | {'Variant A (Production Control)':<32} | {'Variant B (Contextual MDE System)':<32}")
    print("-" * 115)
    print(f"{'Cumulative Net Return (%)':<35} | +{res_a_oos['ret_pct']:<31.2f}% | +{res_b_oos['ret_pct']:<31.2f}%")
    print(f"{'CAGR (%)':<35} | +{res_a_oos['cagr']:<31.2f}% | +{res_b_oos['cagr']:<31.2f}%")
    print(f"{'Annualized Sharpe Ratio':<35} | {res_a_oos['sharpe']:<32.2f} | {res_b_oos['sharpe']:<32.2f}")
    print(f"{'Annualized Sortino Ratio':<35} | {res_a_oos['sortino']:<32.2f} | {res_b_oos['sortino']:<32.2f}")
    print(f"{'Max Drawdown (MDD %)':<35} | {res_a_oos['max_dd']:<31.2f}% | {res_b_oos['max_dd']:<31.2f}%")
    print(f"{'Calmar Ratio (CAGR / MDD)':<35} | {res_a_oos['calmar']:<32.2f} | {res_b_oos['calmar']:<32.2f}")
    print(f"{'Profit Factor (PF)':<35} | {res_a_oos['pf']:<32.2f} | {res_b_oos['pf']:<32.2f}")
    print(f"{'Trade Count':<35} | {res_a_oos['trades']:<32} | {res_b_oos['trades']:<32}")
    print(f"{'Average R-Multiple':<35} | {res_a_oos['avg_r']:<+32.2f} | {res_b_oos['avg_r']:<+32.2f}")
    print(f"{'Worst Month Return (%)':<35} | {res_a_oos['worst_month']:<+31.2f}% | {res_b_oos['worst_month']:<+31.2f}%")
    print(f"{'Worst Year Return (%)':<35} | {res_a_oos['worst_year']:<+31.2f}% | {res_b_oos['worst_year']:<+31.2f}%")
    print(f"{'Time Spent in Drawdown (%)':<35} | {res_a_oos['pct_in_dd']:<31.2f}% | {res_b_oos['pct_in_dd']:<31.2f}%")
    print(f"{'95th Percentile Drawdown (%)':<35} | {res_a_oos['dd_95']:<31.2f}% | {res_b_oos['dd_95']:<31.2f}%")
    print(f"{'99th Percentile Drawdown (%)':<35} | {res_a_oos['dd_99']:<31.2f}% | {res_b_oos['dd_99']:<31.2f}%")
    print("-" * 115)

    print(f"\n📊 2. 100% UNTOUCHED 2026 LIVE HOLDOUT DATA (JAN 1 - AUG 11, 2026):")
    print("-" * 115)
    print(f"{'Performance Metric':<35} | {'Variant A (Production Control)':<32} | {'Variant B (Contextual MDE System)':<32}")
    print("-" * 115)
    print(f"{'Cumulative Net Return (%)':<35} | +{res_a_26['ret_pct']:<31.2f}% | +{res_b_26['ret_pct']:<31.2f}%")
    print(f"{'Annualized Sharpe Ratio':<35} | {res_a_26['sharpe']:<32.2f} | {res_b_26['sharpe']:<32.2f}")
    print(f"{'Annualized Sortino Ratio':<35} | {res_a_26['sortino']:<32.2f} | {res_b_26['sortino']:<32.2f}")
    print(f"{'Max Drawdown (MDD %)':<35} | {res_a_26['max_dd']:<31.2f}% | {res_b_26['max_dd']:<31.2f}%")
    print(f"{'Calmar Ratio':<35} | {res_a_26['calmar']:<32.2f} | {res_b_26['calmar']:<32.2f}")
    print(f"{'Profit Factor (PF)':<35} | {res_a_26['pf']:<32.2f} | {res_b_26['pf']:<32.2f}")
    print(f"{'Trade Count':<35} | {res_a_26['trades']:<32} | {res_b_26['trades']:<32}")
    print(f"{'95th Percentile Drawdown (%)':<35} | {res_a_26['dd_95']:<31.2f}% | {res_b_26['dd_95']:<31.2f}%")
    print("-" * 115)

    print(f"\n🎉 MASTER MDE A/B RECONCILIATION COMPLETE IN {total_elapsed:.1f}s!", flush=True)

if __name__ == "__main__":
    run_mde_untouched_ab_test()
