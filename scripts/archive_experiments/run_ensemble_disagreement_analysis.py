"""
Empirical Ensemble Disagreement & Statistical Noise Reduction Analysis.
Calculates probability correlations, directional disagreement %, prediction error correlations,
false-positive rejection frequency, and performance of disagreement trades across all OOS bars (2018-2025 EURUSD H1).
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

def run_disagreement_analysis():
    print("=================================================================================", flush=True)
    print("  🔬 EMPIRICAL ENSEMBLE DISAGREEMENT & NOISE REDUCTION ANALYSIS")
    print("=================================================================================", flush=True)
    print("  • Period: 2018-2025 EURUSD H1 (8-Fold Expanding Walk-Forward OOS Gauntlet)")
    print("  • Evaluating: LightGBM vs CatBoost vs XGBoost vs Triple Stacking Consensus\n", flush=True)

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

    # Containers for out-of-sample probability arrays
    p_lgb_long = np.zeros(total_h1_bars)
    p_cat_long = np.zeros(total_h1_bars)
    p_xgb_long = np.zeros(total_h1_bars)

    p_lgb_short = np.zeros(total_h1_bars)
    p_cat_short = np.zeros(total_h1_bars)
    p_xgb_short = np.zeros(total_h1_bars)

    y_actual_long = np.zeros(total_h1_bars)
    y_actual_short = np.zeros(total_h1_bars)
    hmm_oos = np.zeros(total_h1_bars)
    s_test_arr = np.zeros(total_h1_bars, dtype=int)

    for yr in years_oos:
        train_end_year = yr - 1
        train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
        test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

        df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
        df_te = df_lbl[test_m].copy()

        # Step 1: HMM State (H_i in {0,1,2})
        hmm_detector = HMMRegimeDetector()
        hmm_detector.fit(df_tr)
        hmm_tr = hmm_detector.predict(df_tr)
        hmm_te = hmm_detector.predict(df_te)

        # Step 2: Volatility State (V_i in {0,1,2})
        tr_v = df_tr['feat_vol_atr_pct'].values
        te_v = df_te['feat_vol_atr_pct'].values

        v_tr = np.zeros(len(tr_v), dtype=int)
        v_tr[tr_v >= 33.33] = 1
        v_tr[tr_v >= 66.67] = 2

        v_te = np.zeros(len(te_v), dtype=int)
        v_te[te_v >= 33.33] = 1
        v_te[te_v >= 66.67] = 2

        # Step 3: Combined S_test = (H_i * 3) + V_i
        state_tr = (hmm_tr * 3) + v_tr
        state_te = (hmm_te * 3) + v_te

        X_tr_mat = df_tr[all_feat_cols].values
        y_l_tr = df_tr['label_dir_long'].values
        y_s_tr = df_tr['label_dir_short'].values
        X_te_mat = df_te[all_feat_cols].values

        pl_lgb = np.zeros(len(df_te))
        pl_cat = np.zeros(len(df_te))
        pl_xgb = np.zeros(len(df_te))

        ps_lgb = np.zeros(len(df_te))
        ps_cat = np.zeros(len(df_te))
        ps_xgb = np.zeros(len(df_te))

        for s in range(9):
            mask_tr = (state_tr == s)
            mask_te = (state_te == s)
            if not np.any(mask_te):
                continue
            if np.sum(mask_tr) >= 30:
                # Fit 3 individual models per state
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
        p_lgb_long[fold_eval_indices] = pl_lgb
        p_cat_long[fold_eval_indices] = pl_cat
        p_xgb_long[fold_eval_indices] = pl_xgb

        p_lgb_short[fold_eval_indices] = ps_lgb
        p_cat_short[fold_eval_indices] = ps_cat
        p_xgb_short[fold_eval_indices] = ps_xgb

        y_actual_long[fold_eval_indices] = df_te['label_dir_long'].values
        y_actual_short[fold_eval_indices] = df_te['label_dir_short'].values
        hmm_oos[fold_eval_indices] = hmm_te
        s_test_arr[fold_eval_indices] = state_te

    # Compute Stacking Consensus Probabilities
    p_stack_long = (p_lgb_long + p_cat_long + p_xgb_long) / 3.0
    p_stack_short = (p_lgb_short + p_cat_short + p_xgb_short) / 3.0

    # Metric 1: Probability Correlations
    corr_lgb_cat = np.corrcoef(p_lgb_long, p_cat_long)[0, 1]
    corr_lgb_xgb = np.corrcoef(p_lgb_long, p_xgb_long)[0, 1]
    corr_cat_xgb = np.corrcoef(p_cat_long, p_xgb_long)[0, 1]

    # Metric 2: Prediction Error Correlations
    err_lgb = p_lgb_long - y_actual_long
    err_cat = p_cat_long - y_actual_long
    err_xgb = p_xgb_long - y_actual_long

    err_corr_lgb_cat = np.corrcoef(err_lgb, err_cat)[0, 1]
    err_corr_lgb_xgb = np.corrcoef(err_lgb, err_xgb)[0, 1]
    err_corr_cat_xgb = np.corrcoef(err_cat, err_xgb)[0, 1]

    # Metric 3: Directional Signal Disagreement Analysis
    # Determine signal decisions for individual models and ensemble
    sig_lgb = np.zeros(total_h1_bars, dtype=bool)
    sig_cat = np.zeros(total_h1_bars, dtype=bool)
    sig_xgb = np.zeros(total_h1_bars, dtype=bool)
    sig_stack = np.zeros(total_h1_bars, dtype=bool)

    timestamps = df_eval.index
    for i in range(total_h1_bars):
        hour = timestamps[i].hour if isinstance(timestamps, pd.DatetimeIndex) else 0
        if 13 <= hour <= 16:
            continue
        st = hmm_oos[i]
        vol_pct = float(df_eval['feat_vol_atr_pct'].iloc[i])
        req_p = 0.42 if st == 1.0 else 0.36

        if vol_pct >= 40.0:
            if p_lgb_long[i] >= req_p or p_lgb_short[i] >= req_p:
                sig_lgb[i] = True
            if p_cat_long[i] >= req_p or p_cat_short[i] >= req_p:
                sig_cat[i] = True
            if p_xgb_long[i] >= req_p or p_xgb_short[i] >= req_p:
                sig_xgb[i] = True
            if p_stack_long[i] >= req_p or p_stack_short[i] >= req_p:
                sig_stack[i] = True

    # Disagreement Frequencies
    model_counts = sig_lgb.astype(int) + sig_cat.astype(int) + sig_xgb.astype(int)

    unanimous_agree = (model_counts == 3) | (model_counts == 0)
    any_disagree = ~unanimous_agree

    # Trades Accepted by 1 or 2 Models but REJECTED by Stack Ensemble
    trades_any_single = sig_lgb | sig_cat | sig_xgb
    rejected_by_ensemble = trades_any_single & (~sig_stack)
    accepted_by_ensemble_not_all = sig_stack & (model_counts < 3)
    unanimous_ensemble_trades = sig_stack & (model_counts == 3)

    disagree_pct = (np.sum(any_disagree) / total_h1_bars) * 100.0

    print("=========================================================================================================================================")
    print("  📊 EMPIRICAL STATISTICAL METRICS: ENSEMBLE NOISE REDUCTION PROOF")
    print("=========================================================================================================================================")
    print(f"1. PROBABILITY PREDICTION CORRELATIONS:")
    print(f"   • LightGBM vs CatBoost Probability Correlation: {corr_lgb_cat:.4f}")
    print(f"   • LightGBM vs XGBoost Probability Correlation:  {corr_lgb_xgb:.4f}")
    print(f"   • CatBoost vs XGBoost Probability Correlation:  {corr_cat_xgb:.4f}")
    print(f"   • Average Inter-Model Correlation:               {np.mean([corr_lgb_cat, corr_lgb_xgb, corr_cat_xgb]):.4f}\n")

    print(f"2. PREDICTION ERROR CORRELATIONS:")
    print(f"   • LightGBM vs CatBoost Residual Error Correlation: {err_corr_lgb_cat:.4f}")
    print(f"   • LightGBM vs XGBoost Residual Error Correlation:  {err_corr_lgb_xgb:.4f}")
    print(f"   • CatBoost vs XGBoost Residual Error Correlation:  {err_corr_cat_xgb:.4f}\n")

    print(f"3. DIRECTIONAL TRADE DISAGREEMENT & REJECTION FREQUENCY:")
    print(f"   • Total Hourly Bars Analyzed:                      {total_h1_bars:,}")
    print(f"   • Overall Directional Disagreement Rate:            {disagree_pct:.2f}% of all bars")
    print(f"   • Bars Triggered by ANY Single Model:              {np.sum(trades_any_single):,}")
    print(f"   • Trades REJECTED by Ensemble (Single-Model Noise): {np.sum(rejected_by_ensemble):,} ({np.sum(rejected_by_ensemble)/np.sum(trades_any_single)*100:.2f}% Noise Filtered)")
    print(f"   • Trades ACCEPTED by Ensemble (Consensus Signals): {np.sum(sig_stack):,}")
    print(f"   • Unanimous Consensus Trades (3/3 Models Agree):   {np.sum(unanimous_ensemble_trades):,}\n")

    # Re-run simulation to isolate PnL of Disagreement Trades vs Unanimous Trades
    def run_sim_custom_mask(prob_l, prob_s, hmm_arr, allow_mask=None):
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
            if allow_mask is not None and not allow_mask[i]:
                continue
            hour = timestamps[i].hour if isinstance(timestamps, pd.DatetimeIndex) else 0
            if 13 <= hour <= 16:
                continue
            p_l, p_s = prob_l[i], prob_s[i]
            st = hmm_arr[i]
            vol_pct = float(df_eval['feat_vol_atr_pct'].iloc[i])
            req_p = 0.42 if st == 1.0 else 0.36

            if p_l >= req_p and vol_pct >= 40.0:
                signals_arr[i] = "BUY"
            elif p_s >= req_p:
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

    # Evaluate Rejected Single-Model Trades PnL (Counterfactual)
    m_rejected = calc_metrics(*run_sim_custom_mask(p_lgb_long, p_lgb_short, hmm_oos, allow_mask=rejected_by_ensemble))
    m_unanimous = calc_metrics(*run_sim_custom_mask(p_stack_long, p_stack_short, hmm_oos, allow_mask=unanimous_ensemble_trades))
    m_partial_disagree = calc_metrics(*run_sim_custom_mask(p_stack_long, p_stack_short, hmm_oos, allow_mask=accepted_by_ensemble_not_all))

    print(f"4. PERFORMANCE OF DISAGREEMENT TRADES:")
    print(f"   • Counterfactual PnL of Trades REJECTED by Ensemble: Net Return = {m_rejected['ret_pct']:+.2f}%, PF = {m_rejected['pf']:.2f}, Sharpe = {m_rejected['sharpe']:.2f}")
    print(f"   • Performance of UNANIMOUS Consensus Trades (3/3):   Net Return = {m_unanimous['ret_pct']:+.2f}%, PF = {m_unanimous['pf']:.2f}, Sharpe = {m_unanimous['sharpe']:.2f}")
    print(f"   • Performance of Ensemble Partial-Agreement Trades: Net Return = {m_partial_disagree['ret_pct']:+.2f}%, PF = {m_partial_disagree['pf']:.2f}, Sharpe = {m_partial_disagree['sharpe']:.2f}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_disagreement_analysis()
