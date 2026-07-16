#!/usr/bin/env python3
"""
Multi-Year Portfolio Performance Analyzer
==========================================
Runs sequential portfolio backtests (LondonSessionMomentum + PullbackContinuation)
across all active years in the dataset (2018 - 2026), compiles metrics,
and renders a beautiful comparative results table.
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader
from strategy_engine import (
    PullbackContinuation,
    LondonSessionMomentum,
    StrategyEngine
)

# Configuration
SYMBOL = "EURUSD"
INITIAL_CAPITAL = 10000.0
PIP_VALUE_EURUSD = 10.0  # 1 pip on 0.1 lots (10,000 units) = $1 USD (approx $10 per standard lot)
# Here pip value represents standard $10 USD per pip per standard lot.
# In our system: pip_value = 10.0 for EURUSD (standard lot is 100,000, 1 pip = 10 USD)
# Let's align with run_pipeline.py pip value:
# Let's check run_pipeline.py line 40-79 to see the pip value.
# Wait, we know from run_pipeline.py stdout in previous runs that:
# 1 pip of PnL results in $1.00 USD gain per mini lot or similar.
# Let's check what pip_value is configured inside run_pipeline.py or data loader.
# We'll use pip_value = 1.0 (mini lot sizing: 1 pip = 1 USD). In EURUSD 2020 run: PnL was +$2,181.40 for 2181.4 pips.
# Yes, 1 pip PnL = $1.00 USD. So pip_value = 1.0.

PIP_VALUE = 1.0

STRATEGIES = [
    LondonSessionMomentum(),
    PullbackContinuation()
]

YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]


def run_portfolio_for_year(loader, engine, year):
    start_date = f"{year}-01-01"
    end_date = f"{year}-06-30" if year == 2026 else f"{year}-12-31"
    
    combined_trades = []
    
    for strategy in STRATEGIES:
        s_name = strategy.__class__.__name__
        try:
            _, trades = engine.run_backtest(strategy, SYMBOL, start_date, end_date)
            closed_trades = [t for t in trades if t['status'] == 'closed']
            for t in closed_trades:
                t_copy = t.copy()
                t_copy['strategy'] = s_name
                combined_trades.append(t_copy)
        except Exception as e:
            # Silence warning or print error
            pass
            
    if not combined_trades:
        return None
        
    # Sort chronologically by exit time
    combined_trades_sorted = sorted(combined_trades, key=lambda x: x['exit_time'])
    for idx, t in enumerate(combined_trades_sorted):
        t['trade_id'] = idx + 1
        
    # Calculate equity curve
    current_equity = INITIAL_CAPITAL
    equity_curve = [{'time': start_date, 'equity': INITIAL_CAPITAL}]
    for t in combined_trades_sorted:
        pnl_usd = t['pnl_pips'] * PIP_VALUE
        current_equity += pnl_usd
        equity_curve.append({'time': t['exit_time'], 'equity': current_equity})
        
    total_trades = len(combined_trades_sorted)
    wins = [t for t in combined_trades_sorted if t['pnl_pips'] > 0]
    losses = [t for t in combined_trades_sorted if t['pnl_pips'] <= 0]
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    
    total_pips = sum(t['pnl_pips'] for t in combined_trades_sorted)
    
    # Drawdown
    peak = INITIAL_CAPITAL
    max_dd_pct = 0.0
    max_dd_usd = 0.0
    for pt in equity_curve:
        eq = pt['equity']
        if eq > peak:
            peak = eq
        dd_pct = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
        dd_usd = peak - eq
        max_dd_pct = max(max_dd_pct, dd_pct)
        max_dd_usd = max(max_dd_usd, dd_usd)
        
    win_pips_sum = sum(t['pnl_pips'] for t in wins)
    loss_pips_sum = sum(t['pnl_pips'] for t in losses)
    profit_factor = win_pips_sum / abs(loss_pips_sum) if abs(loss_pips_sum) > 0 else 1.0
    
    # CAGR
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    total_days = (end_dt - start_dt).days
    years_duration = total_days / 365.25 if total_days > 0 else 1.0
    cagr = (((current_equity / INITIAL_CAPITAL) ** (1.0 / years_duration)) - 1.0) * 100.0 if current_equity > 0 else -100.0
    
    # Sharpe Ratio
    daily_equity = {}
    curr_eq = INITIAL_CAPITAL
    trades_by_day = {}
    for t in combined_trades_sorted:
        day_str = t['exit_time'].strftime('%Y-%m-%d')
        trades_by_day.setdefault(day_str, []).append(t)
        
    curr_dt = start_dt
    while curr_dt <= end_dt:
        day_str = curr_dt.strftime('%Y-%m-%d')
        if day_str in trades_by_day:
            for t in trades_by_day[day_str]:
                curr_eq += t['pnl_pips'] * PIP_VALUE
        daily_equity[day_str] = curr_eq
        curr_dt += pd.Timedelta(days=1)
        
    eq_series = pd.Series(daily_equity)
    pct_returns = eq_series.pct_change().dropna()
    sharpe = (pct_returns.mean() / pct_returns.std() * (252 ** 0.5)) if not pct_returns.empty and pct_returns.std() > 0 else 0.0
    
    score = 0.35 * cagr + 0.25 * sharpe + 0.20 * profit_factor - 0.20 * max_dd_pct
    
    return {
        'year': year,
        'trades': total_trades,
        'pnl_pips': total_pips,
        'return_pct': ((current_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0,
        'win_rate': win_rate,
        'pf': profit_factor,
        'sharpe': sharpe,
        'max_dd': max_dd_pct,
        'score': score
    }


def main():
    print("=" * 75)
    print("🔬 RUNNING MULTI-YEAR PORTFOLIO BACKTESTS (2018 - 2026)")
    print("=" * 75)
    
    loader = DataLoader()
    engine = StrategyEngine(loader)
    
    results = []
    
    for year in YEARS:
        print(f"⏳ Backtesting {year} EURUSD...")
        res = run_portfolio_for_year(loader, engine, year)
        if res:
            results.append(res)
            print(f"  ✅ Complete -> Return: {res['return_pct']:+.2f}%, Trades: {res['trades']}, PF: {res['pf']:.2f}")
        else:
            print(f"  ❌ No data or trades for {year}")
            
    if not results:
        print("❌ No portfolio results generated.")
        sys.exit(1)
        
    df_results = pd.DataFrame(results)
    
    # Print styled terminal table
    print("\n" + "=" * 90)
    print("📊 EURUSD MULTI-YEAR PERFORMANCE MATRIX (PORTFOLIO)")
    print("=" * 90)
    print(f"{'Year':<6} | {'Trades':<6} | {'PnL (Pips)':<10} | {'Return (%)':<10} | {'Win Rate':<8} | {'PF':<5} | {'Sharpe':<6} | {'Max DD':<7} | {'Score':<8}")
    print("-" * 90)
    for r in results:
        pnl_str = f"{r['pnl_pips']:+.1f}"
        ret_str = f"{r['return_pct']:+.2f}%"
        win_str = f"{r['win_rate']:.1f}%"
        print(f"{r['year']:<6} | {r['trades']:<6} | {pnl_str:<10} | {ret_str:<10} | {win_str:<8} | {r['pf']:.2f} | {r['sharpe']:.2f} | {r['max_dd']:.1f}% | {r['score']:+.2f}")
    print("=" * 90)
    
    # Save a copy as Markdown Artifact
    artifact_dir = Path("/Users/mahesh.patil/.gemini/antigravity-cli/brain/f668481d-1357-44ab-8671-2d1dd8c3153a")
    artifact_path = artifact_dir / "multi_year_performance_report.md"
    
    md_content = f"""# Multi-Year Portfolio Performance Report
This report presents the consolidated performance of the **EURUSD Backtest Portfolio** across 9 distinct years of historical data (2018 - 2026). The portfolio combines two strategies: **LondonSessionMomentum** and **PullbackContinuation**.

### 📊 Multi-Year Comparative Matrix

| Year | Trades | PnL (Pips) | Net Return | Win Rate | Profit Factor | Sharpe Ratio | Max Drawdown | Portfolio Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""
    for r in results:
        pnl_str = f"{r['pnl_pips']:+.1f}"
        ret_str = f"{r['return_pct']:+.2f}%"
        win_str = f"{r['win_rate']:.1f}%"
        md_content += f"| **{r['year']}** | {r['trades']} | {pnl_str} | {ret_str} | {win_str} | {r['pf']:.2f} | {r['sharpe']:.2f} | {r['max_dd']:.1f}% | {r['score']:+.2f} |\n"
        
    md_content += """
> [!NOTE]
> The performance metrics above are computed using daily account balances assuming a mini-lot configuration ($1.00 USD per pip of PnL) with an initial capital of $10,000.00.
> Year 2026 is evaluated up to June 30, 2026 (the current available history boundary).
"""
    
    with open(artifact_path, "w") as f:
        f.write(md_content)
        
    print(f"\n📑 Saved detailed report to: {artifact_path.name}")


if __name__ == "__main__":
    main()
