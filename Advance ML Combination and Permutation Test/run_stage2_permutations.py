"""
Stage 2 Permutation & Negative Control Testing.
Destroys informational structure of Stage 2 Additive components (HMM regimes, Volatility ranks, Signals, Timestamps)
across the 8-Fold Walk-Forward OOS Gauntlet (2018-2025 EURUSD H1) to prove that the architecture edge is genuine.
"""

import os, sys, time
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

sys.path.insert(0, os.path.abspath("."))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector

def run_stage2_permutations_laboratory():
    print("=================================================================================")
    print("  🧪 STAGE 2 PERMUTATION & NEGATIVE CONTROL LABORATORY")
    print("=================================================================================")
    print("  • Period: 2018-2025 EURUSD H1 (8-Fold Expanding Walk-Forward OOS Gauntlet)")
    print("  • Objective: Destroy information content of Stage 2 components to prove edge is genuine\n")

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

    # Permutation Configurations
    perm_configs = {
        "Control Benchmark (Real Unshuffled System)": {
            "shuffle_hmm": False, "shuffle_vol": False, "random_signals": False, "shift_features": 0
        },
        "Permutation 2.A: Shuffled HMM Regime Labels": {
            "shuffle_hmm": True, "shuffle_vol": False, "random_signals": False, "shift_features": 0
        },
        "Permutation 2.B: Shuffled Volatility Quantile Ranks": {
            "shuffle_hmm": False, "shuffle_vol": True, "random_signals": False, "shift_features": 0
        },
        "Permutation 2.C: Fully Shuffled 9-State Regime Matrix": {
            "shuffle_hmm": True, "shuffle_vol": True, "random_signals": False, "shift_features": 0
        },
        "Permutation 2.D: 50/50 Random Directional Signals": {
            "shuffle_hmm": False, "shuffle_vol": False, "random_signals": True, "shift_features": 0
        },
        "Permutation 2.E: Time-Shifted Features (+24 Bar Offset)": {
            "shuffle_hmm": False, "shuffle_vol": False, "random_signals": False, "shift_features": 24
        }
    }

    def generate_permuted_predictions(cfg):
        np.random.seed(42)
        prob_l = np.zeros(total_h1_bars)
        prob_s = np.zeros(total_h1_bars)
        hmm_oos = np.zeros(total_h1_bars)

        df_lbl_work = df_lbl.copy()
        if cfg["shift_features"] > 0:
            df_lbl_work[all_feat_cols] = df_lbl_work[all_feat_cols].shift(cfg["shift_features"]).bfill()

        for yr in years_oos:
            train_end_year = yr - 1
            train_m = (df_lbl_work.index >= "2014-01-01") & (df_lbl_work.index <= f"{train_end_year}-12-31")
            test_m = (df_lbl_work.index >= f"{yr}-01-01") & (df_lbl_work.index <= f"{yr}-12-31")

            df_tr = df_lbl_work[train_m].dropna(subset=['label_dir_long']).copy()
            df_te = df_lbl_work[test_m].copy()

            hmm_detector = HMMRegimeDetector()
            hmm_detector.fit(df_tr)
            hmm_tr = hmm_detector.predict(df_tr)
            hmm_te = hmm_detector.predict(df_te)

            if cfg["shuffle_hmm"]:
                np.random.shuffle(hmm_tr)
                np.random.shuffle(hmm_te)

            tr_v = df_tr['feat_vol_atr_pct'].values.copy()
            te_v = df_te['feat_vol_atr_pct'].values.copy()

            if cfg["shuffle_vol"]:
                np.random.shuffle(tr_v)
                np.random.shuffle(te_v)

            v_tr = np.zeros(len(tr_v), dtype=int)
            v_tr[tr_v >= 33.33] = 1
            v_tr[tr_v >= 66.67] = 2

            v_te = np.zeros(len(te_v), dtype=int)
            v_te[te_v >= 33.33] = 1
            v_te[te_v >= 66.67] = 2

            state_tr = (hmm_tr * 3) + v_tr
            state_te = (hmm_te * 3) + v_te

            m_long = {}
            m_short = {}
            X_tr_mat = df_tr[all_feat_cols].values
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

            X_te_mat = df_te[all_feat_cols].values
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

            if cfg["random_signals"]:
                pl_te = np.random.uniform(0.20, 0.50, len(df_te))
                ps_te = np.random.uniform(0.20, 0.50, len(df_te))

            fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
            prob_l[fold_eval_indices] = pl_te
            prob_s[fold_eval_indices] = ps_te
            hmm_oos[fold_eval_indices] = hmm_te

        return prob_l, prob_s, hmm_oos

    def run_sim(prob_l, prob_s, hmm_arr):
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

    perm_results = {}
    control_m = None

    print("=========================================================================================================================================")
    print("  🏆 STAGE 2 PERMUTATION & NEGATIVE CONTROL SCORECARD (2018-2025 EURUSD H1 OOS GAUNTLET)")
    print("=========================================================================================================================================")
    print(f"{'Permutation / Negative Control Case':<48} | {'Trades':<7} | {'Net Return (%)':<14} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6} | {'Permutation Destruction Impact':<24}")
    print("-" * 125)

    for name, cfg in perm_configs.items():
        pl, ps, hmm = generate_permuted_predictions(cfg)
        trades, final_eq = run_sim(pl, ps, hmm)
        m = calc_metrics(trades, final_eq)
        perm_results[name] = m

        if name.startswith("Control"):
            control_m = m
            destruct_str = "UNSHUFFLED BENCHMARK"
        else:
            r_diff = m['ret_pct'] - control_m['ret_pct']
            s_diff = m['sharpe'] - control_m['sharpe']
            destruct_str = f"{r_diff:+.2f}% Return (Sharpe {s_diff:+.2f})"

        print(f"{name:<48} | {m['trades']:<7} | {m['ret_pct']:<+13.2f}% | {m['sharpe']:<8.2f} | {m['max_dd']:<7.2f}% | {m['pf']:<6.2f} | {destruct_str:<24}")

    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_stage2_permutations_laboratory()
