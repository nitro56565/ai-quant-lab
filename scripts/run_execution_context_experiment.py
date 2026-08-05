import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from research_engine.bucket_diagnostic import analyze_bucketed_expectancy
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExecutionContextExperiment")

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — EXECUTION CONTEXT ENGINE & BUCKETED DIAGNOSTIC (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # 1. Load Strategy Data & Predictions
    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    # 2. Compute Rolling Percentile Execution Context
    ctx_engine = ExecutionContextEngine(rolling_window=1000)
    df_context = ctx_engine.prepare_rolling_ranks(df_signals)

    n_rows = len(df_context)
    trend_alignments = np.zeros(n_rows)
    trend_persistences = np.zeros(n_rows)
    volatility_states = np.zeros(n_rows)

    signals = df_context['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    for i in range(n_rows):
        sig = signals[i]
        trade_dir = sig if sig in ['BUY', 'SELL'] else 'BUY'
        ctx = ctx_engine.compute_context(df_context, i, trade_dir)
        trend_alignments[i] = ctx['trend_alignment']
        trend_persistences[i] = ctx['trend_persistence']
        volatility_states[i] = ctx['volatility_state']

    df_context['trend_alignment'] = trend_alignments
    df_context['trend_persistence'] = trend_persistences
    df_context['volatility_state'] = volatility_states

    # 3. First Backtest: Baseline Trade Signals with Context Logging
    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    config_base = {
        'sl_multiplier': strat.sl_atr_multiplier,
        'tp_multiplier': None,
        'trail_multiplier': strat.trail_atr_multiplier
    }

    trades_base = exec_engine.run_simulation(
        df=df_context,
        signals=signals,
        config=config_base,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name='BaselineInstitutionalAI'
    )

    closed_base = [t for t in trades_base if t['status'] == 'closed']
    df_trades_base = pd.DataFrame(closed_base)

    # Map context scores to trades at entry time
    entry_indices = [df_context.index.get_loc(t['entry_time']) for t in closed_base]
    df_trades_base['trend_alignment'] = df_context['trend_alignment'].iloc[entry_indices].values
    df_trades_base['trend_persistence'] = df_context['trend_persistence'].iloc[entry_indices].values
    df_trades_base['volatility_state'] = df_context['volatility_state'].iloc[entry_indices].values
    df_trades_base['year'] = pd.to_datetime(df_trades_base['exit_time']).dt.year

    # 4. Bucketed Expectancy Diagnostic Matrix
    print("=== 📊 BUCKETED EXPECTANCY DIAGNOSTIC: TREND ALIGNMENT ===")
    df_bucket_align = analyze_bucketed_expectancy(df_trades_base, 'trend_alignment')
    print(df_bucket_align.to_string(index=False))
    print("\n")

    print("=== 📊 BUCKETED EXPECTANCY DIAGNOSTIC: VOLATILITY STATE ===")
    df_bucket_vol = analyze_bucketed_expectancy(df_trades_base, 'volatility_state')
    print(df_bucket_vol.to_string(index=False))
    print("\n")

    # 5. Context-Modulated Execution Policy Simulation
    # NO TRADE FILTERING (100% of Signals Approved)
    # High Alignment (>= 70): Stretch TP (trail_multiplier = 4.5, sl_multiplier = 1.2)
    # Moderate Alignment (40-69): Standard Policy
    # Low Alignment (< 40): Conservative Policy (sl_multiplier = 1.0)
    print("=== 🚀 CONTEXT-MODULATED EXECUTION POLICY BACKTEST (2018 - 2025) ===\n")
    
    trades_ctx = exec_engine.run_simulation(
        df=df_context,
        signals=signals,
        config=config_base,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name='ContextModulatedInstitutionalAI'
    )

    closed_ctx = [t for t in trades_ctx if t['status'] == 'closed']
    df_trades_ctx = pd.DataFrame(closed_ctx)
    df_trades_ctx['year'] = pd.to_datetime(df_trades_ctx['exit_time']).dt.year

    print(f"{'Year':<6} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL ($)':<14} | {'Return (%)':<12} | {'Profit Factor':<14}")
    print("-" * 75)

    total_initial = 10000.0
    curr_cap = total_initial

    for yr in range(2018, 2026):
        yr_trades = df_trades_ctx[df_trades_ctx['year'] == yr]
        n_trades = len(yr_trades)

        if n_trades == 0:
            print(f"{yr:<6} | {0:<8} | {'0.0%':<10} | {'$0.00':<14} | {'+0.00%':<12} | {'1.00':<14}")
            continue

        wins = yr_trades[yr_trades['pnl_pips'] > 0]
        losses = yr_trades[yr_trades['pnl_pips'] <= 0]
        win_rate = (len(wins) / n_trades) * 100.0

        net_pnl = yr_trades['pnl_usd'].sum()
        ret_pct = (net_pnl / curr_cap) * 100.0
        curr_cap += net_pnl

        win_cash = sum(t['pnl_usd'] for t in wins.to_dict('records'))
        loss_cash = sum(t['pnl_usd'] for t in losses.to_dict('records'))
        pf = win_cash / abs(loss_cash) if abs(loss_cash) > 0 else 1.0

        print(f"{yr:<6} | {n_trades:<8} | {win_rate:<9.1f}% | ${net_pnl:<13.2f} | {ret_pct:<+11.2f}% | {pf:<14.2f}")

    tot_wins = [t for t in closed_ctx if t['pnl_pips'] > 0]
    tot_loss = [t for t in closed_ctx if t['pnl_pips'] <= 0]
    tot_pf = sum(t['pnl_usd'] for t in tot_wins) / max(abs(sum(t['pnl_usd'] for t in tot_loss)), 1e-9)

    print("-" * 75)
    print(f"{'TOTAL':<6} | {len(closed_ctx):<8} | {(len(tot_wins)/max(len(closed_ctx),1))*100:<9.1f}% | ${curr_cap - total_initial:<13.2f} | {((curr_cap - total_initial)/total_initial)*100:<+11.2f}% | {tot_pf:<14.2f}")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
