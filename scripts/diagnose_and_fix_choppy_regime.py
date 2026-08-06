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
from execution_engine import ExecutionEngine
from ai_engine.regime_hmm import HMMRegimeDetector

logging.basicConfig(level=logging.WARNING)

def main():
    print("=================================================================================")
    print("  🔬 RESEARCH: DIAGNOSING & SOLVING CHOPPY MARKET (STATE 0) PROFITABILITY")
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

    n_rows = len(df_signals)
    signals = df_signals['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    vol_rank = df_signals['feat_vol_atr_pct'].values
    risk_vol = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
    df_signals['target_risk_pct'] = risk_vol

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)

    # 1. BASELINE RUN (Fixed TP 3.6 = 1.8R, SL 2.0 = 1.0R)
    config_base = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}
    trades_base = exec_engine.run_simulation(df=df_signals, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name="Baseline")
    closed_base = [t for t in trades_base if t['status'] == 'closed']
    
    df_closed_base = pd.DataFrame(closed_base)
    entry_idx = [df_signals.index.get_loc(t['entry_time']) for t in closed_base]
    df_closed_base['hmm_state'] = states[entry_idx]

    sub_st0_base = df_closed_base[df_closed_base['hmm_state'] == 0]
    pnl_st0_base = sub_st0_base['pnl_usd'].sum()
    w_c = sub_st0_base[sub_st0_base['pnl_pips'] > 0]['pnl_usd'].sum()
    l_c = abs(sub_st0_base[sub_st0_base['pnl_pips'] <= 0]['pnl_usd'].sum())
    pf_st0_base = w_c / l_c if l_c > 0 else 1.0

    print("=== 📊 1. BASELINE CHOPPY REGIME (STATE 0) METRICS ===")
    print(f"   • Total State 0 Trades: {len(sub_st0_base)}")
    print(f"   • State 0 Net PnL:       ${pnl_st0_base:+.2f}")
    print(f"   • State 0 Profit Factor: {pf_st0_base:.2f}\n")

    # 2. SOLUTION A: Quick Target Escalation in State 0 (TP = 1.2R = 2.4x ATR)
    # In choppy markets, smaller TP targets fill quickly before price reverses!
    tp_mults_solA = np.where(states[entry_idx] == 0, 2.4 / 3.6, np.where(vol_rank[entry_idx] >= 60, 4.8 / 3.6, 1.0))
    df_closed_solA = df_closed_base.copy()
    df_closed_solA['pnl_pips'] = np.where(df_closed_solA['pnl_pips'] > 0, df_closed_solA['pnl_pips'] * tp_mults_solA, df_closed_solA['pnl_pips'])
    df_closed_solA['pnl_usd'] = np.where(df_closed_solA['pnl_usd'] > 0, df_closed_solA['pnl_usd'] * tp_mults_solA, df_closed_solA['pnl_usd'])
    
    sub_st0_solA = df_closed_solA[df_closed_solA['hmm_state'] == 0]
    pnl_st0_solA = sub_st0_solA['pnl_usd'].sum()
    w_cA = sub_st0_solA[sub_st0_solA['pnl_pips'] > 0]['pnl_usd'].sum()
    l_cA = abs(sub_st0_solA[sub_st0_solA['pnl_pips'] <= 0]['pnl_usd'].sum())
    pf_st0_solA = w_cA / l_cA if l_cA > 0 else 1.0

    m_solA = exec_engine.calculate_performance(df_closed_solA.to_dict('records'), start_date, end_date)

    print("=== 🧪 2. SOLUTION A: FAST TARGET (1.2R) IN CHOPPY REGIME ===")
    print(f"   • State 0 Net PnL:       ${pnl_st0_solA:+.2f}")
    print(f"   • State 0 Profit Factor: {pf_st0_solA:.2f}")
    print(f"   • Total Strategy Return: {m_solA['return_pct']:+.2f}% (${m_solA['net_pnl']:+0.2f})")
    print(f"   • Overall Profit Factor: {m_solA['pf']:.2f}\n")

    # 3. SOLUTION B: Mean Reversion / RSI Fade Signal Integration in State 0
    # In State 0, when RSI is oversold (< 45) trigger BUY, when RSI is overbought (> 55) trigger SELL
    rsi = df_signals['feat_osc_rsi'].values if 'feat_osc_rsi' in df_signals.columns else np.full(n_rows, 50.0)
    sig_solB = signals.copy()
    
    for i in range(n_rows):
        if states[i] == 0:
            if rsi[i] < 42:
                sig_solB[i] = 'BUY'
            elif rsi[i] > 58:
                sig_solB[i] = 'SELL'

    trades_solB = exec_engine.run_simulation(df=df_signals, signals=sig_solB, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name="SolB")
    closed_solB = [t for t in trades_solB if t['status'] == 'closed']
    df_closed_solB = pd.DataFrame(closed_solB)
    entry_idxB = [df_signals.index.get_loc(t['entry_time']) for t in closed_solB]
    df_closed_solB['hmm_state'] = states[entry_idxB]

    tp_mults_solB = np.where(states[entry_idxB] == 0, 2.4 / 3.6, np.where(vol_rank[entry_idxB] >= 60, 4.8 / 3.6, 1.0))
    df_closed_solB['pnl_pips'] = np.where(df_closed_solB['pnl_pips'] > 0, df_closed_solB['pnl_pips'] * tp_mults_solB, df_closed_solB['pnl_pips'])
    df_closed_solB['pnl_usd'] = np.where(df_closed_solB['pnl_usd'] > 0, df_closed_solB['pnl_usd'] * tp_mults_solB, df_closed_solB['pnl_usd'])

    sub_st0_solB = df_closed_solB[df_closed_solB['hmm_state'] == 0]
    pnl_st0_solB = sub_st0_solB['pnl_usd'].sum()
    w_cB = sub_st0_solB[sub_st0_solB['pnl_pips'] > 0]['pnl_usd'].sum()
    l_cB = abs(sub_st0_solB[sub_st0_solB['pnl_pips'] <= 0]['pnl_usd'].sum())
    pf_st0_solB = w_cB / l_cB if l_cB > 0 else 1.0

    m_solB = exec_engine.calculate_performance(df_closed_solB.to_dict('records'), start_date, end_date)

    print("=== 🧪 3. SOLUTION B: MEAN REVERSION (RSI FADE) IN CHOPPY REGIME ===")
    print(f"   • State 0 Trades:        {len(sub_st0_solB)}")
    print(f"   • State 0 Net PnL:       ${pnl_st0_solB:+.2f}")
    print(f"   • State 0 Profit Factor: {pf_st0_solB:.2f}")
    print(f"   • Total Strategy Return: {m_solB['return_pct']:+.2f}% (${m_solB['net_pnl']:+0.2f})")
    print(f"   • Overall Profit Factor: {m_solB['pf']:.2f}\n")

    # 4. SOLUTION C: Low-Vol Noise Filter (Skip State 0 signals unless EV >= 6.0 pips)
    sig_solC = signals.copy()
    net_ev_l = df_signals['pred_ev_long'].values if 'pred_ev_long' in df_signals.columns else np.zeros(n_rows)
    net_ev_s = df_signals['pred_ev_short'].values if 'pred_ev_short' in df_signals.columns else np.zeros(n_rows)
    
    for i in range(n_rows):
        if states[i] == 0:
            max_ev = max(net_ev_l[i], net_ev_s[i])
            if max_ev < 6.0:
                sig_solC[i] = None

    trades_solC = exec_engine.run_simulation(df=df_signals, signals=sig_solC, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name="SolC")
    closed_solC = [t for t in trades_solC if t['status'] == 'closed']
    df_closed_solC = pd.DataFrame(closed_solC)
    entry_idxC = [df_signals.index.get_loc(t['entry_time']) for t in closed_solC]
    df_closed_solC['hmm_state'] = states[entry_idxC]

    tp_mults_solC = np.where(vol_rank[entry_idxC] >= 60, 4.8 / 3.6, 1.0)
    df_closed_solC['pnl_pips'] = np.where(df_closed_solC['pnl_pips'] > 0, df_closed_solC['pnl_pips'] * tp_mults_solC, df_closed_solC['pnl_pips'])
    df_closed_solC['pnl_usd'] = np.where(df_closed_solC['pnl_usd'] > 0, df_closed_solC['pnl_usd'] * tp_mults_solC, df_closed_solC['pnl_usd'])

    sub_st0_solC = df_closed_solC[df_closed_solC['hmm_state'] == 0]
    pnl_st0_solC = sub_st0_solC['pnl_usd'].sum()
    w_cC = sub_st0_solC[sub_st0_solC['pnl_pips'] > 0]['pnl_usd'].sum()
    l_cC = abs(sub_st0_solC[sub_st0_solC['pnl_pips'] <= 0]['pnl_usd'].sum())
    pf_st0_solC = w_cC / l_cC if l_cC > 0 else 1.0

    m_solC = exec_engine.calculate_performance(df_closed_solC.to_dict('records'), start_date, end_date)

    print("=== 🧪 4. SOLUTION C: LOW-VOL EV FILTER (SKIP NOISE TRADES) IN CHOPPY REGIME ===")
    print(f"   • State 0 Trades:        {len(sub_st0_solC)}")
    print(f"   • State 0 Net PnL:       ${pnl_st0_solC:+.2f}")
    print(f"   • State 0 Profit Factor: {pf_st0_solC:.2f}")
    print(f"   • Total Strategy Return: {m_solC['return_pct']:+.2f}% (${m_solC['net_pnl']:+0.2f})")
    print(f"   • Overall Profit Factor: {m_solC['pf']:.2f}\n")

    print("=================================================================================")
    print("  🏆 SUMMARY OF CHOPPY MARKET SOLUTIONS")
    print("=================================================================================")
    print(f"   Baseline (Unfiltered State 0):    PnL = ${pnl_st0_base:+.2f} (PF = {pf_st0_base:.2f})")
    print(f"   Solution A (Quick 1.2R TP Target): PnL = ${pnl_st0_solA:+.2f} (PF = {pf_st0_solA:.2f})")
    print(f"   Solution B (RSI Mean Reversion):   PnL = ${pnl_st0_solB:+.2f} (PF = {pf_st0_solB:.2f})")
    print(f"   Solution C (EV Noise Gate Filter): PnL = ${pnl_st0_solC:+.2f} (PF = {pf_st0_solC:.2f})")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
