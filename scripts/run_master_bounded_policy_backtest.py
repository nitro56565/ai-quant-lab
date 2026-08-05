import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from execution_policy_engine.policy import ExecutionPolicyEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MasterBoundedPolicyBacktest")

def main():
    print("=================================================================================")
    print("  🤖 MASTER INSTITUTIONAL BOUNDED EXECUTION POLICY BACKTEST (2018 - 2025)")
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

    policy_engine = ExecutionPolicyEngine()

    n_rows = len(df_context)
    signals = df_context['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    target_risk_pcts = np.full(n_rows, 0.50)
    tp_multipliers = np.full(n_rows, 2.0)

    for i in range(n_rows):
        sig = signals[i]
        if sig in ['BUY', 'SELL']:
            ctx = ctx_engine.compute_context(df_context, i, sig)
            policy = policy_engine.determine_policy(ctx)
            
            if policy['action'] != 'SKIP_TRADE':
                target_risk_pcts[i] = 0.50 * policy['risk_multiplier']
                tp_multipliers[i] = policy['tp_r_multiple']

    df_context['target_risk_pct'] = target_risk_pcts

    # 3. Execute Master Bounded Policy Simulation
    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    config = {
        'sl_multiplier': strat.sl_atr_multiplier,
        'tp_multiplier': None,
        'trail_multiplier': strat.trail_atr_multiplier
    }

    trades = exec_engine.run_simulation(
        df=df_context,
        signals=signals,
        config=config,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name='BoundedExecutionPolicyAI'
    )

    closed = [t for t in trades if t['status'] == 'closed']
    df_trades = pd.DataFrame(closed)
    df_trades['year'] = pd.to_datetime(df_trades['exit_time']).dt.year

    print("=== YEARLY PERFORMANCE BREAKDOWN: BOUNDED EXECUTION POLICY (2018 - 2025) ===\n")
    print(f"{'Year':<6} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL ($)':<14} | {'Return (%)':<12} | {'Profit Factor':<14}")
    print("-" * 75)

    total_initial = 10000.0
    curr_cap = total_initial

    for yr in range(2018, 2026):
        yr_trades = df_trades[df_trades['year'] == yr]
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

    tot_wins = [t for t in closed if t['pnl_pips'] > 0]
    tot_loss = [t for t in closed if t['pnl_pips'] <= 0]
    tot_pf = sum(t['pnl_usd'] for t in tot_wins) / max(abs(sum(t['pnl_usd'] for t in tot_loss)), 1e-9)

    print("-" * 75)
    print(f"{'TOTAL':<6} | {len(closed):<8} | {(len(tot_wins)/max(len(closed),1))*100:<9.1f}% | ${curr_cap - total_initial:<13.2f} | {((curr_cap - total_initial)/total_initial)*100:<+11.2f}% | {tot_pf:<14.2f}")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
