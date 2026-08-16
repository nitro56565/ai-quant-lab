"""
=================================================================================
  MULTI-PAIR PORTFOLIO ABLATION TEST: MAX OPEN POSITIONS (1 to 20) ON BASELINE v2.0
=================================================================================
Evaluates Baseline v2.0 (Combo #271) across 6 Major Currency Pairs:
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF
over 8-Fold Out-of-Sample Walk-Forward Gauntlet (2018-2025 H1).

Compares individual asset performance and combined multi-pair portfolio execution
under varying portfolio max_open_positions limits (1 to 20).
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

TARGET_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]

def run_multipair_portfolio_simulation(asset_data_dict, max_open_pos=1, initial_cap=10000.0):
    # Align all timestamps across assets
    all_timestamps = sorted(list(set().union(*[d['df_eval'].index for d in asset_data_dict.values()])))
    
    active_positions = []
    pending_orders = []
    closed_trades = []
    current_equity = initial_cap
    daily_equity = {}

    friction_pips = 0.3
    comm_per_lot = 7.0
    risk_pct = 0.0075
    max_holding_bars = 36.0

    # Build per-asset lookup indexing
    asset_sim_states = {}
    for sym, data in asset_data_dict.items():
        df_eval = data['df_eval']
        p_l = data['p_l']
        p_s = data['p_s']
        hmm_arr = data['hmm_arr']
        pip_size = 0.01 if "JPY" in sym else 0.0001
        
        req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)
        hours = np.array([ts.hour for ts in df_eval.index])
        trading_window = ~((hours >= 13) & (hours <= 16))
        vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)

        sig_buy = (p_l >= req_p_arr) & vol_pass & trading_window
        sig_sell = (p_s >= req_p_arr) & trading_window

        sig_arr = np.full(len(df_eval), "NONE", dtype=object)
        for i in range(len(df_eval)):
            if sig_buy[i]: sig_arr[i] = "BUY"
            elif sig_sell[i]: sig_arr[i] = "SELL"

        asset_sim_states[sym] = {
            'timestamps': list(df_eval.index),
            'ts_map': {ts: idx for idx, ts in enumerate(df_eval.index)},
            'closes': df_eval['close'].values,
            'highs': df_eval['high'].values,
            'lows': df_eval['low'].values,
            'atrs': df_eval['feat_vol_atr'].values,
            'pip_size': pip_size,
            'signals': sig_arr
        }

    for ts in all_timestamps:
        # 1. Evaluate Active Positions
        remaining_positions = []
        for pos in active_positions:
            sym = pos['symbol']
            state = asset_sim_states[sym]
            if ts not in state['ts_map']:
                remaining_positions.append(pos)
                continue
            
            idx = state['ts_map'][ts]
            close = state['closes'][idx]; high = state['highs'][idx]; low = state['lows'][idx]
            pip_size = state['pip_size']; sig_now = state['signals'][idx]

            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            # Partial Exit (50% @ +1.5R)
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            # Exit Conditions
            if sig_now == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (ts - entry_time).total_seconds() / 3600.0 >= max_holding_bars: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = ts; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
                current_equity += rem_net
                closed_trades.append(pos)

                if sig_now == opposite_sig:
                    atr = state['atrs'][idx] if not np.isnan(state['atrs'][idx]) else (0.12 if "JPY" in sym else 0.0012)
                    pending_orders.append({
                        "symbol": sym, "direction": opposite_sig,
                        "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr),
                        "signal_time": ts, "atr": atr
                    })
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        # 2. Check Pending Limit Order Fills
        remaining_orders = []
        for p_order in pending_orders:
            sym = p_order['symbol']
            state = asset_sim_states[sym]
            if ts not in state['ts_map']:
                remaining_orders.append(p_order)
                continue

            idx = state['ts_map'][ts]
            high = state['highs'][idx]; low = state['lows'][idx]
            pip_size = state['pip_size']

            # Expire pending order if older than 3 hours
            if (ts - p_order['signal_time']).total_seconds() / 3600.0 > 3.0:
                continue

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
                    'symbol': sym, 'entry_time': ts, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0,
                    'status': 'open'
                }
                active_positions.append(new_pos)
            elif not filled:
                remaining_orders.append(p_order)

        pending_orders = remaining_orders

        # 3. Generate New Pending Orders
        for sym, state in asset_sim_states.items():
            if ts not in state['ts_map']: continue
            if len(active_positions) + len(pending_orders) >= max_open_pos: break

            idx = state['ts_map'][ts]
            sig = state['signals'][idx]
            if sig in ('BUY', 'SELL'):
                close = state['closes'][idx]
                atr = state['atrs'][idx] if not np.isnan(state['atrs'][idx]) else (0.12 if "JPY" in sym else 0.0012)
                pip_size = state['pip_size']

                retrace_pips = (atr / pip_size) * 0.25
                limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)

                # Check if asset already has active pos or pending order
                sym_active = any(p['symbol'] == sym for p in active_positions)
                sym_pending = any(p['symbol'] == sym for p in pending_orders)

                if not sym_active and not sym_pending:
                    pending_orders.append({
                        'symbol': sym, 'direction': sig, 'limit_price': limit_price,
                        'signal_time': ts, 'atr': atr
                    })

        daily_equity[str(ts.date())] = current_equity

    pnls = [t['pnl_usd'] for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()

    num_years = (all_timestamps[-1] - all_timestamps[0]).days / 365.25
    cagr_pct = (((max(0.01, current_equity) / initial_cap) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    downside_rets = daily_rets[daily_rets < 0]
    sortino_daily = (daily_rets.mean() / downside_rets.std() * np.sqrt(252)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0

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
        'mtm_max_dd': mtm_max_dd
    }

def process_symbol_gauntlet(sym):
    print(f"▶ Pre-computing 8-Fold OOS Model Predictions for {sym}...", flush=True)
    loader = DataLoader()
    req = DataRequest(symbol=sym, timeframe="1h", start="2014-01-01", end="2025-12-31")
    df_full = loader.load(req)

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

    return sym, {
        'df_eval': df_eval_oos,
        'p_l': p_stack_l_oos,
        'p_s': p_stack_s_oos,
        'hmm_arr': hmm_oos
    }

def main():
    print("=================================================================================", flush=True)
    print("  🌐 MULTI-PAIR PORTFOLIO MAX OPEN POSITIONS ABLATION — BASELINE v2.0", flush=True)
    print("=================================================================================\n", flush=True)

    asset_data_dict = {}
    for sym in TARGET_SYMBOLS:
        sym_name, data = process_symbol_gauntlet(sym)
        asset_data_dict[sym_name] = data

    print("\n=================================================================================", flush=True)
    print("  📊 SINGLE-PAIR BASELINE v2.0 SCORECARDS (max_open_positions = 1 per pair)", flush=True)
    print("=================================================================================\n", flush=True)

    single_pair_scorecard = []
    for sym, data in asset_data_dict.items():
        res = run_multipair_portfolio_simulation({sym: data}, max_open_pos=1)
        single_pair_scorecard.append({
            'Symbol': sym,
            'Trades': f"{res['trades']:,}",
            'Net Return': f"+{res['ret_pct']:.2f}%",
            'CAGR': f"+{res['cagr_pct']:.2f}%",
            'Sharpe': f"{res['sharpe']:.2f}",
            'Sortino': f"{res['sortino']:.2f}",
            'PF': f"{res['pf']:.2f}",
            'MDD': f"-{res['mtm_max_dd']:.2f}%"
        })

    def format_df_to_markdown(df):
        headers = list(df.columns)
        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for _, row in df.iterrows():
            lines.append("| " + " | ".join([str(val) for val in row.values]) + " |")
        return "\n".join(lines)

    df_single = pd.DataFrame(single_pair_scorecard)
    single_md = format_df_to_markdown(df_single)
    print(single_md)

    print("\n=================================================================================", flush=True)
    print("  🚀 MULTI-PAIR PORTFOLIO SWEEP ACROSS MAX OPEN POSITIONS = 1 to 20", flush=True)
    print("=================================================================================\n", flush=True)

    pos_limits = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]
    portfolio_results = []
    for max_pos in pos_limits:
        res = run_multipair_portfolio_simulation(asset_data_dict, max_open_pos=max_pos)
        portfolio_results.append(res)
        print(f"  Portfolio Max Open Pos = {max_pos:2d} | Trades: {res['trades']:5,d} | Net Return: +{res['ret_pct']:8.2f}% | CAGR: +{res['cagr_pct']:6.2f}% | Sharpe: {res['sharpe']:4.2f} | PF: {res['pf']:4.2f} | MDD: -{res['mtm_max_dd']:5.2f}%", flush=True)

    df_port = pd.DataFrame(portfolio_results)

    # Save to Markdown
    os.makedirs("docs", exist_ok=True)
    md_path = "documentation_and_ledgers/combo271_multipair_max_open_positions_sweep.md"
    with open(md_path, "w") as f:
        f.write("# 🌐 Multi-Pair Portfolio Max Open Positions Sweep (1 to 20) — Baseline v2.0\n\n")
        f.write("## 1. Single-Pair Out-of-Sample Scorecards (Baseline v2.0)\n\n")
        f.write(single_md)
        f.write("\n\n## 2. Multi-Pair Portfolio Scorecard Matrix across Max Open Positions\n\n")
        
        headers = ["Portfolio Max Open Pos", "Trades", "Net Return (%)", "CAGR (%/yr)", "Sharpe (Daily)", "Sortino", "Profit Factor", "Win Rate (%)", "Max DD (%)"]
        lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        for r in portfolio_results:
            row_vals = [
                str(r['max_pos']),
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
        f.write("\n".join(lines))
        f.write("\n\n")

    print(f"\n✅ Multi-Pair Portfolio Ablation Complete! Results saved to '{md_path}'.")

if __name__ == "__main__":
    main()
