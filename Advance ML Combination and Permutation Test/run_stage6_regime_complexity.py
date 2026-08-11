"""
Stage 6: Regime Discretization & State-Space Complexity Laboratory.
Benchmarks 1-State vs 3-State vs 6-State vs 9-State (Control Champion) vs 12-State Regimes
across the 8-Fold Walk-Forward OOS Gauntlet (2018-2025 EURUSD H1) using the Champion Triple Stacking Ensemble.
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

def run_stage6_regime_complexity():
    print("=================================================================================", flush=True)
    print("  🔬 STAGE 6: REGIME DISCRETIZATION & STATE-SPACE COMPLEXITY LABORATORY", flush=True)
    print("=================================================================================", flush=True)
    print("  • Period: 2018-2025 EURUSD H1 (8-Fold Expanding Walk-Forward OOS Gauntlet)", flush=True)
    print("  • Comparing Architectures: 1-State (Global) vs 3-State vs 6-State vs 9-State (Control) vs 12-State\n", flush=True)

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

    regime_configs = {
        "1-State: Global Single Ensemble (No Regimes)": {"n_hmm": 1, "n_vol": 1},
        "3-State: Directional HMM Regimes Only (3x1)": {"n_hmm": 3, "n_vol": 1},
        "6-State: HMM x 2 Volatility Quantiles (3x2)": {"n_hmm": 3, "n_vol": 2},
        "9-State: Champion Control HMM x 3 Volatility (3x3)": {"n_hmm": 3, "n_vol": 3},
        "12-State: 4 HMM States x 3 Volatility Quantiles (4x3)": {"n_hmm": 4, "n_vol": 3},
    }

    def run_regime_experiment(n_hmm, n_vol):
        p_stack_l = np.zeros(total_h1_bars)
        p_stack_s = np.zeros(total_h1_bars)
        hmm_oos = np.zeros(total_h1_bars)

        for yr in years_oos:
            train_end_year = yr - 1
            train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
            test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

            df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
            df_te = df_lbl[test_m].copy()

            if n_hmm == 1:
                hmm_tr = np.zeros(len(df_tr), dtype=int)
                hmm_te = np.zeros(len(df_te), dtype=int)
            else:
                hmm_detector = HMMRegimeDetector(n_components=n_hmm)
                hmm_detector.fit(df_tr)
                hmm_tr = hmm_detector.predict(df_tr)
                hmm_te = hmm_detector.predict(df_te)

            tr_v = df_tr['feat_vol_atr_pct'].values
            te_v = df_te['feat_vol_atr_pct'].values

            if n_vol == 1:
                v_tr = np.zeros(len(tr_v), dtype=int)
                v_te = np.zeros(len(te_v), dtype=int)
            elif n_vol == 2:
                v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 50.0] = 1
                v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 50.0] = 1
            elif n_vol == 3:
                v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 33.33] = 1; v_tr[tr_v >= 66.67] = 2
                v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 33.33] = 1; v_te[te_v >= 66.67] = 2

            state_tr = (hmm_tr * n_vol) + v_tr
            state_te = (hmm_te * n_vol) + v_te
            total_states = n_hmm * n_vol

            X_tr_mat = df_tr[all_feat_cols].values
            y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values
            X_te_mat = df_te[all_feat_cols].values

            pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
            ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

            for s in range(total_states):
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

            fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
            p_stack_l[fold_eval_indices] = (pl_lgb + pl_cat + pl_xgb) / 3.0
            p_stack_s[fold_eval_indices] = (ps_lgb + ps_cat + ps_xgb) / 3.0
            hmm_oos[fold_eval_indices] = hmm_te

        # Run Trade Simulator
        pip_size = 0.0001
        timestamps = df_eval.index
        closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
        hours = np.array([ts.hour for ts in timestamps])
        trading_window = ~((hours >= 13) & (hours <= 16))
        vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
        req_p_arr = np.where(hmm_oos == 1.0, 0.42, 0.36)

        signals_buy = (p_stack_l >= req_p_arr) & vol_pass & trading_window
        signals_sell = (p_stack_s >= req_p_arr) & trading_window

        trades = []; in_trade = False; direction = None; entry_price = 0.0; entry_time = None; sl_price = 0.0; tp_price = 0.0; initial_sl_dist = 0.0; current_equity = 10000.0; pending_order = None
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
        if not closed: return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0}
        pnls = [t['pnl_usd'] for t in closed]
        wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
        net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0
        gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0; pf = gross_win / gross_loss

        eq_curve = [10000.0]
        for p in pnls: eq_curve.append(eq_curve[-1] + p)
        eq_arr = np.array(eq_curve); peaks = np.maximum.accumulate(eq_arr); dds = (eq_arr - peaks) / peaks * 100.0; max_dd = abs(np.min(dds))
        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0
        return {"trades": len(closed), "net_pnl": net_pnl, "ret_pct": ret_pct, "pf": pf, "sharpe": sharpe, "max_dd": max_dd}

    regime_results = {}
    base_m = None

    for name, cfg in regime_configs.items():
        print(f"▶ Evaluating Regime State-Space Config: {name}...", flush=True)
        m = run_regime_experiment(cfg["n_hmm"], cfg["n_vol"])
        regime_results[name] = m
        if "Champion Control" in name:
            base_m = m
        print(f"  ✓ {name} Complete: Net Return = {m['ret_pct']:+.2f}%, Sharpe = {m['sharpe']:.2f}, MDD = {m['max_dd']:.2f}%\n", flush=True)

    total_elapsed = time.time() - t0

    print("=========================================================================================================================================", flush=True)
    print(f"  🏆 STAGE 6 REGIME COMPLEXITY SCORECARD (TOTAL TIME: {total_elapsed:.1f}s)", flush=True)
    print("=========================================================================================================================================", flush=True)
    print(f"{'Regime State-Space Architecture':<54} | {'Trades':<7} | {'Net Return (%)':<14} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6} | {'Delta vs 9-State Champion':<22}", flush=True)
    print("-" * 125, flush=True)

    base_r = base_m['ret_pct']
    base_s = base_m['sharpe']

    for name, m in regime_results.items():
        diff_r = m['ret_pct'] - base_r
        diff_s = m['sharpe'] - base_s
        diff_str = f"{diff_r:+.2f}% Return (Sharpe {diff_s:+.2f})" if "Champion Control" not in name else "CHAMPION BENCHMARK 🟢"
        print(f"{name:<54} | {m['trades']:<7} | +{m['ret_pct']:<13.2f}% | {m['sharpe']:<8.2f} | {m['max_dd']:<7.2f}% | {m['pf']:<6.2f} | {diff_str:<22}", flush=True)

    print("=========================================================================================================================================", flush=True)

if __name__ == "__main__":
    run_stage6_regime_complexity()
