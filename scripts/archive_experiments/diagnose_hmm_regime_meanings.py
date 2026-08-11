import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from execution_engine import ExecutionEngine
from ai_engine.regime_hmm import HMMRegimeDetector

def main():
    print("=================================================================================")
    print("  🔍 DIAGNOSTIC: HMM REGIME MEANING & DIRECTIONAL PNL ANALYSIS")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    hmm = HMMRegimeDetector()
    hmm.fit(df_signals)
    states = hmm.predict(df_signals)
    df_signals['hmm_state'] = states

    print("=== 📊 1. FEATURE MEANS PER HMM STATE ===")
    for st in range(3):
        sub = df_signals[df_signals['hmm_state'] == st]
        print(f"--- State {st} (N = {len(sub)} candles) ---")
        print(f"   • EMA50 Slope (Trend Dir):  {sub['feat_trend_ema50_slope'].mean():+.6f}")
        print(f"   • ATR Percentile (Vol):     {sub['feat_vol_atr_pct'].mean():.2f}%")
        print(f"   • ADX (Trend Strength):     {sub['feat_trend_adx'].mean():.2f}")
        print(f"   • RSI (Oscillator):         {sub['feat_osc_rsi'].mean():.2f}\n")

    # Run simulation and break down PnL by Signal Direction (BUY vs SELL) and HMM State
    n_rows = len(df_signals)
    signals = df_signals['signal'].values

    vol_rank = df_signals['feat_vol_atr_pct'].values
    risk_vol = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
    df_signals['target_risk_pct'] = risk_vol

    config = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}
    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    trades = exec_engine.run_simulation(df=df_signals, signals=signals, config=config, symbol=symbol, pip_size=pip_size, strategy_name="Diag")
    closed_trades = [t for t in trades if t['status'] == 'closed']
    df_closed = pd.DataFrame(closed_trades)

    entry_idx = [df_signals.index.get_loc(t['entry_time']) for t in closed_trades]
    v_rank_sub = vol_rank[entry_idx]
    tp_mults = np.where(v_rank_sub >= 60, 2.4 / 1.8, 1.0)

    df_closed['pnl_pips'] = np.where(df_closed['pnl_pips'] > 0, df_closed['pnl_pips'] * tp_mults, df_closed['pnl_pips'])
    df_closed['pnl_usd'] = np.where(df_closed['pnl_usd'] > 0, df_closed['pnl_usd'] * tp_mults, df_closed['pnl_usd'])
    df_closed['hmm_state'] = states[entry_idx]

    print("=== 📊 2. PNL BREAKDOWN BY DIRECTION & HMM STATE ===")
    print(f"{'HMM State':<12} | {'Direction':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL ($)':<14} | {'PF':<6}")
    print("-" * 75)

    for st in [0, 1, 2]:
        for d in ['BUY', 'SELL']:
            sub = df_closed[(df_closed['hmm_state'] == st) & (df_closed['direction'] == d)]
            if len(sub) > 0:
                n_t = len(sub)
                wins = len(sub[sub['pnl_pips'] > 0])
                wr = (wins / n_t) * 100.0
                pnl = sub['pnl_usd'].sum()
                w_c = sub[sub['pnl_pips'] > 0]['pnl_usd'].sum()
                l_c = abs(sub[sub['pnl_pips'] <= 0]['pnl_usd'].sum())
                pf = w_c / l_c if l_c > 0 else 1.0
                print(f"{st:<12} | {d:<10} | {n_t:<8} | {wr:<9.1f}% | ${pnl:<+13.2f} | {pf:<6.2f}")

    print("=================================================================================\n")

if __name__ == "__main__":
    main()
