import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import json
import logging

from data_loader import DataLoader
from strategy_engine.volatility_breakout import VolatilityBreakout
from research_engine.feature_matrix import FeatureMatrixBuilder
from market_state_engine.state_calculator import MarketStateEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MarketStateEngineBacktest")

def main():
    print("=================================================================================")
    print("  🤖 PHASE 1: QUANTITATIVE MARKET STATE ENGINE (AI 2) BACKTEST (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # 1. Primary Strategy Candidates: Volatility Breakout
    vb = VolatilityBreakout()
    df_primary = vb.prepare_data(loader, symbol, "2014-01-01", end_date)

    # 2. Build Quantitative Feature Matrix
    builder = FeatureMatrixBuilder()
    df_feat = builder.build(df_primary)

    # 3. Market State Engine Calculations
    state_engine = MarketStateEngine()
    
    n_rows = len(df_feat)
    trend_strengths = np.zeros(n_rows)
    trend_qualities = np.zeros(n_rows)
    volatility_scores = np.zeros(n_rows)
    liquidity_scores = np.zeros(n_rows)

    for i in range(n_rows):
        state = state_engine.compute_market_state(df_feat, i)
        trend_strengths[i] = state['trend_strength']
        trend_qualities[i] = state['trend_quality']
        volatility_scores[i] = state['volatility_score']
        liquidity_scores[i] = state['liquidity_score']

    df_feat['state_trend_strength'] = trend_strengths
    df_feat['state_trend_quality'] = trend_qualities
    df_feat['state_volatility'] = volatility_scores
    df_feat['state_liquidity'] = liquidity_scores

    dates = df_feat.index
    years = dates.year
    candidate_mask = (df_feat['entry_signal'] == True)

    print("=== QUANTITATIVE MARKET STATE SCORES BY YEAR (2018 - 2025) ===\n")
    print(f"{'Year':<6} | {'Trend Strength':<15} | {'Trend Quality':<15} | {'Volatility Score':<18} | {'Liquidity Score':<15}")
    print("-" * 75)

    for yr in range(2018, 2026):
        yr_mask = (years == yr)
        if not yr_mask.any():
            continue
        ts_mean = df_feat.loc[yr_mask, 'state_trend_strength'].mean()
        tq_mean = df_feat.loc[yr_mask, 'state_trend_quality'].mean()
        vs_mean = df_feat.loc[yr_mask, 'state_volatility'].mean()
        ls_mean = df_feat.loc[yr_mask, 'state_liquidity'].mean()
        print(f"{yr:<6} | {ts_mean:<15.1f} | {tq_mean:<15.1f} | {vs_mean:<18.1f} | {ls_mean:<15.1f}")

    print("-" * 75 + "\n")

    # 4. Generate Strategy Signals Filtered by Quantitative Market State Engine
    # Filter Rule:
    # - Candidate Breakout Triggered
    # - Trend Strength >= 35.0 AND Trend Quality >= 40.0 (Filter out weak/messy trends)
    # - Liquidity Score >= 35.0 (Filter out illiquid bars)
    df_feat['signal'] = None
    
    market_state_ok = (
        (df_feat['state_trend_strength'] >= 35.0) &
        (df_feat['state_trend_quality'] >= 40.0) &
        (df_feat['state_liquidity'] >= 35.0)
    )
    
    active_mask = (years >= 2018) & (years <= 2025) & candidate_mask & market_state_ok
    df_feat.loc[active_mask, 'signal'] = 'BUY'

    signals = df_feat['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    # Dynamic Bounded Execution: Higher Volatility -> Stretch Target 3.0R; Normal -> 2.0R
    config = {
        'sl_multiplier': 1.5,
        'tp_multiplier': None,
        'trail_multiplier': 3.0
    }

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    
    # Filter to test range for simulation
    is_test = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_test = df_feat[is_test]
    signals_test = signals[is_test]

    trades = exec_engine.run_simulation(
        df=df_test,
        signals=signals_test,
        config=config,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name='MarketStateFilteredBreakout'
    )

    closed = [t for t in trades if t['status'] == 'closed']
    df_trades = pd.DataFrame(closed)
    df_trades['year'] = pd.to_datetime(df_trades['exit_time']).dt.year

    print("=== YEARLY PERFORMANCE BREAKDOWN: MARKET STATE ENGINE (2018 - 2025) ===\n")
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

if __name__ == "__main__":
    main()
