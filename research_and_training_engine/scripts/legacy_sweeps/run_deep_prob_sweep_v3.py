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

def calculate_mdd_duration(eq_series):
    peaks = eq_series.cummax()
    drawdowns = (eq_series - peaks) / peaks * 100.0
    
    underwater = drawdowns < 0
    underwater_groups = (underwater != underwater.shift()).cumsum()
    
    mdd_durations = []
    for k, v in eq_series.groupby(underwater_groups):
        if drawdowns.loc[v.index].min() < 0:
            duration = (v.index[-1] - v.index[0]).days
            mdd_durations.append(duration)
    
    return max(mdd_durations) if mdd_durations else 0

def calculate_max_losing_streak(pnls):
    max_streak = 0
    current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0
    return max_streak

def run_simulation(df_eval, p_l, p_s, hmm_arr, trend_p, range_p, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values
    atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    
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
    daily_equity = {}

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
            stop_out = False; exit_price = 0.0

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_net = partial_pips * (partial_lots * 10.0) - (7.0 * partial_lots)
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size)
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size)
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_net = rem_pips * (rem_lots * 10.0) - (7.0 * rem_lots)
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)
                
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
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
            if (i - p_order['signal_idx']) > 3: continue
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

        daily_equity[str(timestamp.date())] = current_equity

    # Compute Metrics
    pnls = [t['pnl_usd'] for t in closed_trades]
    r_multiples = [t.get('r_multiple', 0.0) for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    total_trades = len(closed_trades)
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    eq_series.index = pd.to_datetime(eq_series.index)
    daily_rets = eq_series.pct_change().dropna()

    num_years = (timestamps[-1] - timestamps[0]).days / 365.25
    cagr_pct = (((current_equity / initial_cap) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    downside_rets = daily_rets[daily_rets < 0]
    sortino = (daily_rets.mean() / downside_rets.std() * np.sqrt(252)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss
    win_rate = (len(wins) / total_trades * 100.0) if total_trades else 0.0
    avg_r = np.mean(r_multiples) if r_multiples else 0.0

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min()) if len(dds) > 0 else 0.0
    
    max_streak = calculate_max_losing_streak(pnls)
    mdd_dur = calculate_mdd_duration(eq_series)
    
    monthly_rets = eq_series.resample('ME').last().pct_change().dropna() * 100.0
    yearly_rets = eq_series.resample('YE').last().pct_change().dropna() * 100.0
    
    worst_month = monthly_rets.min() if len(monthly_rets) > 0 else 0.0
    worst_year = yearly_rets.min() if len(yearly_rets) > 0 else 0.0
    profitable_years = len(yearly_rets[yearly_rets > 0])

    return {
        'trend_p': trend_p, 'range_p': range_p,
        'trades': total_trades,
        'net_ret': ret_pct,
        'cagr': cagr_pct,
        'sharpe': sharpe,
        'sortino': sortino,
        'pf': pf,
        'win_rate': win_rate,
        'avg_r': avg_r,
        'mdd': mtm_max_dd,
        'max_streak': max_streak,
        'mdd_dur': mdd_dur,
        'worst_month': worst_month,
        'worst_year': worst_year,
        'prof_years': f"{profitable_years}/{len(yearly_rets)}"
    }

def main():
    print("Loading Data and Model for Deep Probability Threshold Robustness Test...")
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
    
    # 2018 - 2025 OOS Mask
    oos_mask = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    
    # 2026 Holdout Mask
    holdout_mask = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")

    oos_results = []
    
    print("Running 2018-2025 OOS Grid Search for all 25 combinations...")
    for t_p in trend_thresholds:
        for r_p in range_thresholds:
            res = run_simulation(df_feat[oos_mask], p_l[oos_mask], p_s[oos_mask], hmm_states[oos_mask], t_p, r_p)
            oos_results.append(res)
            
    # Compute rank logic:
    # Maximize CAGR, Minimize MDD, Maximize Sharpe/PF.
    # Score = (CAGR * 0.4) + ((100 - MDD) * 0.3) + (Sharpe * 15 * 0.15) + (PF * 10 * 0.15)
    # Actually, simpler: Just sort by MDD, then pick highest CAGR among top 5 lowest MDD.
    oos_results.sort(key=lambda x: x['mdd']) # Sort by lowest MDD
    top_5 = oos_results[:5]
    top_5.sort(key=lambda x: x['cagr'], reverse=True) # Sort top 5 by highest CAGR
    challenger = top_5[0]

    baseline = None
    for r in oos_results:
        if r['trend_p'] == 0.36 and r['range_p'] == 0.42:
            baseline = r
            break
            
    print("\n\n### 2018-2025 OOS Deep Probability Sweep Results (All 25 Combinations)")
    
    headers = ["Trend", "Range", "Trades", "NetRet%", "CAGR%", "MDD%", "Sharpe", "Sortino", "PF", "Win%", "AvgR", "MaxLoss", "MDD(d)", "WorstYr%", "ProfYrs"]
    print("-" * 140)
    print("".join(f"{h:<9}" for h in headers))
    print("-" * 140)
    
    # Print all sorted by Trend then Range
    oos_sorted = sorted(oos_results, key=lambda x: (x['trend_p'], x['range_p']))
    for r in oos_sorted:
        row = [
            f"{r['trend_p']:.2f}", f"{r['range_p']:.2f}", f"{r['trades']}", 
            f"{r['net_ret']:.1f}", f"{r['cagr']:.1f}", f"{r['mdd']:.1f}", 
            f"{r['sharpe']:.2f}", f"{r['sortino']:.2f}", f"{r['pf']:.2f}", 
            f"{r['win_rate']:.1f}", f"{r['avg_r']:.3f}", f"{r['max_streak']}", 
            f"{r['mdd_dur']}", f"{r['worst_year']:.1f}", f"{r['prof_years']}"
        ]
        print("".join(f"{str(v):<9}" for v in row))
        
    print("\n\n==========================================================================================")
    print(f"🏆 CHALLENGER SELECTED (Pareto-Optimal OOS): Trend={challenger['trend_p']}, Range={challenger['range_p']}")
    print(f"🔒 FROZEN BASELINE (Current Prod): Trend=0.36, Range=0.42")
    print("==========================================================================================")
    print("\nRunning untouched 2026 Holdout comparison...")
    
    base_26 = run_simulation(df_feat[holdout_mask], p_l[holdout_mask], p_s[holdout_mask], hmm_states[holdout_mask], 0.36, 0.42)
    chal_26 = run_simulation(df_feat[holdout_mask], p_l[holdout_mask], p_s[holdout_mask], hmm_states[holdout_mask], challenger['trend_p'], challenger['range_p'])
    
    print("\n### 2026 Live Holdout Confrontation (Jan 1, 2026 - Aug 11, 2026)")
    print("-" * 115)
    print(f"{'Configuration':<25} | {'Trades':<8} | {'Net Return':<12} | {'MDD':<8} | {'Sharpe':<8} | {'PF':<8} | {'Win Rate':<8}")
    print("-" * 115)
    
    r1 = base_26
    print(f"{'Frozen Baseline (0.36/0.42)':<25} | {r1['trades']:<8} | +{r1['net_ret']:.2f}%{' ':>3} | -{r1['mdd']:.2f}%{' ':>1} | {r1['sharpe']:.2f}{' ':>4} | {r1['pf']:.2f}{' ':>4} | {r1['win_rate']:.1f}%")
    
    r2 = chal_26
    c_name = f"Challenger ({challenger['trend_p']:.2f}/{challenger['range_p']:.2f})"
    print(f"{c_name:<25} | {r2['trades']:<8} | +{r2['net_ret']:.2f}%{' ':>3} | -{r2['mdd']:.2f}%{' ':>1} | {r2['sharpe']:.2f}{' ':>4} | {r2['pf']:.2f}{' ':>4} | {r2['win_rate']:.1f}%")
    print("-" * 115)

if __name__ == "__main__":
    main()
