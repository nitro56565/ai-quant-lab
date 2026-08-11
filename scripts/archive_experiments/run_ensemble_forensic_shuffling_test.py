"""
Ensemble Forensic Shuffling & Agreement Breakdown Protocol.
Evaluates:
1. Trade Breakdown by Agreement Level (Production Ensemble A, 3/3 Unanimous B, 2/3 Partial C, 1/3 Single Noise D).
2. Real vs Shuffled Model Predictions Permutation Gauntlet (Tests A, B, C, D, E).
Across the 8-Fold Walk-Forward OOS Gauntlet (2018-2025 EURUSD H1).
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

def run_ensemble_forensic_shuffling_test():
    print("=================================================================================", flush=True)
    print("  🔬 ENSEMBLE FORENSIC SHUFFLING & AGREEMENT BREAKDOWN LABORATORY")
    print("=================================================================================", flush=True)
    print("  • Period: 2018-2025 EURUSD H1 (8-Fold Expanding Walk-Forward OOS Gauntlet)")
    print("  • Objective: Evaluate Agreement Trade Breakdown & Shuffled Model Predictions (Tests A-E)\n", flush=True)

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
    df_lbl = tb_lab.label(df_feat)
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    eval_mask = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval = df_feat[eval_mask].copy()
    total_h1_bars = len(df_eval)
    years_oos = list(range(2018, 2026))

    # Raw prediction arrays
    p_lgb_l = np.zeros(total_h1_bars)
    p_cat_l = np.zeros(total_h1_bars)
    p_xgb_l = np.zeros(total_h1_bars)

    p_lgb_s = np.zeros(total_h1_bars)
    p_cat_s = np.zeros(total_h1_bars)
    p_xgb_s = np.zeros(total_h1_bars)

    hmm_oos = np.zeros(total_h1_bars)

    print("Generating OOS predictions for LightGBM, CatBoost, and XGBoost across 8 folds...", flush=True)

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

        v_tr = np.zeros(len(tr_v), dtype=int)
        v_tr[tr_v >= 33.33] = 1
        v_tr[tr_v >= 66.67] = 2

        v_te = np.zeros(len(te_v), dtype=int)
        v_te[te_v >= 33.33] = 1
        v_te[te_v >= 66.67] = 2

        state_tr = (hmm_tr * 3) + v_tr
        state_te = (hmm_te * 3) + v_te

        X_tr_mat = df_tr[all_feat_cols].values
        y_l_tr = df_tr['label_dir_long'].values
        y_s_tr = df_tr['label_dir_short'].values
        X_te_mat = df_te[all_feat_cols].values

        pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
        ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

        for s in range(9):
            mask_tr = (state_tr == s)
            mask_te = (state_te == s)
            if not np.any(mask_te):
                continue
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

        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
        p_lgb_l[fold_eval_indices] = pl_lgb
        p_cat_l[fold_eval_indices] = pl_cat
        p_xgb_l[fold_eval_indices] = pl_xgb

        p_lgb_s[fold_eval_indices] = ps_lgb
        p_cat_s[fold_eval_indices] = ps_cat
        p_xgb_s[fold_eval_indices] = ps_xgb

        hmm_oos[fold_eval_indices] = hmm_te

    # Simulator
    def run_sim_signals(signals_buy, signals_sell):
        pip_size = 0.0001
        trades = []
        in_trade = False
        direction = None
        entry_price = 0.0
        entry_time = None
        sl_price = 0.0
        tp_price = 0.0
        initial_sl_dist = 0.0
        current_equity = 10000.0
        pending_order = None

        timestamps = df_eval.index
        closes = df_eval['close'].values
        highs = df_eval['high'].values
        lows = df_eval['low'].values
        atrs = df_eval['feat_vol_atr'].values

        signals_arr = np.full(len(df_eval), "NONE", dtype=object)
        for i in range(len(df_eval)):
            if signals_buy[i]:
                signals_arr[i] = "BUY"
            elif signals_sell[i]:
                signals_arr[i] = "SELL"

        for i in range(len(df_eval)):
            timestamp = timestamps[i]
            close = closes[i]
            high = highs[i]
            low = lows[i]
            atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

            if in_trade:
                t_log = trades[-1]
                stop_out = False
                exit_price = 0.0
                exit_reason = None
                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'

                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                if not t_log['partial_taken'] and r_floating >= 1.5:
                    partial_lots = t_log['initial_lots'] * 0.5
                    t_log['active_lots'] -= partial_lots
                    t_log['partial_taken'] = True

                    partial_pips = (initial_sl_dist / pip_size) * 1.5
                    partial_gross = partial_pips * (partial_lots * 10.0)
                    partial_comm = 7.0 * partial_lots
                    partial_net = partial_gross - partial_comm

                    t_log['partial_pnl_usd'] = partial_net
                    current_equity += partial_net

                if signals_arr[i] == opposite_sig:
                    stop_out = True
                    exit_price = close
                    exit_reason = 'signal_reversal'
                elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0:
                    stop_out = True
                    exit_price = close
                    exit_reason = 'time_limit'
                elif direction == 'BUY' and low <= sl_price:
                    stop_out = True
                    exit_price = sl_price - (0.3 * pip_size)
                    exit_reason = 'stop_loss'
                elif direction == 'SELL' and high >= sl_price:
                    stop_out = True
                    exit_price = sl_price + (0.3 * pip_size)
                    exit_reason = 'stop_loss'
                elif direction == 'BUY' and high >= tp_price:
                    stop_out = True
                    exit_price = tp_price
                    exit_reason = 'take_profit'
                elif direction == 'SELL' and low <= tp_price:
                    stop_out = True
                    exit_price = tp_price
                    exit_reason = 'take_profit'

                if stop_out:
                    in_trade = False
                    rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    rem_lots = t_log['active_lots']
                    rem_gross = rem_pips * (rem_lots * 10.0)
                    rem_comm = 7.0 * rem_lots
                    rem_net = rem_gross - rem_comm

                    total_trade_net = rem_net + t_log.get('partial_pnl_usd', 0.0)

                    t_log['exit_time'] = timestamp
                    t_log['exit_price'] = exit_price
                    t_log['exit_reason'] = exit_reason
                    t_log['pnl_pips'] = rem_pips
                    t_log['pnl_usd'] = total_trade_net
                    t_log['status'] = 'closed'
                    current_equity += rem_net

                    if signals_arr[i] == opposite_sig:
                        pending_order = {
                            "direction": opposite_sig,
                            "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr),
                            "signal_idx": i,
                            "atr": atr
                        }

            if not in_trade and pending_order is not None:
                p_dir = pending_order["direction"]
                p_limit = pending_order["limit_price"]
                p_atr = pending_order["atr"]
                sig_idx = pending_order["signal_idx"]

                if (i - sig_idx) > 3:
                    pending_order = None
                else:
                    filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                    if filled:
                        in_trade = True
                        direction = p_dir
                        entry_time = timestamp
                        entry_price = p_limit
                        pending_order = None

                        sl_pips = (p_atr / pip_size) * 2.0
                        tp_pips = (p_atr / pip_size) * 2.5
                        initial_sl_dist = sl_pips * pip_size

                        if direction == 'BUY':
                            sl_price = entry_price - initial_sl_dist
                            tp_price = entry_price + (tp_pips * pip_size)
                        else:
                            sl_price = entry_price + initial_sl_dist
                            tp_price = entry_price - (tp_pips * pip_size)

                        risk_amt = current_equity * 0.005
                        lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                        trades.append({
                            'trade_id': len(trades) + 1,
                            'symbol': 'EURUSD',
                            'direction': direction,
                            'entry_time': entry_time,
                            'entry_price': entry_price,
                            'sl_price': sl_price,
                            'tp_price': tp_price,
                            'initial_lots': lots,
                            'active_lots': lots,
                            'partial_taken': False,
                            'partial_pnl_usd': 0.0,
                            'status': 'open'
                        })

            if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
                sig = signals_arr[i]
                retrace_pips = (atr / pip_size) * 0.25
                limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
                pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

        return trades, current_equity

    def calc_metrics(trades, final_eq):
        closed = [t for t in trades if t['status'] == 'closed']
        total_n = len(closed)
        if total_n == 0:
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0}

        pnls = [t['pnl_usd'] for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        net_pnl = sum(pnls)
        ret_pct = (net_pnl / 10000.0) * 100.0
        win_rate = (len(wins) / total_n) * 100.0
        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1.0
        pf = gross_win / gross_loss

        eq_curve = [10000.0]
        for p in pnls:
            eq_curve.append(eq_curve[-1] + p)
        eq_arr = np.array(eq_curve)
        peaks = np.maximum.accumulate(eq_arr)
        dds = (eq_arr - peaks) / peaks * 100.0
        max_dd = abs(np.min(dds))

        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0
        ev_usd = net_pnl / total_n

        return {"trades": total_n, "net_pnl": net_pnl, "ret_pct": ret_pct, "win_rate": win_rate, "pf": pf, "sharpe": sharpe, "max_dd": max_dd, "ev_usd": ev_usd}

    # ===================================================================================
    # PART 1: TEST 1 - TRADE BREAKDOWN BY AGREEMENT LEVEL (A, B, C, D)
    # ===================================================================================
    print("\n--- PART 1: TRADE BREAKDOWN BY AGREEMENT LEVEL ---", flush=True)

    # Calculate per-model signals
    timestamps = df_eval.index
    req_p_arr = np.where(hmm_oos == 1.0, 0.42, 0.36)
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)

    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))

    lgb_buy = (p_lgb_l >= req_p_arr) & vol_pass & trading_window
    lgb_sell = (p_lgb_s >= req_p_arr) & trading_window

    cat_buy = (p_cat_l >= req_p_arr) & vol_pass & trading_window
    cat_sell = (p_cat_s >= req_p_arr) & trading_window

    xgb_buy = (p_xgb_l >= req_p_arr) & vol_pass & trading_window
    xgb_sell = (p_xgb_s >= req_p_arr) & trading_window

    # Triple Stacking Signals
    p_stack_l = (p_lgb_l + p_cat_l + p_xgb_l) / 3.0
    p_stack_s = (p_lgb_s + p_cat_s + p_xgb_s) / 3.0

    stack_buy = (p_stack_l >= req_p_arr) & vol_pass & trading_window
    stack_sell = (p_stack_s >= req_p_arr) & trading_window

    # Agreement Counts
    agree_buy_count = lgb_buy.astype(int) + cat_buy.astype(int) + xgb_buy.astype(int)
    agree_sell_count = lgb_sell.astype(int) + cat_sell.astype(int) + xgb_sell.astype(int)

    # A. Ensemble Selected Trades (Actual Production Algorithm)
    mA = calc_metrics(*run_sim_signals(stack_buy, stack_sell))

    # B. 3/3 Agreement Trades (Unanimous Consensus)
    b_buy_3of3 = stack_buy & (agree_buy_count == 3)
    b_sell_3of3 = stack_sell & (agree_sell_count == 3)
    mB = calc_metrics(*run_sim_signals(b_buy_3of3, b_sell_3of3))

    # C. 2/3 Agreement Trades (Ensemble Accepts, but only 2 models agree)
    c_buy_2of3 = stack_buy & (agree_buy_count == 2)
    c_sell_2of3 = stack_sell & (agree_sell_count == 2)
    mC = calc_metrics(*run_sim_signals(c_buy_2of3, c_sell_2of3))

    # D. 1/3 Agreement Trades (Only 1 model satisfied criteria - Single-Model Noise Rejected by Ensemble)
    d_buy_1of3 = (~stack_buy) & (agree_buy_count == 1)
    d_sell_1of3 = (~stack_sell) & (agree_sell_count == 1)
    mD = calc_metrics(*run_sim_signals(d_buy_1of3, d_sell_1of3))

    print("=========================================================================================================================================", flush=True)
    print("  🏆 PART 1: TRADE BREAKDOWN BY AGREEMENT LEVEL SCORECARD")
    print("=========================================================================================================================================", flush=True)
    print(f"{'Agreement Category':<46} | {'Trades':<7} | {'Net Return (%)':<14} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6} | {'Expectancy ($/Tr)':<18}", flush=True)
    print("-" * 125, flush=True)
    print(f"{'A. Production Ensemble Selected Trades':<46} | {mA['trades']:<7} | +{mA['ret_pct']:<13.2f}% | {mA['sharpe']:<8.2f} | {mA['max_dd']:<7.2f}% | {mA['pf']:<6.2f} | ${mA['ev_usd']:<+17.2f}", flush=True)
    print(f"{'B. 3/3 Unanimous Agreement Trades':<46} | {mB['trades']:<7} | +{mB['ret_pct']:<13.2f}% | {mB['sharpe']:<8.2f} | {mB['max_dd']:<7.2f}% | {mB['pf']:<6.2f} | ${mB['ev_usd']:<+17.2f}", flush=True)
    print(f"{'C. 2/3 Partial Agreement Trades (Ensemble Accepted)':<46} | {mC['trades']:<7} | +{mC['ret_pct']:<13.2f}% | {mC['sharpe']:<8.2f} | {mC['max_dd']:<7.2f}% | {mC['pf']:<6.2f} | ${mC['ev_usd']:<+17.2f}", flush=True)
    print(f"{'D. 1/3 Single Model Trades (REJECTED by Ensemble)':<46} | {mD['trades']:<7} | {mD['ret_pct']:<+13.2f}% | {mD['sharpe']:<8.2f} | {mD['max_dd']:<7.2f}% | {mD['pf']:<6.2f} | ${mD['ev_usd']:<+17.2f}", flush=True)
    print("=========================================================================================================================================\n", flush=True)

    # ===================================================================================
    # PART 2: TEST 2 - REAL vs SHUFFLED MODEL PREDICTIONS (TESTS A, B, C, D, E)
    # ===================================================================================
    print("--- PART 2: REAL vs SHUFFLED MODEL PREDICTIONS PERMUTATION GAUNTLET ---", flush=True)

    def block_shuffle(arr, block_size=24, seed=42):
        np.random.seed(seed)
        n = len(arr)
        num_blocks = n // block_size
        blocks = [arr[i*block_size : (i+1)*block_size] for i in range(num_blocks)]
        if n % block_size != 0:
            blocks.append(arr[num_blocks*block_size:])
        indices = np.arange(len(blocks))
        np.random.shuffle(indices)
        shuffled_blocks = [blocks[i] for i in indices]
        return np.concatenate(shuffled_blocks)[:n]

    # Shuffled Model Probabilities (24-bar blocks to preserve local autocorrelation)
    p_lgb_l_shuf = block_shuffle(p_lgb_l, block_size=24, seed=101)
    p_lgb_s_shuf = block_shuffle(p_lgb_s, block_size=24, seed=101)

    p_cat_l_shuf = block_shuffle(p_cat_l, block_size=24, seed=202)
    p_cat_s_shuf = block_shuffle(p_cat_s, block_size=24, seed=202)

    p_xgb_l_shuf = block_shuffle(p_xgb_l, block_size=24, seed=303)
    p_xgb_s_shuf = block_shuffle(p_xgb_s, block_size=24, seed=303)

    def run_stack_perm(lgb_l, lgb_s, cat_l, cat_s, xgb_l, xgb_s):
        stack_l = (lgb_l + cat_l + xgb_l) / 3.0
        stack_s = (lgb_s + cat_s + xgb_s) / 3.0
        buy_sig = (stack_l >= req_p_arr) & vol_pass & trading_window
        sell_sig = (stack_s >= req_p_arr) & trading_window
        return calc_metrics(*run_sim_signals(buy_sig, sell_sig))

    # Test A: Real Triple Stack (LGBM Real + CatBoost Real + XGBoost Real)
    m_TestA = run_stack_perm(p_lgb_l, p_lgb_s, p_cat_l, p_cat_s, p_xgb_l, p_xgb_s)

    # Test B: LGBM Real + CatBoost Real + XGBoost SHUFFLED
    m_TestB = run_stack_perm(p_lgb_l, p_lgb_s, p_cat_l, p_cat_s, p_xgb_l_shuf, p_xgb_s_shuf)

    # Test C: LGBM Real + CatBoost SHUFFLED + XGBoost Real
    m_TestC = run_stack_perm(p_lgb_l, p_lgb_s, p_cat_l_shuf, p_cat_s_shuf, p_xgb_l, p_xgb_s)

    # Test D: LGBM SHUFFLED + CatBoost Real + XGBoost Real
    m_TestD = run_stack_perm(p_lgb_l_shuf, p_lgb_s_shuf, p_cat_l, p_cat_s, p_xgb_l, p_xgb_s)

    # Test E: All 3 Models SHUFFLED (Complete Null Control)
    m_TestE = run_stack_perm(p_lgb_l_shuf, p_lgb_s_shuf, p_cat_l_shuf, p_cat_s_shuf, p_xgb_l_shuf, p_xgb_s_shuf)

    print("=========================================================================================================================================", flush=True)
    print("  🏆 PART 2: REAL vs SHUFFLED MODEL PREDICTIONS PERMUTATION SCORECARD")
    print("=========================================================================================================================================", flush=True)
    print(f"{'Permutation Configuration':<46} | {'Trades':<7} | {'Net Return (%)':<14} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6} | {'Degradation vs Real Stack':<22}", flush=True)
    print("-" * 125, flush=True)

    base_r = m_TestA['ret_pct']
    base_s = m_TestA['sharpe']

    print(f"{'Test A: Real Triple Stack (LGBM + Cat + XGB)':<46} | {m_TestA['trades']:<7} | +{m_TestA['ret_pct']:<13.2f}% | {m_TestA['sharpe']:<8.2f} | {m_TestA['max_dd']:<7.2f}% | {m_TestA['pf']:<6.2f} | {'REAL CONTROL BENCHMARK 🟢':<22}", flush=True)
    print(f"{'Test B: LGBM Real + Cat Real + XGB SHUFFLED':<46} | {m_TestB['trades']:<7} | {m_TestB['ret_pct']:<+13.2f}% | {m_TestB['sharpe']:<8.2f} | {m_TestB['max_dd']:<7.2f}% | {m_TestB['pf']:<6.2f} | {m_TestB['ret_pct']-base_r:+.2f}% Return (Sharpe {m_TestB['sharpe']-base_s:+.2f})", flush=True)
    print(f"{'Test C: LGBM Real + Cat SHUFFLED + XGB Real':<46} | {m_TestC['trades']:<7} | {m_TestC['ret_pct']:<+13.2f}% | {m_TestC['sharpe']:<8.2f} | {m_TestC['max_dd']:<7.2f}% | {m_TestC['pf']:<6.2f} | {m_TestC['ret_pct']-base_r:+.2f}% Return (Sharpe {m_TestC['sharpe']-base_s:+.2f})", flush=True)
    print(f"{'Test D: LGBM SHUFFLED + Cat Real + XGB Real':<46} | {m_TestD['trades']:<7} | {m_TestD['ret_pct']:<+13.2f}% | {m_TestD['sharpe']:<8.2f} | {m_TestD['max_dd']:<7.2f}% | {m_TestD['pf']:<6.2f} | {m_TestD['ret_pct']-base_r:+.2f}% Return (Sharpe {m_TestD['sharpe']-base_s:+.2f})", flush=True)
    print(f"{'Test E: All 3 Models SHUFFLED (Complete Null)':<46} | {m_TestE['trades']:<7} | {m_TestE['ret_pct']:<+13.2f}% | {m_TestE['sharpe']:<8.2f} | {m_TestE['max_dd']:<7.2f}% | {m_TestE['pf']:<6.2f} | {m_TestE['ret_pct']-base_r:+.2f}% Return (Sharpe {m_TestE['sharpe']-base_s:+.2f})", flush=True)
    print("=========================================================================================================================================", flush=True)

if __name__ == "__main__":
    run_ensemble_forensic_shuffling_test()
