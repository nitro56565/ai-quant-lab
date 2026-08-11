"""
Advanced Protection & Trailing Experiment Script — Certified Baseline System (2018-2025 EURUSD H1).
Evaluates 5 Protection & Exit Strategies across 8-Fold Rolling Walk-Forward Out-of-Sample Gauntlet:
  • Track A: No Trailing (Certified Baseline Champion: Static 2.0 ATR SL)
  • Track B: Breakeven Protection Only after +1.2R
  • Track C: Market Structure Trailing (Previous 3-Bar H1 Swing Low/High)
  • Track D: ATR Trailing ONLY after +2.0R Floating Profit
  • Track E: Regime-Dependent Trailing (Trail ONLY in Strong Trend Regimes with High Model Prob)
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

def run_advanced_protection_gauntlet():
    print("=================================================================================")
    print("  🧪 ADVANCED PROTECTION & TRAILING EXPERIMENT: 5-TRACK OOS GAUNTLET (2018-2025)")
    print("=================================================================================")
    print("  • Track A: No Trailing (Certified Baseline Champion: Static 2.0 ATR SL)")
    print("  • Track B: Breakeven Protection Only after +1.2R Floating Profit")
    print("  • Track C: Market Structure Trailing (3-Bar H1 Swing Low / High)")
    print("  • Track D: Delayed ATR Trailing (ONLY after +2.0R Floating Profit)")
    print("  • Track E: Regime-Dependent Trailing (ONLY in Bull/Bear Trend Regimes when P >= 0.40)\n")

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

    # 3-Bar Swing Low and High for Structure-based trailing
    df_feat['swing_low_3'] = df_feat['low'].rolling(window=3).min()
    df_feat['swing_high_3'] = df_feat['high'].rolling(window=3).max()

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

    # Execution Simulator Supporting Advanced Trailing Modes
    def run_advanced_sim(df_data, signals_arr, mode="NONE", initial_capital=10000.0):
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
        swing_lows = df_data['swing_low_3'].values
        swing_highs = df_data['swing_high_3'].values
        hmms = df_data['feat_hmm_regime'].values if 'feat_hmm_regime' in df_data.columns else np.zeros(len(df_data))

        for i in range(len(df_data)):
            timestamp = timestamps[i]
            close = closes[i]
            high = highs[i]
            low = lows[i]
            atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

            if in_trade:
                t_log = trades[-1]
                lots = t_log['lots']
                stop_out = False
                exit_price = 0.0
                exit_reason = None
                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'

                # Floating profit in R-multiples
                floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                # Advanced Protection Rules
                if mode == "BREAKEVEN_12R":
                    if r_floating >= 1.2 and not t_log.get('be_applied'):
                        be_price = entry_price + (1.0 * pip_size) if direction == 'BUY' else entry_price - (1.0 * pip_size)
                        if direction == 'BUY' and be_price > sl_price:
                            sl_price = be_price
                            t_log['be_applied'] = True
                        elif direction == 'SELL' and be_price < sl_price:
                            sl_price = be_price
                            t_log['be_applied'] = True

                elif mode == "STRUCTURE_SWING":
                    s_low = swing_lows[i] if not np.isnan(swing_lows[i]) else low
                    s_high = swing_highs[i] if not np.isnan(swing_highs[i]) else high
                    if direction == 'BUY':
                        new_sl = s_low - (0.5 * pip_size)
                        if new_sl > sl_price:
                            sl_price = new_sl
                            t_log['structure_updated'] = True
                    else: # SELL
                        new_sl = s_high + (0.5 * pip_size)
                        if new_sl < sl_price:
                            sl_price = new_sl
                            t_log['structure_updated'] = True

                elif mode == "DELAYED_ATR_2R":
                    if r_floating >= 2.0:
                        trail_dist = atr * 1.5
                        if direction == 'BUY':
                            new_sl = high - trail_dist
                            if new_sl > sl_price:
                                sl_price = new_sl
                                t_log['delayed_trail_updated'] = True
                        else: # SELL
                            new_sl = low + trail_dist
                            if new_sl < sl_price:
                                sl_price = new_sl
                                t_log['delayed_trail_updated'] = True

                elif mode == "REGIME_DEPENDENT":
                    st = hmms[i]
                    p_val = prob_long_oos[i] if direction == 'BUY' else prob_short_oos[i]
                    # Only trail in Bull (2.0) or Bear (0.0) trends when P >= 0.40
                    if st in (0.0, 2.0) and p_val >= 0.40:
                        trail_dist = atr * 1.8
                        if direction == 'BUY':
                            new_sl = high - trail_dist
                            if new_sl > sl_price:
                                sl_price = new_sl
                                t_log['regime_trail_updated'] = True
                        else: # SELL
                            new_sl = low + trail_dist
                            if new_sl < sl_price:
                                sl_price = new_sl
                                t_log['regime_trail_updated'] = True

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
                    exit_reason = 'protection_stop' if (t_log.get('be_applied') or t_log.get('structure_updated') or t_log.get('delayed_trail_updated') or t_log.get('regime_trail_updated')) else 'stop_loss'
                elif direction == 'SELL' and high >= sl_price:
                    stop_out = True
                    exit_price = sl_price + (0.3 * pip_size)
                    exit_reason = 'protection_stop' if (t_log.get('be_applied') or t_log.get('structure_updated') or t_log.get('delayed_trail_updated') or t_log.get('regime_trail_updated')) else 'stop_loss'
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
                    pnl_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    gross_usd = pnl_pips * (lots * 10.0)
                    comm_usd = 7.0 * lots
                    net_usd = gross_usd - comm_usd

                    t_log['exit_time'] = timestamp
                    t_log['exit_price'] = exit_price
                    t_log['exit_reason'] = exit_reason
                    t_log['pnl_pips'] = pnl_pips
                    t_log['pnl_usd'] = net_usd
                    t_log['status'] = 'closed'
                    current_equity += net_usd

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
                            'lots': lots,
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
            return {"trades": 0, "net_pnl": 0.0, "ret_pct": 0.0, "cagr": 0.0, "win_rate": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd": 0.0, "ev_usd": 0.0, "prot_exits": 0}

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
        prot_exits = len([t for t in closed if t.get('exit_reason') == 'protection_stop'])

        return {
            "trades": total_n,
            "net_pnl": net_pnl,
            "ret_pct": ret_pct,
            "cagr": cagr,
            "win_rate": win_rate,
            "pf": pf,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "ev_usd": ev_usd,
            "prot_exits": prot_exits
        }

    # Run 5 Tracks
    m_a = calc_metrics(*run_advanced_sim(df_eval, signals_cert, mode="NONE"))
    m_b = calc_metrics(*run_advanced_sim(df_eval, signals_cert, mode="BREAKEVEN_12R"))
    m_c = calc_metrics(*run_advanced_sim(df_eval, signals_cert, mode="STRUCTURE_SWING"))
    m_d = calc_metrics(*run_advanced_sim(df_eval, signals_cert, mode="DELAYED_ATR_2R"))
    m_e = calc_metrics(*run_advanced_sim(df_eval, signals_cert, mode="REGIME_DEPENDENT"))

    print("\n==================================================================================================================================================")
    print("  🏆 ADVANCED PROTECTION EXPERIMENT SCORECARD (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("==================================================================================================================================================")
    print(f"{'Performance Metric':<28} | {'Track A: Baseline (No Trail)':<27} | {'Track B: Breakeven +1.2R':<24} | {'Track C: Structure Swing':<24} | {'Track D: Delayed ATR +2R':<24} | {'Track E: Regime Dynamic':<24}")
    print("-" * 162)
    print(f"{'Total Executed OOS Trades':<28} | {m_a['trades']:<27} | {m_b['trades']:<24} | {m_c['trades']:<24} | {m_d['trades']:<24} | {m_e['trades']:<24}")
    print(f"{'Cumulative Net PnL ($)':<28} | ${m_a['net_pnl']:<+26.2f} | ${m_b['net_pnl']:<+23.2f} | ${m_c['net_pnl']:<+23.2f} | ${m_d['net_pnl']:<+23.2f} | ${m_e['net_pnl']:<+23.2f}")
    print(f"{'Cumulative Net Return (%)':<28} | {m_a['ret_pct']:<+26.2f}% | {m_b['ret_pct']:<+23.2f}% | {m_c['ret_pct']:<+23.2f}% | {m_d['ret_pct']:<+23.2f}% | {m_e['ret_pct']:<+23.2f}%")
    print(f"{'Compound Annual Rate (CAGR)':<28} | {m_a['cagr']:<+26.2f}% | {m_b['cagr']:<+23.2f}% | {m_c['cagr']:<+23.2f}% | {m_d['cagr']:<+23.2f}% | {m_e['cagr']:<+23.2f}%")
    print(f"{'Model Win Rate (%)':<28} | {m_a['win_rate']:<26.1f}% | {m_b['win_rate']:<23.1f}% | {m_c['win_rate']:<23.1f}% | {m_d['win_rate']:<23.1f}% | {m_e['win_rate']:<23.1f}%")
    print(f"{'Profit Factor (PF)':<28} | {m_a['pf']:<27.2f} | {m_b['pf']:<24.2f} | {m_c['pf']:<24.2f} | {m_d['pf']:<24.2f} | {m_e['pf']:<24.2f}")
    print(f"{'Annualized Sharpe Ratio':<28} | {m_a['sharpe']:<27.2f} | {m_b['sharpe']:<24.2f} | {m_c['sharpe']:<24.2f} | {m_d['sharpe']:<24.2f} | {m_e['sharpe']:<24.2f}")
    print(f"{'Maximum Drawdown (MDD %)':<28} | {m_a['max_dd']:<26.2f}% | {m_b['max_dd']:<23.2f}% | {m_c['max_dd']:<23.2f}% | {m_d['max_dd']:<23.2f}% | {m_e['max_dd']:<23.2f}%")
    print(f"{'Expected Value ($ / Trade)':<28} | ${m_a['ev_usd']:<+26.2f} | ${m_b['ev_usd']:<+23.2f} | ${m_c['ev_usd']:<+23.2f} | ${m_d['ev_usd']:<+23.2f} | ${m_e['ev_usd']:<+23.2f}")
    print(f"{'Protection / Trail Exits':<28} | {m_a['prot_exits']:<27} | {m_b['prot_exits']:<24} | {m_c['prot_exits']:<24} | {m_d['prot_exits']:<24} | {m_e['prot_exits']:<24}")
    print("==================================================================================================================================================")

if __name__ == "__main__":
    run_advanced_protection_gauntlet()
