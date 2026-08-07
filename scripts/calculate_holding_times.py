#!/usr/bin/env python3
"""
Trade Holding Time Analysis Script — AI Quant Lab
Calculates lowest (minimum), average (mean), median, and longest (maximum) trade holding times across EURUSD and multi-asset backtest data.
"""

import sys
import os
import json
import numpy as np
import pandas as pd

from data_loader import DataLoader, DataRequest
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from execution_engine.engine import ExecutionEngine
from macro_engine.parser import MacroContextEngine
from execution_policy_engine.policy import ExecutionPolicyEngine

def analyze_asset(symbol, timeframe='1h', start='2018-01-01', end='2025-12-31'):
    print(f"=== ANALYZING TRADE HOLDING TIMES FOR {symbol} ({start} to {end}) ===")
    
    loader = DataLoader()
    try:
        strat = InstitutionalAIStrategy()
        df_signals = strat.prepare_data(loader, symbol, start, end)
    except Exception as e:
        print(f"Error preparing data for {symbol}: {e}\n")
        return None

    n_rows = len(df_signals)
    signals = np.full(n_rows, None, dtype=object)
    if 'signal' in df_signals.columns:
        signals = df_signals['signal'].values
    else:
        signals[df_signals['entry_signal'].values] = 'BUY'

    macro_engine = MacroContextEngine()
    policy_engine = ExecutionPolicyEngine(allow_risk_expansion=False)
    
    vol_rank = df_signals['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_signals.columns else np.full(n_rows, 50.0)
    base_risk = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
    
    macro_risk_mults = np.ones(n_rows)
    for i in range(n_rows):
        ts = df_signals.index[i]
        macro_ctx = macro_engine.get_macro_context(symbol, ts, df_signals, i)
        state_vec = {
            "market_context_index": macro_ctx["market_context_index"],
            "trend_alignment": macro_ctx["trend_macro"],
            "volatility_state": macro_ctx["risk_sentiment"],
            "macro_context": macro_ctx
        }
        pol = policy_engine.determine_policy(state_vec)
        macro_risk_mults[i] = pol["risk_multiplier"]

    df_signals['target_risk_pct'] = base_risk * macro_risk_mults

    config = {
        'sl_multiplier': 2.0,
        'tp_multiplier': 3.6,
        'trail_multiplier': None
    }

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    trades = exec_engine.run_simulation(
        df=df_signals,
        signals=signals,
        config=config,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name="InstitutionalAIStrategy"
    )

    closed_trades = [t for t in trades if t['status'] == 'closed']
    if not closed_trades:
        print(f"No closed trades for {symbol}\n")
        return None

    df_closed = pd.DataFrame(closed_trades)
    df_closed['holding_hours'] = (pd.to_datetime(df_closed['exit_time']) - pd.to_datetime(df_closed['entry_time'])).dt.total_seconds() / 3600.0

    min_h = float(df_closed['holding_hours'].min())
    avg_h = float(df_closed['holding_hours'].mean())
    median_h = float(df_closed['holding_hours'].median())
    max_h = float(df_closed['holding_hours'].max())

    def fmt_time(hours):
        h = int(hours)
        m = int(round((hours - h) * 60))
        if h == 0:
            return f"{m} Mins ({hours:.2f}h)"
        elif m == 0:
            return f"{h} Hours"
        else:
            return f"{h} Hours {m} Mins ({hours:.2f}h)"

    print(f"  • Total Executed Trades:            {len(df_closed)}")
    print(f"  • Lowest (Minimum) Trade Holding Time: {fmt_time(min_h)}")
    print(f"  • Average (Mean) Trade Holding Time:    {fmt_time(avg_h)}")
    print(f"  • Median Trade Holding Time:           {fmt_time(median_h)}")
    print(f"  • Longest (Maximum) Trade Holding Time: {fmt_time(max_h)}\n")

    return {
        'symbol': symbol,
        'count': len(df_closed),
        'min_hours': min_h,
        'avg_hours': avg_h,
        'median_hours': median_h,
        'max_hours': max_h,
        'min_str': fmt_time(min_h),
        'avg_str': fmt_time(avg_h),
        'max_str': fmt_time(max_h)
    }

if __name__ == "__main__":
    results = {}
    symbols = ['EURUSD', 'XAUUSD']
    for sym in symbols:
        res = analyze_asset(sym)
        if res:
            results[sym] = res

    print("=================================================================================")
    print("  📊 COMPARATIVE TRADE HOLDING TIME MATRIX (ALL BACKTESTED ASSETS)")
    print("=================================================================================")
    for sym, res in results.items():
        print(f"Asset: {sym}")
        print(f"  • Total Trades Analyzed:      {res['count']}")
        print(f"  • Lowest (Minimum) Holding Time:  {res['min_str']}")
        print(f"  • Average (Mean) Holding Time:    {res['avg_str']}")
        print(f"  • Longest (Maximum) Holding Time: {res['max_str']}")
        print("-" * 65)
