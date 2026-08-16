"""
Reconciliation Fact-Check: Exact Reproduction of +927.25% / Sharpe 6.67 / MDD 14.54% / 4,020 trades.
Audits:
1. Daily vs Hourly Sharpe Ratio calculation
2. Equity Drawdown calculation (Daily peak-to-trough vs Trade-by-trade vs Portfolio Peak)
3. Lot Sizing rounding / fixed risk calculation ($75 risk per trade on $10k initial capital vs compounding)
4. Friction model: Full exit spread deduction vs SL-only vs universal friction
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
    return df_te.index, p_stack_l, p_stack_s, hmm_te

def run_targeted_sim(df_eval, p_l, p_s, hmm_arr, friction_mode="full_exit_only", compounding=True, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    risk_pct = 0.0075

    trades = []
    in_trade = False
    direction = None
    entry_price = 0.0
    entry_time = None
    sl_price = 0.0
    tp_price = 0.0
    initial_sl_dist = 0.0
    current_equity = initial_cap
    pending_order = None
    daily_equity = {}

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        if in_trade:
            t_log = trades[-1]; stop_out = False; exit_price = 0.0; exit_reason = None
            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not t_log['partial_taken'] and r_floating >= 1.5:
                partial_lots = t_log['initial_lots'] * 0.5; t_log['active_lots'] -= partial_lots; t_log['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5
                if friction_mode == "universal":
                    partial_pips -= 0.3
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
                if friction_mode in ("full_exit_only", "universal"):
                    rem_pips -= 0.3

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

                    risk_amt = (current_equity if compounding else initial_cap) * risk_pct
                    lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                    trades.append({'trade_id': len(trades) + 1, 'symbol': 'EURUSD', 'direction': direction, 'entry_time': entry_time, 'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'})

        if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]; retrace_pips = (atr / pip_size) * 0.25; limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

        daily_equity[str(timestamp.date())] = current_equity

    closed = [t for t in trades if t['status'] == 'closed']
    pnls = [t['pnl_usd'] for t in closed]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0
    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0; pf = gross_win / gross_loss

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()
    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0

    eq_curve = [initial_cap]
    for p in pnls: eq_curve.append(eq_curve[-1] + p)
    eq_arr = np.array(eq_curve); peaks = np.maximum.accumulate(eq_arr); dds = (eq_arr - peaks) / peaks * 100.0; max_dd_trade = abs(np.min(dds))

    # Daily Peak-to-Trough MDD
    daily_peaks = eq_series.cummax()
    daily_dds = (eq_series - daily_peaks) / daily_peaks * 100.0
    max_dd_daily = abs(daily_dds.min())

    return {
        "trades": len(closed),
        "ret_pct": ret_pct,
        "end_eq": current_equity,
        "sharpe_daily": sharpe_daily,
        "max_dd_daily": max_dd_daily,
        "max_dd_trade": max_dd_trade,
        "pf": pf
    }

def main():
    print("=================================================================================")
    print("  🔬 FINAL ADVOCATE FACT-CHECK: REPRODUCING +927.25% / SHARPE 6.67 / MDD 14.54%")
    print("=================================================================================\n")

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
    years_oos = list(range(2018, 2026))

    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l = np.zeros(len(df_eval))
    p_stack_s = np.zeros(len(df_eval))
    hmm_oos = np.zeros(len(df_eval))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in te_indices if idx in df_eval.index]
        p_stack_l[fold_eval_indices] = pl_fold
        p_stack_s[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    res_full_exit = run_targeted_sim(df_eval, p_stack_l, p_stack_s, hmm_oos, friction_mode="full_exit_only")
    res_universal = run_targeted_sim(df_eval, p_stack_l, p_stack_s, hmm_oos, friction_mode="universal")

    print("=================================================================================")
    print("  🏆 TARGETED RECONCILIATION SCORECARD FOR +927.25% / 6.67 / 14.54%")
    print("=================================================================================")
    print(f"{'Friction Accounting Mode':<30} | {'Trades':<7} | {'Net Return (%)':<15} | {'Daily Sharpe':<13} | {'Daily MDD (%)':<13} | {'PF':<6}")
    print("-" * 92)
    print(f"{'Full-Exit Friction Only':<30} | {res_full_exit['trades']:<7} | +{res_full_exit['ret_pct']:<14.2f}% | {res_full_exit['sharpe_daily']:<13.2f} | -{res_full_exit['max_dd_daily']:<12.2f}% | {res_full_exit['pf']:<6.2f}")
    print(f"{'Universal Production Friction':<30} | {res_universal['trades']:<7} | +{res_universal['ret_pct']:<14.2f}% | {res_universal['sharpe_daily']:<13.2f} | -{res_universal['max_dd_daily']:<12.2f}% | {res_universal['pf']:<6.2f}")
    print(f"{'Historical Headline Baseline':<30} | 4020    | +927.25       % | 6.67          | -14.54     % | 1.15  ")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
