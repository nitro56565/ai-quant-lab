"""
Locked Track B vs Track C Comparison on 100% Untouched 2026 Dataset (2026-01-01 to 2026-08-11).
Locks both pipelines completely with zero retraining or parameter modifications.
Evaluates both pipelines head-to-head on 2026 data and outputs comparative metrics,
monthly consistency breakdown, and regime performance analysis.
"""

import os, sys, time, joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder

def run_locked_b_vs_c():
    print("=================================================================================")
    print("  🔒 LOCKED HEAD-TO-HEAD AUDIT: TRACK B vs TRACK C ON UNTOUCHED 2026 DATA")
    print("=================================================================================")
    print("  • Period: 2026-01-01 to 2026-08-11 (100% Untouched 2026 Dataset)")
    print("  • Track B: Standard 33.33% / 66.67% Volatility Terziles")
    print("  • Track C: Shifted 25.0% / 75.0% Volatility Quantiles\n")

    loader = DataLoader()
    symbol = "EURUSD"
    req_2026 = DataRequest(symbol=symbol, timeframe="1h", start="2026-01-01", end="2026-08-11")
    df_2026 = loader.load(req_2026)

    # Load Base Model Suite
    bundle_path = "models/production/model_suite.joblib"
    bundle = joblib.load(bundle_path)
    hmm_detector = bundle["hmm_detector"]
    feat_cols = bundle["feature_cols"]
    models_long = bundle["models_long"]
    models_short = bundle["models_short"]

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_2026.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)
    df_feat[feat_cols] = df_feat[feat_cols].bfill().ffill().fillna(0.0)

    hmm_states = hmm_detector.predict(df_feat)
    tr_vol_pct = df_feat['feat_vol_atr_pct'].values

    # Predict function for given volatility thresholds
    def get_track_predictions(low_th, high_th):
        v_state = np.zeros(len(tr_vol_pct), dtype=int)
        v_state[tr_vol_pct >= low_th] = 1
        v_state[tr_vol_pct >= high_th] = 2

        state_9 = (hmm_states * 3) + v_state
        prob_l = np.zeros(len(df_feat))
        prob_s = np.zeros(len(df_feat))

        for s in range(9):
            mask = (state_9 == s)
            if not np.any(mask):
                continue
            m_l = models_long.get(s)
            m_s = models_short.get(s)
            if m_l and m_s:
                X_sub = df_feat.loc[mask, feat_cols].values
                prob_l[mask] = m_l.predict_proba(X_sub)[:, 1]
                prob_s[mask] = m_s.predict_proba(X_sub)[:, 1]
            else:
                prob_l[mask] = 0.30
                prob_s[mask] = 0.30

        return prob_l, prob_s, state_9

    # Simulator
    def run_sim(prob_l, prob_s):
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

        timestamps = df_feat.index
        closes = df_feat['close'].values
        highs = df_feat['high'].values
        lows = df_feat['low'].values
        atrs = df_feat['feat_vol_atr'].values

        signals_arr = np.full(len(df_feat), "NONE", dtype=object)
        for i in range(len(df_feat)):
            hour = timestamps[i].hour if isinstance(timestamps, pd.DatetimeIndex) else 0
            if 13 <= hour <= 16:
                continue
            p_l, p_s = prob_l[i], prob_s[i]
            st = hmm_states[i]
            vol_pct = float(df_feat['feat_vol_atr_pct'].iloc[i])
            req_p = 0.42 if st == 1.0 else 0.36

            if p_l >= req_p and vol_pct >= 40.0:
                signals_arr[i] = "BUY"
            elif p_s >= req_p:
                signals_arr[i] = "SELL"

        for i in range(len(df_feat)):
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
                    t_log['hmm_state'] = st
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
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0, "avg_r": 0.0, "closed": []}

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
        avg_r = ev_usd / 50.0

        return {
            "trades": total_n,
            "net_pnl": net_pnl,
            "ret_pct": ret_pct,
            "win_rate": win_rate,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "ev_usd": ev_usd,
            "avg_r": avg_r,
            "closed": closed
        }

    # Run Track B (33.33 / 66.67)
    pl_b, ps_b, st9_b = get_track_predictions(33.33, 66.67)
    tr_b, eq_b = run_sim(pl_b, ps_b)
    m_b = calc_metrics(tr_b, eq_b)

    # Run Track C (25.0 / 75.0)
    pl_c, ps_c, st9_c = get_track_predictions(25.0, 75.0)
    tr_c, eq_c = run_sim(pl_c, ps_c)
    m_c = calc_metrics(tr_c, eq_c)

    print("=========================================================================================================================================")
    print("  🏆 LOCKED HEAD-TO-HEAD AUDIT SCORECARD: UNTOUCHED 2026 DATASET (JAN 1 - AUG 11, 2026)")
    print("=========================================================================================================================================")
    print(f"{'Performance Metric':<32} | {'Track B (Terziles 33.3/66.7%)':<32} | {'Track C (Quantiles 25.0/75.0%)':<32} | {'Winner':<12}")
    print("-" * 115)
    print(f"{'Total Trades Executed':<32} | {m_b['trades']:<32} | {m_c['trades']:<32} | {'-':<12}")
    print(f"{'Cumulative Net Return (%)':<32} | +{m_b['ret_pct']:<31.2f}% | +{m_c['ret_pct']:<31.2f}% | {'TRACK C 🏆' if m_c['ret_pct'] > m_b['ret_pct'] else 'TRACK B 🏆'}")
    print(f"{'Net Dollar Profit ($)':<32} | ${m_b['net_pnl']:<+31.2f} | ${m_c['net_pnl']:<+31.2f} | {'TRACK C 🏆' if m_c['net_pnl'] > m_b['net_pnl'] else 'TRACK B 🏆'}")
    print(f"{'Profit Factor (PF)':<32} | {m_b['pf']:<32.2f} | {m_c['pf']:<32.2f} | {'TRACK C 🏆' if m_c['pf'] > m_b['pf'] else 'TRACK B 🏆'}")
    print(f"{'Expectancy ($/Trade)':<32} | ${m_b['ev_usd']:<+31.2f} | ${m_c['ev_usd']:<+31.2f} | {'TRACK C 🏆' if m_c['ev_usd'] > m_b['ev_usd'] else 'TRACK B 🏆'}")
    print(f"{'Expectancy (R/Trade)':<32} | +{m_b['avg_r']:<31.3f}R | +{m_c['avg_r']:<31.3f}R | {'TRACK C 🏆' if m_c['avg_r'] > m_b['avg_r'] else 'TRACK B 🏆'}")
    print(f"{'Annualized Sharpe Ratio':<32} | {m_b['sharpe']:<32.2f} | {m_c['sharpe']:<32.2f} | {'TRACK C 🏆' if m_c['sharpe'] > m_b['sharpe'] else 'TRACK B 🏆'}")
    print(f"{'Maximum Drawdown (MDD %)':<32} | {m_b['max_dd']:<31.2f}% | {m_c['max_dd']:<31.2f}% | {'TRACK B 🏆' if m_b['max_dd'] < m_c['max_dd'] else 'TRACK C 🏆'}")
    print("=========================================================================================================================================\n")

    # Monthly Breakdown
    print("=========================================================================================================================================")
    print("  📅 2026 MONTHLY CONSISTENCY BREAKDOWN (TRACK B vs TRACK C)")
    print("=========================================================================================================================================")
    print(f"{'Month':<12} | {'Track B PnL ($)':<18} | {'Track C PnL ($)':<18} | {'Track B Return':<16} | {'Track C Return':<16} | {'Winner':<10}")
    print("-" * 105)

    months_2026 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
    for m_idx in range(1, 9):
        m_name = months_2026[m_idx - 1]
        sub_b = [t for t in m_b['closed'] if pd.to_datetime(t['exit_time']).month == m_idx]
        sub_c = [t for t in m_c['closed'] if pd.to_datetime(t['exit_time']).month == m_idx]

        pnl_b_m = sum([t['pnl_usd'] for t in sub_b]) if sub_b else 0.0
        pnl_c_m = sum([t['pnl_usd'] for t in sub_c]) if sub_c else 0.0

        ret_b_m = (pnl_b_m / 10000.0) * 100.0
        ret_c_m = (pnl_c_m / 10000.0) * 100.0

        winner = "TRACK C 🏆" if ret_c_m > ret_b_m else "TRACK B 🏆"
        print(f"{m_name:<12} | ${pnl_b_m:<+17.2f} | ${pnl_c_m:<+17.2f} | {ret_b_m:<+15.2f}% | {ret_c_m:<+15.2f}% | {winner:<10}")

    print("=========================================================================================================================================\n")

    # Regime Breakdown across HMM Bear (0), Range (1), Bull (2)
    print("=========================================================================================================================================")
    print("  🎯 REGIME CONSISTENCY BREAKDOWN ACROSS HMM STATES (BEAR / RANGE / BULL)")
    print("=========================================================================================================================================")
    print(f"{'HMM Regime State':<22} | {'Track B PnL ($)':<18} | {'Track C PnL ($)':<18} | {'Track B PF':<14} | {'Track C PF':<14}")
    print("-" * 95)

    states_names = {0: "State 0: Bear Trend", 1: "State 1: Range/Chop", 2: "State 2: Bull Trend"}
    for st_id, st_name in states_names.items():
        sub_b = [t for t in m_b['closed'] if t.get('hmm_state') == st_id]
        sub_c = [t for t in m_c['closed'] if t.get('hmm_state') == st_id]

        pnl_b_st = sum([t['pnl_usd'] for t in sub_b]) if sub_b else 0.0
        pnl_c_st = sum([t['pnl_usd'] for t in sub_c]) if sub_c else 0.0

        wins_b = [t['pnl_usd'] for t in sub_b if t['pnl_usd'] > 0]
        loss_b = [abs(t['pnl_usd']) for t in sub_b if t['pnl_usd'] < 0]
        pf_b = (sum(wins_b) / sum(loss_b)) if loss_b and sum(loss_b) > 0 else (1.0 if not loss_b else 0.0)

        wins_c = [t['pnl_usd'] for t in sub_c if t['pnl_usd'] > 0]
        loss_c = [abs(t['pnl_usd']) for t in sub_c if t['pnl_usd'] < 0]
        pf_c = (sum(wins_c) / sum(loss_c)) if loss_c and sum(loss_c) > 0 else (1.0 if not loss_c else 0.0)

        print(f"{st_name:<22} | ${pnl_b_st:<+17.2f} | ${pnl_c_st:<+17.2f} | {pf_b:<14.2f} | {pf_c:<14.2f}")

    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_locked_b_vs_c()
