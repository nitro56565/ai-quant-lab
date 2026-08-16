import os
import sys
import warnings
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector

def run_mtf_simulation_multi_style(df_eval, df_1m, p_l, p_s, hmm_arr, initial_cap=10000.0, max_open_pos=3, exec_atr_mult=0.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes_1h = df_eval['close'].values; atrs_1h = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.38)
    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & vol_pass & trading_window

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    pip_size = 0.0001; friction_pips = 0.3; comm_per_lot = 7.0; risk_pct = 0.0075
    max_holding_hours = 36.0

    ts_1m = df_1m.index.values
    highs_1m = df_1m['high'].values
    lows_1m = df_1m['low'].values
    closes_1m = df_1m['close'].values

    active_positions = []; pending_orders = []; closed_trades = []; current_equity = initial_cap; daily_equity = {}
    total_signals_fired = 0

    for i in range(total_bars):
        t_start = timestamps[i]
        t_end = t_start + pd.Timedelta(minutes=59)
        
        dt_start = np.datetime64(t_start)
        dt_end = np.datetime64(t_end)
        idx_start = np.searchsorted(ts_1m, dt_start)
        idx_end = np.searchsorted(ts_1m, dt_end, side='right')
        
        for k in range(idx_start, idx_end):
            timestamp_1m = pd.Timestamp(ts_1m[k])
            high_1m = highs_1m[k]
            low_1m = lows_1m[k]
            close_1m = closes_1m[k]

            remaining_positions = []
            for pos in active_positions:
                direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
                sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
                stop_out = False; exit_price = 0.0; exit_reason = None

                opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
                floating_pnl_pips = (high_1m - entry_price) / pip_size if direction == 'BUY' else (entry_price - low_1m) / pip_size
                r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                if not pos['partial_taken'] and r_floating >= 1.5:
                    partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                    partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                    partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                    pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

                if (timestamp_1m - entry_time).total_seconds() / 3600.0 >= max_holding_hours: stop_out = True; exit_price = close_1m; exit_reason = 'time_limit'
                elif direction == 'BUY' and low_1m <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
                elif direction == 'SELL' and high_1m >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
                elif direction == 'BUY' and high_1m >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
                elif direction == 'SELL' and low_1m <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

                if stop_out:
                    rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                    rem_pips -= friction_pips
                    rem_lots = pos['active_lots']
                    rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                    total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                    pos['exit_time'] = timestamp_1m; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                    pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                    current_equity += rem_net
                    closed_trades.append(pos)
                else:
                    remaining_positions.append(pos)
            active_positions = remaining_positions

            remaining_orders = []
            for p_order in pending_orders:
                hours_passed = (timestamp_1m - timestamps[p_order['signal_idx']]).total_seconds() / 3600.0
                if hours_passed > 3.0: continue
                p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']

                filled = (p_dir == 'BUY' and low_1m <= p_limit) or (p_dir == 'SELL' and high_1m >= p_limit)
                if filled and len(active_positions) < max_open_pos:
                    sl_pips = (p_atr / pip_size) * 1.5; tp_pips = (p_atr / pip_size) * 3.0; initial_sl_dist = (p_atr / pip_size) * 1.5 * pip_size
                    entry_price = p_limit
                    sl_price = entry_price - (p_atr * 1.5) if p_dir == 'BUY' else entry_price + (p_atr * 1.5)
                    tp_price = entry_price + (p_atr * 3.0) if p_dir == 'BUY' else entry_price - (p_atr * 3.0)
                    risk_amt = current_equity * risk_pct
                    lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                    new_pos = {
                        'trade_id': len(closed_trades) + len(active_positions) + 1, 'entry_time': timestamp_1m, 'direction': p_dir, 'entry_price': entry_price,
                        'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'
                    }
                    active_positions.append(new_pos)
                elif not filled:
                    remaining_orders.append(p_order)
            pending_orders = remaining_orders

        # Signal Reversals processed exactly at the hour close
        remaining_positions = []
        for pos in active_positions:
            opposite_sig = 'SELL' if pos['direction'] == 'BUY' else 'BUY'
            if signals_arr[i] == opposite_sig:
                exit_price = closes_1h[i]
                rem_pips = (exit_price - pos['entry_price']) / pip_size if pos['direction'] == 'BUY' else (pos['entry_price'] - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = timestamps[i]; pos['exit_price'] = exit_price; pos['exit_reason'] = 'signal_reversal'
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                current_equity += rem_net
                closed_trades.append(pos)
                
                total_signals_fired += 1
                atr = atrs_1h[i] if not np.isnan(atrs_1h[i]) else 0.0012
                if exec_atr_mult == 0.0:
                    entry_price = closes_1h[i]
                    sl_pips = (atr / pip_size) * 1.5; tp_pips = (atr / pip_size) * 3.0; initial_sl_dist = (atr / pip_size) * 1.5 * pip_size
                    sl_price = entry_price - (atr * 1.5) if opposite_sig == 'BUY' else entry_price + (atr * 1.5)
                    tp_price = entry_price + (atr * 3.0) if opposite_sig == 'BUY' else entry_price - (atr * 3.0)
                    risk_amt = current_equity * risk_pct
                    lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)
                    new_pos = {
                        'trade_id': len(closed_trades) + len(active_positions) + 1, 'entry_time': timestamps[i], 'direction': opposite_sig, 'entry_price': entry_price,
                        'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'
                    }
                    remaining_positions.append(new_pos)
                else:
                    retrace_pips = (atr / pip_size) * exec_atr_mult
                    limit_price = closes_1h[i] - (retrace_pips * pip_size) if opposite_sig == 'BUY' else closes_1h[i] + (retrace_pips * pip_size)
                    pending_orders.append({"direction": opposite_sig, "limit_price": limit_price, "signal_idx": i, "atr": atr})
            else:
                remaining_positions.append(pos)
        active_positions = remaining_positions

        if len(active_positions) + len(pending_orders) < max_open_pos and signals_arr[i] in ('BUY', 'SELL'):
            total_signals_fired += 1
            sig = signals_arr[i]
            atr = atrs_1h[i] if not np.isnan(atrs_1h[i]) else 0.0012
            
            if exec_atr_mult == 0.0:
                entry_price = closes_1h[i]
                sl_pips = (atr / pip_size) * 1.5; tp_pips = (atr / pip_size) * 3.0; initial_sl_dist = (atr / pip_size) * 1.5 * pip_size
                sl_price = entry_price - (atr * 1.5) if sig == 'BUY' else entry_price + (atr * 1.5)
                tp_price = entry_price + (atr * 3.0) if sig == 'BUY' else entry_price - (atr * 3.0)
                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)
                new_pos = {
                    'trade_id': len(closed_trades) + len(active_positions) + 1, 'entry_time': timestamps[i], 'direction': sig, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist, 'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'
                }
                active_positions.append(new_pos)
            else:
                retrace_pips = (atr / pip_size) * exec_atr_mult
                limit_price = closes_1h[i] - (retrace_pips * pip_size) if sig == 'BUY' else closes_1h[i] + (retrace_pips * pip_size)
                pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

        daily_equity[str(timestamps[i].date())] = current_equity

    pnls = [t['pnl_usd'] for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    eq_series.index = pd.to_datetime(eq_series.index)
    daily_rets = eq_series.pct_change().dropna()
    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    
    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss
    missed_trade_rate = 100.0 * (1.0 - (len(closed_trades) / max(1, total_signals_fired)))

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min())

    return {
        'total_signals': total_signals_fired,
        'trades': len(closed_trades),
        'missed_trade_rate': missed_trade_rate,
        'ret_pct': ret_pct,
        'sharpe': sharpe_daily,
        'pf': pf,
        'mtm_max_dd': mtm_max_dd
    }

def main():
    print("=================================================================================", flush=True)
    print("  🔬 RESEARCH: 2026 UNTOUCHED HOLDOUT EXECUTION VERIFICATION", flush=True)
    print("=================================================================================\n", flush=True)

    loader = DataLoader()
    symbol = "EURUSD"
    req_1h = DataRequest(symbol=symbol, timeframe="1h", start="2014-01-01", end="2026-08-11")
    df_1h = loader.load(req_1h)
    req_1m = DataRequest(symbol=symbol, timeframe="1min", start="2026-01-01", end="2026-08-11")
    df_1m = loader.load(req_1m)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_1h.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)
    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    print("▶ Executing 100% Untouched 2026 Live Holdout Fold...", flush=True)
    mask_2026 = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_eval_26 = df_feat[mask_2026].copy()

    train_m_26 = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    df_tr_26 = df_lbl[train_m_26].dropna(subset=['label_dir_long']).copy()

    fold_seed = 42
    hmm_detector = HMMRegimeDetector(n_components=2, random_state=fold_seed)
    hmm_detector.fit(df_tr_26)
    hmm_tr_26 = hmm_detector.predict(df_tr_26)
    hmm_te_26 = hmm_detector.predict(df_eval_26)

    tr_v_26 = df_tr_26['feat_vol_atr_pct'].values; te_v_26 = df_eval_26['feat_vol_atr_pct'].values
    v_tr_26 = np.zeros(len(tr_v_26), dtype=int); v_tr_26[tr_v_26 >= 50.0] = 1
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 50.0] = 1

    state_tr_26 = (hmm_tr_26 * 2) + v_tr_26; state_te_26 = (hmm_te_26 * 2) + v_te_26
    X_tr_mat_26 = df_tr_26[all_feat_cols].values; X_te_mat_26 = df_eval_26[all_feat_cols].values
    y_l_tr_26 = df_tr_26['label_dir_long'].values; y_s_tr_26 = df_tr_26['label_dir_short'].values

    pl_lgb = np.zeros(len(df_eval_26)); pl_cat = np.zeros(len(df_eval_26)); pl_xgb = np.zeros(len(df_eval_26))
    ps_lgb = np.zeros(len(df_eval_26)); ps_cat = np.zeros(len(df_eval_26)); ps_xgb = np.zeros(len(df_eval_26))

    for s in range(4):
        mask_tr = (state_tr_26 == s); mask_te = (state_te_26 == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])

            pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]

            ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]

    p_stack_l_26 = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s_26 = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)

    print("\n▶ Running 2026 1M Holdout Simulations...")
    
    styles = [0.0, 0.10, 0.20]
    results = {}
    
    for style in styles:
        label = "MARKET" if style == 0.0 else f"{style:.2f} ATR"
        print(f"  -> Testing: {label}")
        results[label] = run_mtf_simulation_multi_style(df_eval_26, df_1m, p_stack_l_26, p_stack_s_26, hmm_te_26, max_open_pos=3, exec_atr_mult=style)

    print("\n========================================================")
    print("    EXECUTION HOLDOUT COMPARISON (2026 UNTOUCHED 1M)")
    print("========================================================")
    for style in styles:
        label = "MARKET" if style == 0.0 else f"{style:.2f} ATR"
        res = results[label]
        print(f"[{label}]")
        print(f"Signals Fired: {res['total_signals']} | Fills: {res['trades']} | Missed Rate: {res['missed_trade_rate']:.1f}%")
        print(f"Return: +{res['ret_pct']:.2f}% | MDD: -{res['mtm_max_dd']:.2f}% | Sharpe: {res['sharpe']:.2f} | PF: {res['pf']:.2f}")
        print("-" * 56)

if __name__ == "__main__":
    main()
