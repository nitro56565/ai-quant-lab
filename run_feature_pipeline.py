#!/usr/bin/env python3
"""
6-Tier Feature-Based Systematic Trading Backtester
===================================================
Ties together:
1. Data Loader (data_loader)
2. Feature Engine (feature_engine)
3. Regime Detector (regime_detector)
4. Signal Engine (signal_engine)
5. Risk Engine (risk_engine)
6. Execution Engine (execution_engine)
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader, DataRequest
from feature_engine import FeatureEngine
from regime_detector import RegimeDetector
from signal_engine import SignalEngine
from execution_engine import ExecutionEngine

# =====================================================================
# ⚙️ CONFIGURATION SETTINGS (Modify these to customize your backtest)
# =====================================================================
SYMBOL = "EURUSD"                   # Symbol to backtest
START_DATE = "2018-01-01"           # Start Date (YYYY-MM-DD)
END_DATE = "2026-09-30"             # End Date (YYYY-MM-DD)
INITIAL_CAPITAL = 10000.0           # Starting balance in USD

# Select the strategy to backtest:
#   - "AdaptiveTrendFollowing"    (Price structure higher highs/lows + slope)
#   - "PullbackContinuation"      (Price action pullback continuation + rejection)
#   - "MeanReversion"             (Distance from VWAP + RSI reversion)
#   - "VolatilityBreakout"        (Volatility Squeeze + channel breakout)
#   - "LondonSessionMomentum"     (London open timing + breakout momentum)
#   - "AdaptiveMomentumPullback"  (Adaptive Momentum Pullback score-card strategy)
SELECTED_STRATEGY = "AdaptiveMomentumPullback"
# =====================================================================


def main():
    print("=" * 70)
    print("🚀 6-TIER FEATURE-BASED SYSTEMATIC TRADING BACKTESTER")
    print("=" * 70)
    print(f"Target Symbol:     {SYMBOL}")
    print(f"Date Range:        {START_DATE} to {END_DATE}")
    print(f"Initial Capital:   ${INITIAL_CAPITAL:,.2f}")
    print(f"Selected Strategy: {SELECTED_STRATEGY}")
    print("-" * 70)

    # 1. Initialize Tiers
    loader = DataLoader()
    feat_engine = FeatureEngine()
    detector = RegimeDetector()
    sig_engine = SignalEngine()
    exec_engine = ExecutionEngine(initial_capital=INITIAL_CAPITAL, default_pip_value=1.0)
    
    # 2. Determine primary timeframe based on strategy
    primary_timeframe = "15m" if SELECTED_STRATEGY == "LondonSessionMomentum" else "1h"
    
    # Get metadata for pip sizing
    metadata = loader.get_symbol_metadata(SYMBOL)
    pip_size = metadata.get('pip_size', 0.0001)
    
    # 3. Generate Features (loads and aligns H4/H1/M15 automatically)
    print(f"⏳ Step 1 & 2: Running Feature Engine ({primary_timeframe} primary timeframe)...")
    try:
        df_featured = feat_engine.generate_features(
            loader=loader,
            symbol=SYMBOL,
            start_date=START_DATE,
            end_date=END_DATE,
            primary_timeframe=primary_timeframe
        )
    except Exception as e:
        print(f"❌ Failed to generate features: {e}")
        sys.exit(1)
    
    # 4. Classify Regimes
    print("⏳ Step 3: Running Regime Detector...")
    df_regimed = detector.detect_regimes(df_featured)
    
    # 5. Evaluate Signals
    print("⏳ Step 4: Running Signal Engine...")
    eval_funcs = {
        "AdaptiveTrendFollowing": sig_engine.evaluate_adaptive_trend,
        "PullbackContinuation": sig_engine.evaluate_pullback_continuation,
        "MeanReversion": sig_engine.evaluate_mean_reversion,
        "VolatilityBreakout": sig_engine.evaluate_volatility_breakout,
        "LondonSessionMomentum": sig_engine.evaluate_london_momentum,
        "AdaptiveMomentumPullback": sig_engine.evaluate_adaptive_momentum_pullback
    }
    
    if SELECTED_STRATEGY not in eval_funcs:
        print(f"❌ Unknown strategy name: {SELECTED_STRATEGY}")
        sys.exit(1)
        
    signals, config = eval_funcs[SELECTED_STRATEGY](df_regimed)
    
    # Filter out warmup data to evaluate performance only on target range
    start_dt = pd.to_datetime(START_DATE)
    is_in_range = df_regimed.index >= start_dt
    df_regimed_filtered = df_regimed[is_in_range]
    signals_filtered = signals[is_in_range]
    
    # 6. Execute Simulation (Risk Engine + Execution Engine)
    print("⏳ Step 5: Executing simulation (Risk Engine + bar-by-bar fills)...")
    trades = exec_engine.run_simulation(
        df=df_regimed_filtered,
        signals=signals_filtered,
        config=config,
        symbol=SYMBOL,
        pip_size=pip_size,
        strategy_name=SELECTED_STRATEGY
    )
    
    metrics = exec_engine.calculate_performance(trades, START_DATE, END_DATE)
    
    closed_trades = [t for t in trades if t['status'] == 'closed']
    
    # 7. Print Performance Summary
    print("\n" + "=" * 70)
    print(f"📈 {SELECTED_STRATEGY.upper()} PERFORMANCE SUMMARY (6-TIER)")
    print("=" * 70)
    print(f"Net Return:         {metrics['return_pct']:+.2f}%")
    print(f"Total Trades:       {metrics['trades']}")
    print(f"Win Rate:           {metrics['win_rate']:.1f}%")
    print(f"Profit Factor:      {metrics['pf']:.2f}")
    print(f"Max Drawdown:       {metrics['max_dd']:.2f}%")
    print(f"Sharpe Ratio:       {metrics['sharpe']:.2f}")
    print(f"🏆 Portfolio Score: {metrics['score']:+.4f}")
    print("-" * 70)
    
    # Print Sanity Warnings if any exist
    if metrics.get('sanity_warnings'):
        print("\n🚨 SYSTEM SANITY CHECK WARNINGS:")
        for w in metrics['sanity_warnings']:
            print(f"  {w}")
        print("-" * 70)
    
    # Print recent trade logs
    if closed_trades:
        print("\n📝 RECENT CLOSED TRADES LOG:")
        print(f"{'ID':<4} | {'Direction':<9} | {'Entry Price':<11} | {'Exit Price':<10} | {'PnL (Pips)':<10} | {'Exit Reason':<15}")
        print("-" * 70)
        for t in closed_trades[-10:]:
            pnl_str = f"{t['pnl_pips']:+.1f}"
            print(f"{t['trade_id']:<4} | {t['direction']:<9} | {t['entry_price']:<11.5f} | {t['exit_price']:<10.5f} | {pnl_str:<10} | {t['exit_reason']:<15}")
        print("=" * 70)
    else:
        print("\n⚠️ No trades executed in the target period.")


if __name__ == "__main__":
    main()
