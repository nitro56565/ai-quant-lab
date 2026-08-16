import os
import sys
import json
import warnings
import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder

def run_simulation(df_eval, p_l, p_s, hmm_arr, trend_p, range_p, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values
    highs = df_eval['high'].values
    lows = df_eval['low'].values
    atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    
    # HMM state: 1 is Range, 0 is Trend
    req_p_arr = np.where(hmm_arr == 1, range_p, trend_p)

    signals_buy = (p_l >= req_p_arr) & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    friction_pips = 0.3
    risk_pct = 0.0075
    max_open_pos = 1

    active_positions = []
    pending_orders = []
    closed_trades = []
    current_equity = initial_cap

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]
        atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        # 1. Active Position Evaluation
        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            # Partial Exit (50% @ +1.5R) with 0.3 pips friction & $7/lot commission
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_net = partial_pips * (partial_lots * 10.0) - (7.0 * partial_lots)
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            # Exit Conditions
            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size)
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size)
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips # 0.3 pips friction on every exit
                rem_lots = pos['active_lots']
                rem_net = rem_pips * (rem_lots * 10.0) - (7.0 * rem_lots)
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['pnl_usd'] = total_trade_net
                current_equity += rem_net
                closed_trades.append(pos)
                
                if signals_arr[i] == opposite_sig:
                    pending_orders.append({"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr})
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        # 2. Pending Limit Order Fill Check
        remaining_orders = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3:
                continue # Expired
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']
            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)

            if filled and len(active_positions) < max_open_pos:
                sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5; initial_sl_dist = sl_pips * pip_size
                entry_price = p_limit
                sl_price = entry_price - initial_sl_dist if p_dir == 'BUY' else entry_price + initial_sl_dist
                tp_price = entry_price + (tp_pips * pip_size) if p_dir == 'BUY' else entry_price - (tp_pips * pip_size)

                lots = round(max(0.01, min(10.0, (current_equity * risk_pct) / (sl_pips * 10.0))), 2)

                active_positions.append({
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0
                })
            elif not filled:
                remaining_orders.append(p_order)
        pending_orders = remaining_orders

        # 3. New Pending Order Creation
        if len(active_positions) + len(pending_orders) < max_open_pos and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]
            retrace_pips = (atr / pip_size) * 0.25
            limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

    pnls = [t['pnl_usd'] for t in closed_trades]
    wins = len([p for p in pnls if p > 0])
    total_trades = len(closed_trades)
    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    net_pnl = sum(pnls)
    ret_pct = (net_pnl / initial_cap) * 100.0

    return total_trades, ret_pct, win_rate

def main():
    print("Loading Data and Model for Baseline v3.0 Probability Threshold Sweep...")
    loader = DataLoader()
    req = DataRequest(symbol="EURUSD", timeframe="1h", start="2018-01-01", end="2026-08-11")
    df = loader.load(req)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    model_file = "trained_model_artifacts/production_deployment/model_suite.joblib"
    suite = joblib.load(model_file)
    hmm = suite["hmm_detector"]
    models_long = suite["models_long"]
    models_short = suite["models_short"]
    feat_cols = suite["feat_cols"]

    # Pre-fill feature columns missing due to label generator skipping
    for c in feat_cols:
        if c not in df_feat.columns:
            df_feat[c] = 0.0

    df_feat = df_feat.dropna(subset=feat_cols)
    X_mat = df_feat[feat_cols].values

    hmm_states = hmm.predict(df_feat)
    
    vol_v = df_feat['feat_vol_atr_pct'].values
    v_st = np.zeros(len(vol_v), dtype=int)
    v_st[vol_v >= 50.0] = 1
    
    state_arr = (hmm_states * 2) + v_st

    pl_lgb = np.zeros(len(df_feat)); pl_cat = np.zeros(len(df_feat)); pl_xgb = np.zeros(len(df_feat))
    ps_lgb = np.zeros(len(df_feat)); ps_cat = np.zeros(len(df_feat)); ps_xgb = np.zeros(len(df_feat))

    for s in range(4):
        mask = (state_arr == s)
        if not np.any(mask): continue
        if s in models_long and s in models_short:
            try:
                pl_lgb[mask] = models_long[s]['lgb'].predict_proba(X_mat[mask])[:, 1]
                pl_cat[mask] = models_long[s]['cat'].predict_proba(X_mat[mask])[:, 1]
                pl_xgb[mask] = models_long[s]['xgb'].predict_proba(X_mat[mask])[:, 1]

                ps_lgb[mask] = models_short[s]['lgb'].predict_proba(X_mat[mask])[:, 1]
                ps_cat[mask] = models_short[s]['cat'].predict_proba(X_mat[mask])[:, 1]
                ps_xgb[mask] = models_short[s]['xgb'].predict_proba(X_mat[mask])[:, 1]
            except Exception:
                pl_lgb[mask] = 0.3; pl_cat[mask] = 0.3; pl_xgb[mask] = 0.3
                ps_lgb[mask] = 0.3; ps_cat[mask] = 0.3; ps_xgb[mask] = 0.3

    p_l = (pl_cat * 0.5) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_s = (ps_cat * 0.5) + (ps_lgb * 0.25) + (ps_xgb * 0.25)

    trend_thresholds = [0.32, 0.34, 0.36, 0.38, 0.40]
    range_thresholds = [0.38, 0.40, 0.42, 0.44, 0.46]

    results = []
    
    print("Running simulations grid...")
    for t_p in trend_thresholds:
        for r_p in range_thresholds:
            trades, ret, win_rate = run_simulation(df_feat, p_l, p_s, hmm_states, t_p, r_p)
            results.append({
                "Trend Hurdle": t_p,
                "Range Hurdle": r_p,
                "Total Trades": trades,
                "Net Return (%)": f"+{ret:.2f}%" if ret > 0 else f"{ret:.2f}%",
                "Win Rate (%)": f"{win_rate:.1f}%"
            })
            
    print("\n\n### Baseline v3.0 Probability Hurdle Experimental Sweep\n")
    print(f"{'Trend Hurdle':<15} | {'Range Hurdle':<15} | {'Total Trades':<15} | {'Net Return (%)':<15} | {'Win Rate (%)':<15}")
    print("-" * 85)
    for r in results:
        print(f"{r['Trend Hurdle']:<15} | {r['Range Hurdle']:<15} | {r['Total Trades']:<15} | {r['Net Return (%)']:<15} | {r['Win Rate (%)']:<15}")

if __name__ == "__main__":
    main()
