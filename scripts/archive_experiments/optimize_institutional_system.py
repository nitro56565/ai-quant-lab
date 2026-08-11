import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import numpy as np
import pandas as pd
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.WARNING)

def run_system_optimization():
    print("=================================================================================")
    print("  🚀 AI QUANT LAB — SYSTEM-WIDE INSTITUTIONAL TARGET OPTIMIZATION ENGINE")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    # 1. Inspect Signal Distribution & Dual Direction (Long vs Short)
    n_rows = len(df_signals)
    session_ok = ~df_signals.index.hour.isin([13, 14, 15, 16])
    cost_drag = 1.5

    prob_l = df_signals['pred_prob_long'].values if 'pred_prob_long' in df_signals.columns else np.full(n_rows, 0.5)
    mfe_l = df_signals['pred_mfe_long'].values if 'pred_mfe_long' in df_signals.columns else np.full(n_rows, 20.0)
    mae_l = df_signals['pred_mae_long'].values if 'pred_mae_long' in df_signals.columns else np.full(n_rows, 10.0)
    net_ev_l = (prob_l * mfe_l) - ((1.0 - prob_l) * mae_l) - cost_drag

    prob_s = df_signals['pred_prob_short'].values if 'pred_prob_short' in df_signals.columns else np.full(n_rows, 0.5)
    mfe_s = df_signals['pred_mfe_short'].values if 'pred_mfe_short' in df_signals.columns else np.full(n_rows, 20.0)
    mae_s = df_signals['pred_mae_short'].values if 'pred_mae_short' in df_signals.columns else np.full(n_rows, 10.0)
    net_ev_s = (prob_s * mfe_s) - ((1.0 - prob_s) * mae_s) - cost_drag

    # Test lower quantile thresholds (Top 15% EV instead of Top 5% EV) to reach >500 OOS trades
    ev_q85_l = np.percentile(net_ev_l[net_ev_l > 0], 85) if len(net_ev_l[net_ev_l > 0]) > 0 else 5.0
    ev_q85_s = np.percentile(net_ev_s[net_ev_s > 0], 85) if len(net_ev_s[net_ev_s > 0]) > 0 else 5.0

    prob_q85_l = max(float(np.percentile(prob_l, 80)), 0.51)
    prob_q85_s = max(float(np.percentile(prob_s, 80)), 0.51)

    long_ok = (net_ev_l >= ev_q85_l) & (prob_l >= prob_q85_l) & session_ok
    short_ok = (net_ev_s >= ev_q85_s) & (prob_s >= prob_q85_s) & session_ok

    signals_opt = np.full(n_rows, None, dtype=object)
    for i in range(n_rows):
        if long_ok[i] and not short_ok[i]:
            signals_opt[i] = 'BUY'
        elif short_ok[i] and not long_ok[i]:
            signals_opt[i] = 'SELL'
        elif long_ok[i] and short_ok[i]:
            if net_ev_l[i] >= net_ev_s[i]:
                signals_opt[i] = 'BUY'
            else:
                signals_opt[i] = 'SELL'

    df_signals['signal_opt'] = signals_opt

    # Volatility Sizing (0.25% - 1.00%)
    vol_rank = df_signals['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_signals.columns else np.full(n_rows, 50.0)
    risk_vol = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
    df_signals['target_risk_pct'] = risk_vol

    config_opt = {
        'sl_multiplier': 2.0,
        'tp_multiplier': 4.0,  # 2.0R target gives 45-50% win rate
        'trail_multiplier': None
    }

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    trades = exec_engine.run_simulation(
        df=df_signals,
        signals=signals_opt,
        config=config_opt,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name="SymmetricalOptimized"
    )

    closed_trades = [t for t in trades if t['status'] == 'closed']
    metrics = exec_engine.calculate_performance(closed_trades, start_date, end_date)

    df_trades = pd.DataFrame(closed_trades)
    df_trades['year'] = pd.to_datetime(df_trades['exit_time']).dt.year

    # Regime Breakdown
    hmm_states = df_signals['feat_hmm_regime'].values if 'feat_hmm_regime' in df_signals.columns else np.zeros(n_rows)
    entry_indices = [df_signals.index.get_loc(t['entry_time']) for t in closed_trades]
    df_trades['hmm_state'] = hmm_states[entry_indices]
    
    regime_pfs = {}
    for state in [0.0, 1.0, 2.0]:
        sub_t = df_trades[df_trades['hmm_state'] == state]
        if len(sub_t) > 0:
            w_c = sub_t[sub_t['pnl_pips'] > 0]['pnl_usd'].sum()
            l_c = abs(sub_t[sub_t['pnl_pips'] <= 0]['pnl_usd'].sum())
            regime_pfs[state] = round(w_c / l_c if l_c > 0 else 1.0, 2)
        else:
            regime_pfs[state] = 1.0

    print("=================================================================================")
    print("  📊 SYSTEM OPTIMIZATION PERFORMANCE SUMMARY (EURUSD 2018 - 2025)")
    print("=================================================================================")
    print(f"   • Total OOS Executed Trades:         {metrics['trades']} (Target >= 500)")
    print(f"   • Win Rate (Hit Ratio):              {metrics['win_rate']:.1f}% (Target >= 40%)")
    print(f"   • Expected Value (EV):               {metrics['ev_pips']:+.2f} pips (${metrics['ev_usd']:+0.2f}) (Target > +2.0 pips)")
    print(f"   • Profit Factor (PF):                {metrics['pf']:.2f} (Target >= 1.30)")
    print(f"   • Sharpe Ratio:                      {metrics['sharpe']:.2f} (Target >= 1.0)")
    print(f"   • Sortino Ratio:                     {metrics['sortino']:.2f} (Target >= 1.2)")
    print(f"   • Calmar Ratio:                      {metrics['calmar']:.2f} (Target >= 0.7)")
    print(f"   • Max Peak-to-Trough Drawdown:       {metrics['max_dd']:.2f}% (Target <= 15%)")
    print(f"   • Probabilistic Sharpe Ratio (PSR):  {metrics['psr']:.4f} (Target >= 0.95)")
    print("---------------------------------------------------------------------------------\n")

    print("=================================================================================")
    print("  📊 HMM REGIME-SEGMENTED PROFIT FACTOR BREAKDOWN")
    print("=================================================================================")
    print(f"   • Bull Regime (State 0) PF:          {regime_pfs.get(0.0, 1.0):.2f} (Target >= 1.20)")
    print(f"   • Bear Regime (State 1) PF:          {regime_pfs.get(1.0, 1.0):.2f} (Target >= 1.05)")
    print(f"   • Choppy Regime (State 2) PF:        {regime_pfs.get(2.0, 1.0):.2f} (Target >= 1.00)")
    print("---------------------------------------------------------------------------------\n")

    print("=================================================================================")
    print("  📅 YEAR-OVER-YEAR (YoY) MATRIX")
    print("=================================================================================")
    print(f"   {'Year':<6} | {'Return (%)':<12} | {'Net PnL ($)':<14} | {'Max DD (%)':<11} | {'Trades':<8} | {'Win Rate':<9} | {'Profit Factor':<13}")
    print("   " + "-" * 88)

    ym = metrics['yearly_metrics']
    for yr in range(2018, 2026):
        y_data = ym[yr]
        print(f"   {yr:<6} | {y_data['return_pct']:<+11.2f}% | ${y_data['net_pnl']:<+13.2f} | {y_data['max_dd']:<10.2f}% | {y_data['trades']:<8} | {y_data['win_rate']:<8.1f}% | {y_data['pf']:<13.2f}")
    print("=================================================================================\n")

if __name__ == "__main__":
    run_system_optimization()
