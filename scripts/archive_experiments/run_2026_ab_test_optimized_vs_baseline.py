"""
Untouched 2026 Head-to-Head A/B Test: Certified Baseline V10 vs Optimized Engine (No ADX & No MACD).
Period: 2026-01-01 to 2026-08-11 (100% Untouched 2026 Dataset).
Compares current certified production baseline against the Stage 1 & 2 optimized model (No ADX, No MACD).
"""

import os, sys, time, joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from ai_engine.regime_hmm import HMMRegimeDetector
from lightgbm import LGBMClassifier

def run_2026_ab_test():
    print("=================================================================================")
    print("  🔒 UNTOUCHED 2026 A/B TEST: CERTIFIED BASELINE V10 vs OPTIMIZED NO-ADX/MACD ENGINE")
    print("=================================================================================")
    print("  • Period: 2026-01-01 to 2026-08-11 (100% Untouched 2026 Dataset)")
    print("  • Baseline Control: Certified V10 (Full Features with ADX & MACD)")
    print("  • Optimized Candidate: Compact Feature Matrix (WITHOUT ADX & WITHOUT MACD)\n")

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

    from research_engine.labeler import TripleBarrierLabeler
    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_feat)
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    # Historical Training Window (2014-01-01 to 2025-12-31)
    train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    test_2026_m = (df_lbl.index >= "2026-01-01") & (df_lbl.index <= "2026-08-11")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_2026_m].copy()

    # Fit 9-State Regimes
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

    # Trainer function
    def train_and_predict_2026(excluded_feats):
        active_feats = [c for c in all_feat_cols if c not in excluded_feats]
        m_long = {}
        m_short = {}
        X_tr_mat = df_tr[active_feats].values
        y_l_tr = df_tr['label_dir_long'].values
        y_s_tr = df_tr['label_dir_short'].values

        for s in range(9):
            mask_s = (state_tr == s)
            if np.sum(mask_s) >= 30:
                ml = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
                ms = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=42, verbose=-1)
                ml.fit(X_tr_mat[mask_s], y_l_tr[mask_s])
                ms.fit(X_tr_mat[mask_s], y_s_tr[mask_s])
                m_long[s] = ml
                m_short[s] = ms

        X_te_mat = df_te[active_feats].values
        pl_te = np.zeros(len(df_te))
        ps_te = np.zeros(len(df_te))

        for s in range(9):
            mask_te = (state_te == s)
            if not np.any(mask_te):
                continue
            if s in m_long:
                pl_te[mask_te] = m_long[s].predict_proba(X_te_mat[mask_te])[:, 1]
                ps_te[mask_te] = m_short[s].predict_proba(X_te_mat[mask_te])[:, 1]
            else:
                pl_te[mask_te] = 0.30
                ps_te[mask_te] = 0.30

        return pl_te, ps_te

    # 1. Baseline Model (Full Features with ADX & MACD)
    pl_base, ps_base = train_and_predict_2026(excluded_feats=[])

    # 2. Optimized Model (WITHOUT ADX & WITHOUT MACD)
    excluded_opt = ['feat_trend_adx', 'feat_trend_di_spread', 'feat_macd_hist', 'feat_macd_line', 'feat_macd_signal']
    pl_opt, ps_opt = train_and_predict_2026(excluded_feats=excluded_opt)

    # Simulator
    def run_sim(df_data, prob_l, prob_s, hmm_arr):
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

        timestamps = df_data.index
        closes = df_data['close'].values
        highs = df_data['high'].values
        lows = df_data['low'].values
        atrs = df_data['feat_vol_atr'].values

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
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0, "avg_r": 0.0}

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
            "avg_r": avg_r
        }

    m_base = calc_metrics(*run_sim(df_te, pl_base, ps_base, hmm_te))
    m_opt = calc_metrics(*run_sim(df_te, pl_opt, ps_opt, hmm_te))

    print("=========================================================================================================================================")
    print("  🏆 UNTOUCHED 2026 HEAD-TO-HEAD A/B TEST: CERTIFIED BASELINE V10 vs OPTIMIZED ENGINE")
    print("=========================================================================================================================================")
    print(f"{'Performance Metric':<32} | {'Certified Baseline (V10)':<32} | {'Optimized Candidate (No ADX/MACD)':<32} | {'A/B Winner':<12}")
    print("-" * 115)
    print(f"{'Total Trades Executed':<32} | {m_base['trades']:<32} | {m_opt['trades']:<32} | {'-':<12}")
    print(f"{'Cumulative Net Return (%)':<32} | +{m_base['ret_pct']:<31.2f}% | +{m_opt['ret_pct']:<31.2f}% | {'OPTIMIZED 🚀' if m_opt['ret_pct'] > m_base['ret_pct'] else 'BASELINE 🏆'}")
    print(f"{'Net Dollar Profit ($)':<32} | ${m_base['net_pnl']:<+31.2f} | ${m_opt['net_pnl']:<+31.2f} | {'OPTIMIZED 🚀' if m_opt['net_pnl'] > m_base['net_pnl'] else 'BASELINE 🏆'}")
    print(f"{'Profit Factor (PF)':<32} | {m_base['pf']:<32.2f} | {m_opt['pf']:<32.2f} | {'OPTIMIZED 🚀' if m_opt['pf'] > m_base['pf'] else 'BASELINE 🏆'}")
    print(f"{'Expectancy ($/Trade)':<32} | ${m_base['ev_usd']:<+31.2f} | ${m_opt['ev_usd']:<+31.2f} | {'OPTIMIZED 🚀' if m_opt['ev_usd'] > m_base['ev_usd'] else 'BASELINE 🏆'}")
    print(f"{'Expectancy (R/Trade)':<32} | +{m_base['avg_r']:<31.3f}R | +{m_opt['avg_r']:<31.3f}R | {'OPTIMIZED 🚀' if m_opt['avg_r'] > m_base['avg_r'] else 'BASELINE 🏆'}")
    print(f"{'Annualized Sharpe Ratio':<32} | {m_base['sharpe']:<32.2f} | {m_opt['sharpe']:<32.2f} | {'OPTIMIZED 🚀' if m_opt['sharpe'] > m_base['sharpe'] else 'BASELINE 🏆'}")
    print(f"{'Maximum Drawdown (MDD %)':<32} | {m_base['max_dd']:<31.2f}% | {m_opt['max_dd']:<31.2f}% | {'OPTIMIZED 🚀' if m_opt['max_dd'] < m_base['max_dd'] else 'BASELINE 🏆'}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_2026_ab_test()
