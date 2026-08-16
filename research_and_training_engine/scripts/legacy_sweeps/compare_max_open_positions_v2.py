"""
=================================================================================
  ABLATION TEST: MAX OPEN POSITIONS (1 to 10) ON FROZEN BASELINE v2.0 (COMBO #271)
=================================================================================
Evaluates performance metrics across max_open_positions = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
on 8-Fold Out-of-Sample Walk-Forward Gauntlet (2018-2025 EURUSD H1).
=================================================================================
"""

import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from production_deployment.canonical_backtest.run_canonical_production_backtest import process_fold_combo271

def run_simulation_v2(df_eval, p_l, p_s, hmm_arr, max_open_pos=1, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    
    # PAE Hurdles: 0.42 Range / 0.36 Trend
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    friction_pips = 0.3
    comm_per_lot = 7.0
    risk_pct = 0.0075
    max_holding_bars = 36.0 # Extended 36h Holding

    active_positions = []; pending_orders = []; closed_trades = []; current_equity = initial_cap; daily_equity = {}

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        # 1. Active Position Evaluation
        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            # Partial Exit (50% @ +1.5R) with friction & commission
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            # Exit Conditions (36h max holding)
            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= max_holding_bars: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips # 0.3 pips friction on every exit
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = timestamp; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
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
                sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 3.0; initial_sl_dist = (p_atr / pip_size) * 1.5 * pip_size
                entry_price = p_limit
                sl_price = entry_price - (p_atr * 1.5) if p_dir == 'BUY' else entry_price + (p_atr * 1.5)
                tp_price = entry_price + (p_atr * 3.0) if p_dir == 'BUY' else entry_price - (p_atr * 3.0)

                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                new_pos = {
                    'trade_id': len(closed_trades) + len(active_positions) + 1,
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0,
                    'status': 'open'
                }
                active_positions.append(new_pos)
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

    pnls = [t['pnl_usd'] for t in closed_trades]
    r_multiples = [t.get('r_multiple', 0.0) for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()

    num_years = (timestamps[-1] - timestamps[0]).days / 365.25
    cagr_pct = (((max(0.01, current_equity) / initial_cap) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    downside_rets = daily_rets[daily_rets < 0]
    sortino_daily = (daily_rets.mean() / downside_rets.std() * np.sqrt(252)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
    avg_r = np.mean(r_multiples) if r_multiples else 0.0

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min())

    return {
        'max_pos': max_open_pos,
        'trades': len(closed_trades),
        'end_eq': current_equity,
        'net_pnl': net_pnl,
        'ret_pct': ret_pct,
        'cagr_pct': cagr_pct,
        'sharpe': sharpe_daily,
        'sortino': sortino_daily,
        'pf': pf,
        'win_rate': win_rate,
        'mtm_max_dd': mtm_max_dd,
        'avg_r': avg_r
    }

def main():
    print("=================================================================================", flush=True)
    print("  🧪 TESTING MAX OPEN POSITIONS = 1 to 10 ON FROZEN BASELINE v2.0 (COMBO #271)", flush=True)
    print("=================================================================================\n", flush=True)

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
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    years_oos = list(range(2018, 2026))

    safe_cores = max(1, (os.cpu_count() or 4) - 1)
    print("▶ Pre-computing 8-Fold OOS Model Predictions for Combo #271 (2018-2025)...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold_combo271)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l_oos = np.zeros(len(df_eval_oos))
    p_stack_s_oos = np.zeros(len(df_eval_oos))
    hmm_oos = np.zeros(len(df_eval_oos))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[fold_eval_indices] = pl_fold
        p_stack_s_oos[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    print("\n▶ Running Simulation Sweep across max_open_positions = 1 to 10...\n", flush=True)
    results = []
    for max_pos in range(1, 11):
        res = run_simulation_v2(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos, max_open_pos=max_pos)
        results.append(res)
        print(f"  Max Open Positions = {max_pos:2d} | Trades: {res['trades']:,} | Net Return: +{res['ret_pct']:7.2f}% | CAGR: +{res['cagr_pct']:5.2f}% | Sharpe: {res['sharpe']:4.2f} | PF: {res['pf']:4.2f} | MDD: -{res['mtm_max_dd']:5.2f}%", flush=True)

    df_res = pd.DataFrame(results)
    
    # Save Report
    os.makedirs("docs", exist_ok=True)
    csv_path = "documentation_and_ledgers/combo271_max_open_positions_sweep.csv"
    df_res.to_csv(csv_path, index=False)

    print("\n=================================================================================", flush=True)
    print("    🏆 MAX OPEN POSITIONS ABLATION SCORECARD MATRIX — BASELINE v2.0", flush=True)
    print("=================================================================================\n", flush=True)

    table_headers = ["Max Open Pos", "Trades", "Net Return (%)", "CAGR (%/yr)", "Sharpe (Daily)", "Sortino", "Profit Factor", "Win Rate (%)", "Max DD (%)"]
    lines = ["| " + " | ".join(table_headers) + " |", "| " + " | ".join(["---"] * len(table_headers)) + " |"]
    for r in results:
        row_vals = [
            f"**{r['max_pos']}**" if r['max_pos'] == 1 else str(r['max_pos']),
            f"{r['trades']:,}",
            f"+{r['ret_pct']:.2f}%",
            f"+{r['cagr_pct']:.2f}%",
            f"{r['sharpe']:.2f}",
            f"{r['sortino']:.2f}",
            f"{r['pf']:.2f}",
            f"{r['win_rate']:.2f}%",
            f"-{r['mtm_max_dd']:.2f}%"
        ]
        lines.append("| " + " | ".join(row_vals) + " |")

    table_md = "\n".join(lines)
    print(table_md)

    with open("documentation_and_ledgers/combo271_max_open_positions_sweep.md", "w") as f:
        f.write("# 🧪 Max Open Positions Sweep (1 to 10) — Baseline v2.0 (Combo #271)\n\n")
        f.write(table_md)
        f.write("\n\n")

    print(f"\n✅ Ablation Test Complete! Results saved to 'documentation_and_ledgers/combo271_max_open_positions_sweep.md'.")

if __name__ == "__main__":
    main()
