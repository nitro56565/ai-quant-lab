"""
Exness Standard Account Overnight Swap Drag Experiment Script (2018-2025 EURUSD H1).
Evaluates 5 Swap Tracks & Duration Breakdown across 8-Fold Rolling Walk-Forward Out-of-Sample Gauntlet:
  • Track A: Baseline (No Swap)
  • Track B: Realistic Exness Swap (Long -0.62p, Short +0.15p, Wed 3x Triple Swap)
  • Track C: 2x Exness Swap (Long -1.24p, Short +0.30p)
  • Track D: 3x Exness Swap (Long -1.86p, Short +0.45p)
  • Track E: Worst-Case Swap (-1.0p penalty on all overnight holds, Wed 3x)
"""

import os, sys, time
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector
from ai_engine.ensemble import RegimeFusedEnsemble

def run_exness_swap_gauntlet():
    print("=================================================================================")
    print("  🧪 EXNESS STANDARD ACCOUNT OVERNIGHT SWAP EXPERIMENT (2018-2025 EURUSD H1)")
    print("=================================================================================")
    print("  • Broker Specifications: Exness Standard Account EURUSD")
    print("  • Base Long Swap: -0.62 pips/night (-$6.20 / Lot)")
    print("  • Base Short Swap: +0.15 pips/night (+$1.50 / Lot)")
    print("  • Triple Swap Day: Wednesday 21:00 UTC (3x Rollover Charge)\n")

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

    feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[feat_cols] = df_lbl[feat_cols].bfill().ffill().fillna(0.0)

    eval_mask = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval = df_feat[eval_mask].copy()
    total_h1_bars = len(df_eval)
    years_oos = list(range(2018, 2026))

    prob_l = np.zeros(total_h1_bars)
    prob_s = np.zeros(total_h1_bars)
    hmm_oos = np.zeros(total_h1_bars)

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
        df_tr['feat_hmm_regime'] = hmm_tr
        df_te['feat_hmm_regime'] = hmm_te

        ensemble = RegimeFusedEnsemble()
        targets_tr = {'dir_long': df_tr['label_dir_long'], 'dir_short': df_tr['label_dir_short']}
        ensemble.fit(X_train=df_tr[feat_cols], targets=targets_tr, hmm_regimes=hmm_tr)

        X_te = df_te[feat_cols].bfill().ffill().fillna(0.0)
        preds_fold = ensemble.predict(X_te)

        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
        prob_l[fold_eval_indices] = preds_fold['prob_long']
        prob_s[fold_eval_indices] = preds_fold['prob_short']
        hmm_oos[fold_eval_indices] = hmm_te

    # Execution Simulator Supporting Exness Swap Rules
    def run_swap_sim(df_data, prob_l, prob_s, hmm_arr, swap_track="A", initial_capital=10000.0):
        pip_size = 0.0001
        trades = []
        in_trade = False
        direction = None
        entry_price = 0.0
        entry_time = None
        sl_price = 0.0
        tp_price = 0.0
        initial_sl_dist = 0.0
        current_equity = initial_capital
        pending_order = None

        timestamps = df_data.index
        closes = df_data['close'].values
        highs = df_data['high'].values
        lows = df_data['low'].values
        atrs = df_data['feat_vol_atr'].values

        # Base Exness Swap Rates (in pips)
        if swap_track == "A":
            long_swap_pip = 0.0; short_swap_pip = 0.0; mult = 1.0
        elif swap_track == "B":
            long_swap_pip = -0.62; short_swap_pip = +0.15; mult = 1.0
        elif swap_track == "C":
            long_swap_pip = -0.62; short_swap_pip = +0.15; mult = 2.0
        elif swap_track == "D":
            long_swap_pip = -0.62; short_swap_pip = +0.15; mult = 3.0
        elif swap_track == "E":
            long_swap_pip = -1.00; short_swap_pip = -1.00; mult = 1.0

        signals_arr = np.full(len(df_data), "NONE", dtype=object)
        for i in range(len(df_data)):
            hour = timestamps[i].hour if isinstance(timestamps, pd.DatetimeIndex) else 0
            if 13 <= hour <= 16:
                continue
            p_l, p_s = prob_l[i], prob_s[i]
            st = hmm_arr[i]
            vol_pct = float(df_data['feat_vol_atr_pct'].iloc[i])
            req_p = 0.42 if st == 1.0 else 0.36

            if p_l >= req_p and vol_pct >= 40.0:
                signals_arr[i] = "BUY"
            elif p_s >= req_p:
                signals_arr[i] = "SELL"

        for i in range(len(df_data)):
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

                # Calculate floating R
                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                # 50% Partial Exit at +1.5R
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

                # Check Exits
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

                # Rollover Check: Check if position crosses 21:00 UTC
                if timestamp.hour == 21 and swap_track != "A":
                    # Determine rollover multiplier (3x on Wednesday)
                    night_mult = 3.0 if timestamp.weekday() == 2 else 1.0
                    base_pip = long_swap_pip if direction == 'BUY' else short_swap_pip
                    swap_cost_pip = base_pip * mult * night_mult
                    swap_cost_usd = swap_cost_pip * (t_log['active_lots'] * 10.0)
                    t_log['total_swap_usd'] += swap_cost_usd
                    t_log['overnight_holds'] += 1
                    if timestamp.weekday() in (4, 5, 6):
                        t_log['weekend_held'] = True

                if stop_out:
                    in_trade = False
                    rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    rem_lots = t_log['active_lots']
                    rem_gross = rem_pips * (rem_lots * 10.0)
                    rem_comm = 7.0 * rem_lots
                    
                    trade_swap = t_log['total_swap_usd']
                    rem_net = rem_gross - rem_comm + trade_swap

                    total_trade_net = rem_net + t_log.get('partial_pnl_usd', 0.0)

                    t_log['exit_time'] = timestamp
                    t_log['holding_hours'] = (timestamp - entry_time).total_seconds() / 3600.0
                    t_log['exit_price'] = exit_price
                    t_log['exit_reason'] = exit_reason
                    t_log['pnl_pips'] = rem_pips
                    t_log['pnl_usd'] = total_trade_net
                    t_log['gross_usd'] = (rem_gross + t_log.get('partial_pnl_usd', 0.0))
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
                            'total_swap_usd': 0.0,
                            'overnight_holds': 0,
                            'weekend_held': False,
                            'status': 'open'
                        })

            if not in_trade and pending_order is None and signals_arr[i] in ('BUY', 'SELL'):
                sig = signals_arr[i]
                retrace_pips = (atr / pip_size) * 0.25
                limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
                pending_order = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

        return trades, current_equity

    def calc_metrics(trades, final_eq, initial_cap=10000.0, years=8.0):
        closed = [t for t in trades if t['status'] == 'closed']
        total_n = len(closed)
        if total_n == 0:
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "avg_r": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "total_swap": 0.0, "swap_pct_gross": 0.0, "overnight_pct": 0.0, "avg_hold_h": 0.0, "gross_pnl": 0.0}

        pnls = [t['pnl_usd'] for t in closed]
        swaps = [t['total_swap_usd'] for t in closed]
        grosses = [t['gross_usd'] for t in closed]
        holds = [t['holding_hours'] for t in closed]

        net_pnl = sum(pnls)
        total_swap = sum(swaps)
        gross_pnl = sum(grosses)
        ret_pct = (net_pnl / initial_cap) * 100.0
        win_rate = (len([p for p in pnls if p > 0]) / total_n) * 100.0

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1.0
        pf = gross_win / gross_loss

        avg_r = (net_pnl / total_n) / 50.0
        swap_pct_gross = (abs(total_swap) / gross_win * 100.0) if gross_win > 0 else 0.0
        overnight_count = len([t for t in closed if t['overnight_holds'] > 0])
        overnight_pct = (overnight_count / total_n) * 100.0
        avg_hold_h = np.mean(holds) if holds else 0.0

        eq_curve = [initial_cap]
        for p in pnls:
            eq_curve.append(eq_curve[-1] + p)
        eq_arr = np.array(eq_curve)
        peaks = np.maximum.accumulate(eq_arr)
        drawdowns = (eq_arr - peaks) / peaks * 100.0
        max_dd = abs(np.min(drawdowns))

        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0

        return {
            "trades": total_n,
            "net_pnl": net_pnl,
            "ret_pct": ret_pct,
            "avg_r": avg_r,
            "win_rate": win_rate,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "total_swap": total_swap,
            "swap_pct_gross": swap_pct_gross,
            "overnight_pct": overnight_pct,
            "avg_hold_h": avg_hold_h,
            "gross_pnl": gross_pnl,
            "closed_trades": closed
        }

    # Run 5 Tracks
    m_a = calc_metrics(*run_swap_sim(df_eval, prob_l, prob_s, hmm_oos, swap_track="A"))
    m_b = calc_metrics(*run_swap_sim(df_eval, prob_l, prob_s, hmm_oos, swap_track="B"))
    m_c = calc_metrics(*run_swap_sim(df_eval, prob_l, prob_s, hmm_oos, swap_track="C"))
    m_d = calc_metrics(*run_swap_sim(df_eval, prob_l, prob_s, hmm_oos, swap_track="D"))
    m_e = calc_metrics(*run_swap_sim(df_eval, prob_l, prob_s, hmm_oos, swap_track="E"))

    # Calculate Swap Drag for Track B
    swap_drag = m_a['net_pnl'] - m_b['net_pnl']
    swap_drag_pct = (swap_drag / m_a['net_pnl'] * 100.0) if m_a['net_pnl'] > 0 else 0.0

    print("=========================================================================================================================================")
    print("  🏆 EXNESS SWAP DRAG EXPERIMENT SCORECARD (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("=========================================================================================================================================")
    print(f"{'Performance Metric':<28} | {'Track A: Baseline (No Swap)':<28} | {'Track B: Exness Realistic':<24} | {'Track C: 2x Swap':<20} | {'Track D: 3x Swap':<20} | {'Track E: Worst-Case':<20}")
    print("-" * 155)
    print(f"{'Cumulative Net Return (%)':<28} | +{m_a['ret_pct']:<27.2f}% | {m_b['ret_pct']:<+23.2f}% | {m_c['ret_pct']:<+19.2f}% | {m_d['ret_pct']:<+19.2f}% | {m_e['ret_pct']:<+19.2f}%")
    print(f"{'Cumulative Net PnL ($)':<28} | ${m_a['net_pnl']:<+27.2f} | ${m_b['net_pnl']:<+23.2f} | ${m_c['net_pnl']:<+19.2f} | ${m_d['net_pnl']:<+19.2f} | ${m_e['net_pnl']:<+19.2f}")
    print(f"{'Profit Factor (PF)':<28} | {m_a['pf']:<28.2f} | {m_b['pf']:<24.2f} | {m_c['pf']:<20.2f} | {m_d['pf']:<20.2f} | {m_e['pf']:<20.2f}")
    print(f"{'Expectancy (R / Trade)':<28} | +{m_a['avg_r']:<27.3f}R | +{m_b['avg_r']:<23.3f}R | +{m_c['avg_r']:<19.3f}R | +{m_d['avg_r']:<19.3f}R | +{m_e['avg_r']:<19.3f}R")
    print(f"{'Maximum Drawdown (MDD %)':<28} | {m_a['max_dd']:<27.2f}% | {m_b['max_dd']:<23.2f}% | {m_c['max_dd']:<19.2f}% | {m_d['max_dd']:<19.2f}% | {m_e['max_dd']:<19.2f}%")
    print(f"{'Annualized Sharpe Ratio':<28} | {m_a['sharpe']:<28.2f} | {m_b['sharpe']:<24.2f} | {m_c['sharpe']:<20.2f} | {m_d['sharpe']:<20.2f} | {m_e['sharpe']:<20.2f}")
    print(f"{'Total Swap Paid ($)':<28} | ${m_a['total_swap']:<+27.2f} | ${m_b['total_swap']:<+23.2f} | ${m_c['total_swap']:<+19.2f} | ${m_d['total_swap']:<+19.2f} | ${m_e['total_swap']:<+19.2f}")
    print(f"{'Swap % of Gross Profit':<28} | {m_a['swap_pct_gross']:<27.2f}% | {m_b['swap_pct_gross']:<23.2f}% | {m_c['swap_pct_gross']:<19.2f}% | {m_d['swap_pct_gross']:<19.2f}% | {m_e['swap_pct_gross']:<19.2f}%")
    print(f"{'% of Trades Held Overnight':<28} | {m_a['overnight_pct']:<27.1f}% | {m_b['overnight_pct']:<23.1f}% | {m_c['overnight_pct']:<19.1f}% | {m_d['overnight_pct']:<19.1f}% | {m_e['overnight_pct']:<19.1f}%")
    print(f"{'Average Holding Time (hours)':<28} | {m_a['avg_hold_h']:<28.1f}h | {m_b['avg_hold_h']:<24.1f}h | {m_c['avg_hold_h']:<20.1f}h | {m_d['avg_hold_h']:<20.1f}h | {m_e['avg_hold_h']:<20.1f}h")
    print("=========================================================================================================================================\n")

    print(f"📊 EXNESS SWAP DRAG IMPACT SUMMARY (TRACK B):")
    print(f"  • Net PnL Without Swap: ${m_a['net_pnl']:+.2f}")
    print(f"  • Net PnL With Exness Swap: ${m_b['net_pnl']:+.2f}")
    print(f"  • Total Exness Swap Cost: ${m_b['total_swap']:+.2f}")
    print(f"  • Net Swap Drag Impact: ${swap_drag:+.2f} ({swap_drag_pct:.2f}% of Total PnL)\n")

    # Duration Breakdown Matrix for Track B
    print("=========================================================================================================================================")
    print("  ⏱️ DURATION BREAKDOWN MATRIX FOR EXNESS SWAP IMPACT (TRACK B)")
    print("=========================================================================================================================================")
    print(f"{'Holding Duration Bucket':<28} | {'Trade Count':<14} | {'Net PnL ($)':<16} | {'Total Swap ($)':<16} | {'Win Rate (%)':<14} | {'Avg PnL / Trade ($)':<20}")
    print("-" * 115)

    closed_b = m_b['closed_trades']
    buckets = [
        ("0 - 1 Hours", lambda t: t['holding_hours'] <= 1.0),
        ("1 - 4 Hours", lambda t: 1.0 < t['holding_hours'] <= 4.0),
        ("4 - 12 Hours", lambda t: 4.0 < t['holding_hours'] <= 12.0),
        ("12 - 24 Hours", lambda t: 12.0 < t['holding_hours'] <= 24.0),
        ("> 24 Hours", lambda t: t['holding_hours'] > 24.0),
        ("Weekend-Held Trades", lambda t: t['weekend_held'])
    ]

    for b_name, b_filter in buckets:
        sub_trades = [t for t in closed_b if b_filter(t)]
        n_b = len(sub_trades)
        if n_b > 0:
            b_pnl = sum([t['pnl_usd'] for t in sub_trades])
            b_swap = sum([t['total_swap_usd'] for t in sub_trades])
            b_wr = (len([t for t in sub_trades if t['pnl_usd'] > 0]) / n_b) * 100.0
            b_avg_pnl = b_pnl / n_b
            print(f"{b_name:<28} | {n_b:<14} | ${b_pnl:<+15.2f} | ${b_swap:<+15.2f} | {b_wr:<13.1f}% | ${b_avg_pnl:<+19.2f}")
        else:
            print(f"{b_name:<28} | {0:<14} | ${0.0:<+15.2f} | ${0.0:<+15.2f} | {0.0:<13.1f}% | ${0.0:<+19.2f}")

    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_exness_swap_gauntlet()
