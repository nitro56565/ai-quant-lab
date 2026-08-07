#!/usr/bin/env python3
"""
Fast Vectorized Trade Holding Time Analysis Script — AI Quant Lab
Computes lowest (minimum), average (mean), median, and longest (maximum) trade holding durations across EURUSD, XAUUSD, and all available asset classes.
"""

import os
import sys
import numpy as np
import pandas as pd

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder

def run_triple_barrier_holding_analysis(symbol, start='2018-01-01', end='2025-12-31', tp_mult=2.5, sl_mult=1.5, max_h=24):
    loader = DataLoader()
    try:
        req = DataRequest(symbol=symbol, timeframe='1h', start=start, end=end)
        df = loader.load(req)
    except Exception as e:
        print(f"⚠️ Could not load data for {symbol}: {e}")
        return None

    builder = FeatureMatrixBuilder()
    df_feat = builder.build(df)

    close = df_feat['close'].values
    high = df_feat['high'].values
    low = df_feat['low'].values
    n = len(df_feat)

    if 'feat_vol_atr' in df_feat.columns:
        atr = df_feat['feat_vol_atr'].values
    else:
        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values

    holding_times = []

    for i in range(0, n - max_h, 4): # Sample every 4 hours for representative distribution
        entry_p = close[i]
        curr_atr = atr[i]
        if curr_atr <= 0:
            continue

        tp_long = entry_p + (tp_mult * curr_atr)
        sl_long = entry_p - (sl_mult * curr_atr)
        exit_bar = max_h # Expiration fallback

        for h in range(1, max_h + 1):
            c_h = high[i + h]
            c_l = low[i + h]
            if c_l <= sl_long or c_h >= tp_long:
                exit_bar = h
                break

        holding_times.append(exit_bar)

    if not holding_times:
        return None

    holding_arr = np.array(holding_times, dtype=float)
    min_h = float(np.min(holding_arr))
    avg_h = float(np.mean(holding_arr))
    median_h = float(np.median(holding_arr))
    max_h_val = float(np.max(holding_arr))
    total_trades = len(holding_arr)

    def fmt_time(hours):
        h = int(hours)
        m = int(round((hours - h) * 60))
        if h == 0:
            return f"{m} Mins ({hours:.2f}h)"
        elif m == 0:
            return f"{h} Hours"
        else:
            return f"{h} Hours {m} Mins ({hours:.2f}h)"

    return {
        'symbol': symbol,
        'total_trades': total_trades,
        'min_hours': min_h,
        'avg_hours': avg_h,
        'median_hours': median_h,
        'max_hours': max_h_val,
        'min_str': fmt_time(min_h),
        'avg_str': fmt_time(avg_h),
        'median_str': fmt_time(median_h),
        'max_str': fmt_time(max_h_val)
    }

def main():
    symbols = ['EURUSD', 'XAUUSD']
    results = []

    print("=================================================================================")
    print("  📊 STATISTICAL TRADE HOLDING TIME REPORT (RESEARCH & BACKTEST SUITE)")
    print("=================================================================================\n")

    for sym in symbols:
        res = run_triple_barrier_holding_analysis(sym)
        if res:
            results.append(res)
            print(f"📌 Asset Label: {res['symbol']}")
            print(f"   • Total Trades Sampled:              {res['total_trades']:,}")
            print(f"   • Lowest (Minimum) Trade Holding Time: {res['min_str']}")
            print(f"   • Average (Mean) Trade Holding Time:    {res['avg_str']}")
            print(f"   • Median Trade Holding Time:           {res['median_str']}")
            print(f"   • Longest (Maximum) Trade Holding Time: {res['max_str']}")
            print("-" * 70 + "\n")

    print("=================================================================================")
    print("  🏆 SUMMARY TABLE ACROSS ALL TESTED ASSETS")
    print("=================================================================================")
    print(f"{'ASSET LABEL':<15} | {'LOWEST (MIN)':<22} | {'AVERAGE (MEAN)':<22} | {'LONGEST (MAX)':<22}")
    print("-" * 88)
    for r in results:
        print(f"{r['symbol']:<15} | {r['min_str']:<22} | {r['avg_str']:<22} | {r['max_str']:<22}")
    print("-" * 88 + "\n")

if __name__ == "__main__":
    main()
