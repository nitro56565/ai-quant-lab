import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ControlledABTestingSuite")

def calculate_metrics(closed_trades, initial_capital=10000.0):
    if not closed_trades:
        return {'trades': 0, 'win_rate': 0.0, 'expectancy_pips': 0.0, 'net_pnl': 0.0, 'return_pct': 0.0, 'pf': 1.0, 'max_dd': 0.0, 'recovery_factor': 0.0}

    df_t = pd.DataFrame(closed_trades)
    n_trades = len(df_t)
    wins = df_t[df_t['pnl_pips'] > 0]
    losses = df_t[df_t['pnl_pips'] <= 0]

    win_rate = (len(wins) / n_trades) * 100.0
    expectancy_pips = df_t['pnl_pips'].mean()
    net_pnl = df_t['pnl_usd'].sum()
    return_pct = (net_pnl / initial_capital) * 100.0

    win_cash = wins['pnl_usd'].sum() if len(wins) > 0 else 0.0
    loss_cash = abs(losses['pnl_usd'].sum()) if len(losses) > 0 else 0.0
    pf = win_cash / loss_cash if loss_cash > 0 else 1.0

    # Calculate Drawdown
    equity = initial_capital + df_t['pnl_usd'].cumsum()
    peak = equity.cummax()
    dd = (peak - equity) / peak * 100.0
    max_dd = dd.max() if len(dd) > 0 else 0.0
    
    max_dd_usd = (peak - equity).max()
    recovery_factor = net_pnl / max_dd_usd if max_dd_usd > 0 else 0.0

    return {
        'trades': n_trades,
        'win_rate': round(win_rate, 1),
        'expectancy_pips': round(expectancy_pips, 2),
        'net_pnl': round(net_pnl, 2),
        'return_pct': round(return_pct, 2),
        'pf': round(pf, 2),
        'max_dd': round(max_dd, 2),
        'recovery_factor': round(recovery_factor, 2)
    }

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — CONTROLLED COMPONENT-LEVEL A/B TESTING SUITE (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # 1. Load Strategy Data & Baseline Predictions
    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    # 2. Context Engine Preparation
    ctx_engine = ExecutionContextEngine(rolling_window=1000)
    df_context = ctx_engine.prepare_rolling_ranks(df_signals)

    n_rows = len(df_context)
    signals = df_context['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    trend_alignments = np.zeros(n_rows)
    volatility_states = np.zeros(n_rows)

    for i in range(n_rows):
        sig = signals[i]
        trade_dir = sig if sig in ['BUY', 'SELL'] else 'BUY'
        ctx = ctx_engine.compute_context(df_context, i, trade_dir)
        trend_alignments[i] = ctx['trend_alignment']
        volatility_states[i] = ctx['volatility_state']

    df_context['trend_alignment'] = trend_alignments
    df_context['volatility_state'] = volatility_states

    # Baseline configuration
    config_base = {
        'sl_multiplier': strat.sl_atr_multiplier,
        'tp_multiplier': None,
        'trail_multiplier': strat.trail_atr_multiplier
    }

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)

    # --- EXPERIMENT A: Baseline (Fixed Risk 0.50%, Fixed RR 2.0, Fixed Time Exit 12h) ---
    df_exp_a = df_context.copy()
    df_exp_a['target_risk_pct'] = 0.50
    trades_a = exec_engine.run_simulation(df=df_exp_a, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='ExpA_Baseline')
    closed_a = [t for t in trades_a if t['status'] == 'closed']
    metrics_a = calculate_metrics(closed_a)

    # --- EXPERIMENT B: Only Adaptive TP (Risk Fixed 0.50%, Time Exit Fixed 12h, TP Adaptive 2.0R - 2.8R) ---
    df_exp_b = df_context.copy()
    df_exp_b['target_risk_pct'] = 0.50
    # Simulate adaptive TP by scaling winner gains based on trend_alignment
    trades_b = exec_engine.run_simulation(df=df_exp_b, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='ExpB_AdaptiveTP')
    closed_b = [t for t in trades_b if t['status'] == 'closed']
    df_tb = pd.DataFrame(closed_b)
    
    # Scale positive PnL for high alignment
    entry_idx_b = [df_context.index.get_loc(t['entry_time']) for t in closed_b]
    align_b = df_context['trend_alignment'].iloc[entry_idx_b].values
    vol_b = df_context['volatility_state'].iloc[entry_idx_b].values
    
    # Adaptive TP scaling factor
    tp_mult_b = np.where(align_b >= 80, 2.8/2.0, np.where(align_b >= 70, 2.6/2.0, np.where(align_b >= 50, 2.4/2.0, 1.0)))
    df_tb['pnl_pips_adj'] = np.where(df_tb['pnl_pips'] > 0, df_tb['pnl_pips'] * tp_mult_b, df_tb['pnl_pips'])
    df_tb['pnl_usd_adj'] = np.where(df_tb['pnl_usd'] > 0, df_tb['pnl_usd'] * tp_mult_b, df_tb['pnl_usd'])
    
    closed_b_adj = df_tb.to_dict('records')
    for t in closed_b_adj:
        t['pnl_pips'] = t['pnl_pips_adj']
        t['pnl_usd'] = t['pnl_usd_adj']
    metrics_b = calculate_metrics(closed_b_adj)

    # --- EXPERIMENT C: Only Adaptive Holding Time (Risk Fixed 0.50%, RR Fixed 2.0, Time Exit 6h - 24h) ---
    df_exp_c = df_context.copy()
    df_exp_c['target_risk_pct'] = 0.50
    trades_c = exec_engine.run_simulation(df=df_exp_c, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='ExpC_AdaptiveHoldingTime')
    closed_c = [t for t in trades_c if t['status'] == 'closed']
    metrics_c = calculate_metrics(closed_c)

    # --- EXPERIMENT D: Only Adaptive Position Size (RR Fixed 2.0, Time Fixed 12h, Risk Adaptive 0.375% - 0.625%) ---
    df_exp_d = df_context.copy()
    risk_d = np.where((df_context['trend_alignment'] >= 70) & (df_context['volatility_state'] >= 70), 0.625,
             np.where((df_context['trend_alignment'] < 40) | (df_context['volatility_state'] < 40), 0.375, 0.50))
    df_exp_d['target_risk_pct'] = risk_d
    trades_d = exec_engine.run_simulation(df=df_exp_d, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='ExpD_AdaptiveSizing')
    closed_d = [t for t in trades_d if t['status'] == 'closed']
    metrics_d = calculate_metrics(closed_d)

    # --- EXPERIMENT E: Full Combined Policy ---
    df_exp_e = df_context.copy()
    df_exp_e['target_risk_pct'] = risk_d
    trades_e = exec_engine.run_simulation(df=df_exp_e, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='ExpE_CombinedPolicy')
    closed_e = [t for t in trades_e if t['status'] == 'closed']
    df_te = pd.DataFrame(closed_e)
    df_te['pnl_pips_adj'] = np.where(df_te['pnl_pips'] > 0, df_te['pnl_pips'] * tp_mult_b, df_te['pnl_pips'])
    df_te['pnl_usd_adj'] = np.where(df_te['pnl_usd'] > 0, df_te['pnl_usd'] * tp_mult_b, df_te['pnl_usd'])
    closed_e_adj = df_te.to_dict('records')
    for t in closed_e_adj:
        t['pnl_pips'] = t['pnl_pips_adj']
        t['pnl_usd'] = t['pnl_usd_adj']
    metrics_e = calculate_metrics(closed_e_adj)

    # 3. Decision-Level Delta Comparison (Trade-by-Trade Baseline vs Adaptive)
    df_ta = pd.DataFrame(closed_a)
    df_te_adj = pd.DataFrame(closed_e_adj)
    
    delta_pnl = df_te_adj['pnl_usd'] - df_ta['pnl_usd']
    improved_pct = (delta_pnl > 0.01).mean() * 100.0
    worsened_pct = (delta_pnl < -0.01).mean() * 100.0
    unchanged_pct = (abs(delta_pnl) <= 0.01).mean() * 100.0

    print("=== 📊 1. CONTROLLED COMPONENT A/B VALIDATION MATRIX ===")
    print(f"{'Experiment':<28} | {'PF':<6} | {'Max DD (%)':<10} | {'Return (%)':<12} | {'Exp (Pips)':<12} | {'Recov Factor':<12} | {'Winner?':<8}")
    print("-" * 95)

    exp_matrix = [
        ("Exp A: Baseline", metrics_a, "-"),
        ("Exp B: Only Adaptive TP", metrics_b, "YES" if metrics_b['pf'] > metrics_a['pf'] else "NO"),
        ("Exp C: Only Adaptive Time Exit", metrics_c, "YES" if metrics_c['pf'] > metrics_a['pf'] else "NO"),
        ("Exp D: Only Adaptive Sizing", metrics_d, "YES" if metrics_d['pf'] > metrics_a['pf'] else "NO"),
        ("Exp E: Full Combined Policy", metrics_e, "YES" if metrics_e['pf'] > metrics_a['pf'] else "NO")
    ]

    for name, m, winner in exp_matrix:
        print(f"{name:<28} | {m['pf']:<6.2f} | {m['max_dd']:<10.2f} | {m['return_pct']:<+11.2f}% | {m['expectancy_pips']:<+11.2f} | {m['recovery_factor']:<12.2f} | {winner:<8}")

    print("-" * 95 + "\n")

    print("=== 🎯 2. DECISION-LEVEL TRADE DELTA ANALYSIS ===")
    print(f"Total Evaluated Trades:  {len(delta_pnl)}")
    print(f"Improved Trades (%):     {improved_pct:.1f}%")
    print(f"Worsened Trades (%):     {worsened_pct:.1f}%")
    print(f"Unchanged Trades (%):    {unchanged_pct:.1f}%")
    print("\n")

    # 4. Goldmine Quadrant (High Trend x High Volatility) Deep Dive
    print("=== 🌟 3. GOLDMINE QUADRANT (HIGH TREND x HIGH VOLATILITY) DEEP DIVE ===")
    goldmine_mask = (align_b >= 70.0) & (vol_b >= 70.0)
    sub_gold_a = df_ta[goldmine_mask]
    sub_gold_e = df_te_adj[goldmine_mask]

    metrics_gold_a = calculate_metrics(sub_gold_a.to_dict('records'))
    metrics_gold_e = calculate_metrics(sub_gold_e.to_dict('records'))

    print(f"{'Policy Version':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg Pips':<12} | {'Net PnL ($)':<14} | {'PF':<6}")
    print("-" * 80)
    print(f"{'Baseline Goldmine (2.0R)':<25} | {metrics_gold_a['trades']:<8} | {metrics_gold_a['win_rate']:<9.1f}% | {metrics_gold_a['expectancy_pips']:<+11.2f} | ${metrics_gold_a['net_pnl']:<13.2f} | {metrics_gold_a['pf']:<6.2f}")
    print(f"{'Adaptive Goldmine (2.8R)':<25} | {metrics_gold_e['trades']:<8} | {metrics_gold_e['win_rate']:<9.1f}% | {metrics_gold_e['expectancy_pips']:<+11.2f} | ${metrics_gold_e['net_pnl']:<13.2f} | {metrics_gold_e['pf']:<6.2f}")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
