"""
Phase 1 Partial Exit Experiment Script — Certified Baseline System (2018-2025 EURUSD H1).
Evaluates 4 Partial Exit Strategies across 8-Fold Rolling Walk-Forward Out-of-Sample Gauntlet:
  • Track A: No Partial Exit (Baseline Champion: 100% position holds to full TP/SL/Time)
  • Track B: 50% Partial Exit at +1.0R Floating Profit (50% closed, 50% holds to full TP/SL)
  • Track C: 50% Partial Exit at +1.5R Floating Profit (50% closed, 50% holds to full TP/SL)
  • Track D: 50% Partial Exit at +2.0R Floating Profit (50% closed, 50% holds to full TP/SL)
"""

import os, sys, time
import numpy as np
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
import lightgbm as lgb
from ai_engine.ensemble import RegimeFusedEnsemble

def run_phase1_partial_exit_gauntlet():
    print("=================================================================================")
    print("  🧪 PHASE 1 PARTIAL EXIT EXPERIMENT: 4-TRACK OOS GAUNTLET (2018-2025 EURUSD H1)")
    print("=================================================================================")
    print("  • Track A: No Partial Exit (Baseline Champion: 100% holds to full TP/SL)")
    print("  • Track B: 50% Partial Exit at +1.0R Floating Profit")
    print("  • Track C: 50% Partial Exit at +1.5R Floating Profit")
    print("  • Track D: 50% Partial Exit at +2.0R Floating Profit\n")

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
    prob_long_oos = np.zeros(total_h1_bars)
    prob_short_oos = np.zeros(total_h1_bars)

    years_oos = list(range(2018, 2026))

    for yr in years_oos:
        train_end_year = yr - 1
        train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
        test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

        df_tr = df_lbl[train_m].dropna(subset=['label_dir_long'])
        df_te = df_lbl[test_m]

        hmm_tr = df_tr['feat_hmm_regime'].values if 'feat_hmm_regime' in df_tr.columns else np.zeros(len(df_tr))
        hmm_te = df_te['feat_hmm_regime'].values if 'feat_hmm_regime' in df_te.columns else np.zeros(len(df_te))

        ensemble = RegimeFusedEnsemble()
        targets_tr = {'dir_long': df_tr['label_dir_long'], 'dir_short': df_tr['label_dir_short']}
        ensemble.fit(X_train=df_tr[feat_cols], targets=targets_tr, hmm_regimes=hmm_tr)

        X_te = df_te[feat_cols].bfill().ffill().fillna(0.0)
        preds_fold = ensemble.predict(X_te)

        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
        prob_long_oos[fold_eval_indices] = preds_fold['prob_long']
        prob_short_oos[fold_eval_indices] = preds_fold['prob_short']

    signals_cert = np.full(total_h1_bars, "NONE", dtype=object)
    hmm_eval = df_eval['feat_hmm_regime'].values if 'feat_hmm_regime' in df_eval.columns else np.zeros(total_h1_bars)

    for i in range(total_h1_bars):
        hour = df_eval.index[i].hour if isinstance(df_eval.index, pd.DatetimeIndex) else 0
        if 13 <= hour <= 16:
            continue

        p_l, p_s = prob_long_oos[i], prob_short_oos[i]
        st = hmm_eval[i]
        vol_pct = float(df_eval['feat_vol_atr_pct'].iloc[i])
        req_p = 0.42 if st == 1.0 else 0.36

        if p_l >= req_p and vol_pct >= 40.0:
            signals_cert[i] = "BUY"
        elif p_s >= req_p:
            signals_cert[i] = "SELL"

    # Execution Simulator Supporting Phase 1 Partial Exits
    def run_partial_exit_sim(df_data, signals_arr, partial_r_target=None, initial_capital=10000.0):
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

        for i in range(len(df_data)):
            timestamp = timestamps[i]
            close = closes[i]
            high = highs[i]
            low = lows[i]
            atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

            if in_trade:
                t_log = trades[-1]
                lots = t_log['active_lots']
                stop_out = False
                exit_price = 0.0
                exit_reason = None
                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'

                # Calculate floating R-multiple
                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                # 50% Partial Exit Trigger
                if partial_r_target is not None and not t_log['partial_taken'] and r_floating >= partial_r_target:
                    partial_lots = t_log['initial_lots'] * 0.5
                    t_log['active_lots'] -= partial_lots
                    t_log['partial_taken'] = True
                    
                    # Partial exit price at target level
                    partial_pips = (initial_sl_dist / pip_size) * partial_r_target
                    partial_exit_price = entry_price + (partial_pips * pip_size) if direction == 'BUY' else entry_price - (partial_pips * pip_size)
                    
                    partial_gross = partial_pips * (partial_lots * 10.0)
                    partial_comm = 7.0 * partial_lots
                    partial_net = partial_gross - partial_comm
                    
                    t_log['partial_pnl_usd'] = partial_net
                    t_log['partial_pips'] = partial_pips
                    current_equity += partial_net

                # Check Exits for remaining active position
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

    def calc_phase1_metrics(trades, final_eq, initial_cap=10000.0, years=8.0):
        closed = [t for t in trades if t['status'] == 'closed']
        total_n = len(closed)
        if total_n == 0:
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "avg_r": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0, "avg_win_usd": 0.0}

        pnls = [t['pnl_usd'] for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        net_pnl = sum(pnls)
        ret_pct = (net_pnl / initial_cap) * 100.0
        win_rate = (len(wins) / total_n) * 100.0
        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1.0
        pf = gross_win / gross_loss

        avg_win_usd = np.mean(wins) if wins else 0.0
        ev_usd = net_pnl / total_n
        avg_r = ev_usd / 50.0  # Normalized to $50 base risk

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
            "ev_usd": ev_usd,
            "avg_win_usd": avg_win_usd
        }

    # Run 4 Phase-1 Tracks
    m_a = calc_phase1_metrics(*run_partial_exit_sim(df_eval, signals_cert, partial_r_target=None))
    m_b = calc_phase1_metrics(*run_partial_exit_sim(df_eval, signals_cert, partial_r_target=1.0))
    m_c = calc_phase1_metrics(*run_partial_exit_sim(df_eval, signals_cert, partial_r_target=1.5))
    m_d = calc_phase1_metrics(*run_partial_exit_sim(df_eval, signals_cert, partial_r_target=2.0))

    print("\n=========================================================================================================================================")
    print("  🏆 PHASE 1 PARTIAL EXIT EXPERIMENT SCORECARD (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("=========================================================================================================================================")
    print(f"{'Required Phase-1 Metric':<28} | {'Track A: No Partial Exit':<26} | {'Track B: 50% @ +1.0R':<22} | {'Track C: 50% @ +1.5R':<22} | {'Track D: 50% @ +2.0R':<22}")
    print("-" * 135)
    print(f"{'Profit Factor (PF)':<28} | {m_a['pf']:<26.2f} | {m_b['pf']:<22.2f} | {m_c['pf']:<22.2f} | {m_d['pf']:<22.2f}")
    print(f"{'Expectancy / Avg R (R/Trade)':<28} | +{m_a['avg_r']:<25.3f}R | +{m_b['avg_r']:<21.3f}R | +{m_c['avg_r']:<21.3f}R | +{m_d['avg_r']:<21.3f}R")
    print(f"{'Maximum Drawdown (MDD %)':<28} | {m_a['max_dd']:<25.2f}% | {m_b['max_dd']:<21.2f}% | {m_c['max_dd']:<21.2f}% | {m_d['max_dd']:<21.2f}%")
    print(f"{'Annualized Sharpe Ratio':<28} | {m_a['sharpe']:<26.2f} | {m_b['sharpe']:<22.2f} | {m_c['sharpe']:<22.2f} | {m_d['sharpe']:<22.2f}")
    print(f"{'Total Cumulative Return (%)':<28} | +{m_a['ret_pct']:<25.2f}% | {m_b['ret_pct']:<+21.2f}% | {m_c['ret_pct']:<+21.2f}% | {m_d['ret_pct']:<+21.2f}%")
    print(f"{'Average Winner ($)':<28} | ${m_a['avg_win_usd']:<25.2f} | ${m_b['avg_win_usd']:<21.2f} | ${m_c['avg_win_usd']:<21.2f} | ${m_d['avg_win_usd']:<21.2f}")
    print(f"{'Total Executed OOS Trades':<28} | {m_a['trades']:<26} | {m_b['trades']:<22} | {m_c['trades']:<22} | {m_d['trades']:<22}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_phase1_partial_exit_gauntlet()
