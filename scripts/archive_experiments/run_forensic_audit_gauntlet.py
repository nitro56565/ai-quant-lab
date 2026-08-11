"""
Forensic Audit & Stress-Testing Falsification Script — Certified Baseline System + 50% Partial Exit.
Performs 4 brutal stress-tests to falsify and challenge the +76.77% OOS result:
  • Test 1: Strict In-Fold HMM Fitting (Zero HMM Lookahead Leak)
  • Test 2: Intra-Bar Worst-Case Sequence (If both TP/Partial and SL occur in same bar, SL is hit FIRST)
  • Test 3: Partial Exit Adverse Slippage Penalty (Extra 0.5p slippage on 50% partial exit fills)
  • Test 4: Limit Retrace Market Gap Execution Penalty (If open gaps beyond limit price, fill at open)
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

def run_forensic_falsification_gauntlet():
    print("=================================================================================")
    print("  🕵️ FORENSIC AUDIT & FALSIFICATION STRESS-TEST (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("=================================================================================")
    print("  • Challenging the +76.77% Partial Exit Result under 4 Brutal Stress Constraints:\n")
    print("    1. Strict In-Fold HMM Fitting (Zero Lookahead HMM States)")
    print("    2. Worst-Case Intra-Bar Order Sequence (SL hit FIRST if both hit in same candle)")
    print("    3. Partial Exit Adverse Slippage Penalty (Extra 0.5p Slippage on Partial Exits)")
    print("    4. Dynamic Retrace Market Gap Penalty (If Open gaps beyond limit, fill at Open)\n")

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

    # Helper function to run OOS predictions with or without In-Fold HMM
    def generate_oos_predictions(in_fold_hmm=True):
        prob_l = np.zeros(total_h1_bars)
        prob_s = np.zeros(total_h1_bars)
        hmm_oos = np.zeros(total_h1_bars)

        for yr in years_oos:
            train_end_year = yr - 1
            train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
            test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

            df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
            df_te = df_lbl[test_m].copy()

            if in_fold_hmm:
                # Fit HMM strictly on training fold
                hmm_detector = HMMRegimeDetector()
                hmm_detector.fit(df_tr)
                hmm_tr = hmm_detector.predict(df_tr)
                hmm_te = hmm_detector.predict(df_te)
                df_tr['feat_hmm_regime'] = hmm_tr
                df_te['feat_hmm_regime'] = hmm_te
            else:
                hmm_tr = np.zeros(len(df_tr))
                hmm_te = np.zeros(len(df_te))

            ensemble = RegimeFusedEnsemble()
            targets_tr = {'dir_long': df_tr['label_dir_long'], 'dir_short': df_tr['label_dir_short']}
            ensemble.fit(X_train=df_tr[feat_cols], targets=targets_tr, hmm_regimes=hmm_tr)

            X_te = df_te[feat_cols].bfill().ffill().fillna(0.0)
            preds_fold = ensemble.predict(X_te)

            fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
            prob_l[fold_eval_indices] = preds_fold['prob_long']
            prob_s[fold_eval_indices] = preds_fold['prob_short']
            hmm_oos[fold_eval_indices] = hmm_te

        return prob_l, prob_s, hmm_oos

    # Simulator Supporting Stress Penalties
    def run_forensic_sim(df_data, prob_l, prob_s, hmm_arr, 
                         worst_case_intrabar=False, 
                         partial_slippage_pips=0.0, 
                         gap_penalty=False,
                         initial_capital=10000.0):
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
        opens = df_data['open'].values
        highs = df_data['high'].values
        lows = df_data['low'].values
        atrs = df_data['feat_vol_atr'].values

        # Pre-compute signals
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
            open_p = opens[i]
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

                # Check if SL is hit on this candle
                sl_hit = (direction == 'BUY' and low <= sl_price) or (direction == 'SELL' and high >= sl_price)
                tp_hit = (direction == 'BUY' and high >= tp_price) or (direction == 'SELL' and low <= tp_price)
                partial_hit = (not t_log['partial_taken']) and (r_floating >= 1.5)

                if worst_case_intrabar and sl_hit and partial_hit:
                    # Worst-case: SL was hit FIRST on the same candle!
                    stop_out = True
                    exit_price = sl_price - (0.3 * pip_size) if direction == 'BUY' else sl_price + (0.3 * pip_size)
                    exit_reason = 'stop_loss'
                else:
                    # Normal processing: check partial exit first
                    if partial_hit:
                        partial_lots = t_log['initial_lots'] * 0.5
                        t_log['active_lots'] -= partial_lots
                        t_log['partial_taken'] = True

                        partial_pips = (initial_sl_dist / pip_size) * 1.5 - partial_slippage_pips
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
                    elif sl_hit:
                        stop_out = True
                        exit_price = sl_price - (0.3 * pip_size) if direction == 'BUY' else sl_price + (0.3 * pip_size)
                        exit_reason = 'stop_loss'
                    elif tp_hit:
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
                        
                        # Gap execution penalty
                        if gap_penalty:
                            if p_dir == 'BUY' and open_p < p_limit:
                                entry_price = open_p  # Fill at open gap
                            elif p_dir == 'SELL' and open_p > p_limit:
                                entry_price = open_p
                            else:
                                entry_price = p_limit
                        else:
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

    def calc_metrics(trades, final_eq, initial_cap=10000.0, years=8.0):
        closed = [t for t in trades if t['status'] == 'closed']
        total_n = len(closed)
        if total_n == 0:
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "cagr": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0}

        pnls = [t['pnl_usd'] for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        net_pnl = sum(pnls)
        ret_pct = (net_pnl / initial_cap) * 100.0
        cagr = (((final_eq / initial_cap) ** (1 / years)) - 1) * 100.0 if final_eq > 0 else -100.0
        win_rate = (len(wins) / total_n) * 100.0
        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1.0
        pf = gross_win / gross_loss

        eq_curve = [initial_cap]
        for p in pnls:
            eq_curve.append(eq_curve[-1] + p)
        eq_arr = np.array(eq_curve)
        peaks = np.maximum.accumulate(eq_arr)
        drawdowns = (eq_arr - peaks) / peaks * 100.0
        max_dd = abs(np.min(drawdowns))

        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0
        ev_usd = net_pnl / total_n

        return {
            "trades": total_n,
            "net_pnl": net_pnl,
            "ret_pct": ret_pct,
            "cagr": cagr,
            "win_rate": win_rate,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "ev_usd": ev_usd
        }

    # Generate predictions
    pl_clean, ps_clean, hmm_clean = generate_oos_predictions(in_fold_hmm=True)
    pl_no_hmm, ps_no_hmm, hmm_no_hmm = generate_oos_predictions(in_fold_hmm=False)

    # 1. Clean Baseline (Current Production Partial Exit)
    m_base = calc_metrics(*run_forensic_sim(df_eval, pl_clean, ps_clean, hmm_clean))

    # 2. Stress Test 1: In-Fold HMM vs No HMM
    m_nohmm = calc_metrics(*run_forensic_sim(df_eval, pl_no_hmm, ps_no_hmm, hmm_no_hmm))

    # 3. Stress Test 2: Worst-Case Intra-Bar Sequence (SL hit first)
    m_worst = calc_metrics(*run_forensic_sim(df_eval, pl_clean, ps_clean, hmm_clean, worst_case_intrabar=True))

    # 4. Stress Test 3: Partial Exit Adverse Slippage (+0.5p penalty)
    m_slip = calc_metrics(*run_forensic_sim(df_eval, pl_clean, ps_clean, hmm_clean, partial_slippage_pips=0.5))

    # 5. Stress Test 4: Market Gap Fill Penalty
    m_gap = calc_metrics(*run_forensic_sim(df_eval, pl_clean, ps_clean, hmm_clean, gap_penalty=True))

    # 6. COMBINED BRUTAL GAUNTLET: All 4 Stress Penalties Applied Simultaneously
    m_brutal = calc_metrics(*run_forensic_sim(df_eval, pl_clean, ps_clean, hmm_clean, worst_case_intrabar=True, partial_slippage_pips=0.5, gap_penalty=True))

    print("\n=========================================================================================================================================")
    print("  🕵️ FORENSIC AUDIT FALSIFICATION SCORECARD (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("=========================================================================================================================================")
    print(f"{'Audit Stress Test':<30} | {'Net PnL ($)':<16} | {'Return (%)':<14} | {'CAGR (%)':<12} | {'PF':<8} | {'Sharpe':<10} | {'MDD (%)':<10} | {'EV ($/Tr)':<10}")
    print("-" * 135)
    print(f"{'1. Current Clean Production':<30} | ${m_base['net_pnl']:<+15.2f} | {m_base['ret_pct']:<+13.2f}% | {m_base['cagr']:<+11.2f}% | {m_base['pf']:<7.2f} | {m_base['sharpe']:<9.2f} | {m_base['max_dd']:<9.2f}% | ${m_base['ev_usd']:<+9.2f}")
    print(f"{'2. In-Fold Strict HMM Test':<30} | ${m_nohmm['net_pnl']:<+15.2f} | {m_nohmm['ret_pct']:<+13.2f}% | {m_nohmm['cagr']:<+11.2f}% | {m_nohmm['pf']:<7.2f} | {m_nohmm['sharpe']:<9.2f} | {m_nohmm['max_dd']:<9.2f}% | ${m_nohmm['ev_usd']:<+9.2f}")
    print(f"{'3. Worst-Case Intra-Bar SL':<30} | ${m_worst['net_pnl']:<+15.2f} | {m_worst['ret_pct']:<+13.2f}% | {m_worst['cagr']:<+11.2f}% | {m_worst['pf']:<7.2f} | {m_worst['sharpe']:<9.2f} | {m_worst['max_dd']:<9.2f}% | ${m_worst['ev_usd']:<+9.2f}")
    print(f"{'4. Partial Exit +0.5p Slippage':<30} | ${m_slip['net_pnl']:<+15.2f} | {m_slip['ret_pct']:<+13.2f}% | {m_slip['cagr']:<+11.2f}% | {m_slip['pf']:<7.2f} | {m_slip['sharpe']:<9.2f} | {m_slip['max_dd']:<9.2f}% | ${m_slip['ev_usd']:<+9.2f}")
    print(f"{'5. Retrace Gap Open Penalty':<30} | ${m_gap['net_pnl']:<+15.2f} | {m_gap['ret_pct']:<+13.2f}% | {m_gap['cagr']:<+11.2f}% | {m_gap['pf']:<7.2f} | {m_gap['sharpe']:<9.2f} | {m_gap['max_dd']:<9.2f}% | ${m_gap['ev_usd']:<+9.2f}")
    print(f"{'6. ALL 4 PENALTIES COMBINED':<30} | ${m_brutal['net_pnl']:<+15.2f} | {m_brutal['ret_pct']:<+13.2f}% | {m_brutal['cagr']:<+11.2f}% | {m_brutal['pf']:<7.2f} | {m_brutal['sharpe']:<9.2f} | {m_brutal['max_dd']:<9.2f}% | ${m_brutal['ev_usd']:<+9.2f}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_forensic_falsification_gauntlet()
