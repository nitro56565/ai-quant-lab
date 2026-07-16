#!/usr/bin/env python3
"""
Quant Research Pipeline Runner
==============================
Modify the CONFIGURATION SETTINGS block below to select your symbols, 
timeframes, date ranges, and strategy portfolio, then run this file in your terminal:
    python3 run_pipeline.py
"""

import sys
import pandas as pd
import numpy as np

# =====================================================================
# ⚙️ CONFIGURATION SETTINGS (Edit these to modify your backtest run)
# =====================================================================
SYMBOL = "EURUSD"                # Forex pair to backtest (e.g. "EURUSD")
START_DATE = "2021-01-01"        # Start date (YYYY-MM-DD)
END_DATE = "2021-12-31"          # End date (YYYY-MM-DD)
INITIAL_CAPITAL = 10000.0        # Starting balance in USD

# Select strategies to combine into your portfolio.
# Available options:
#   - "AdaptiveTrendFollowing"  (Strategy 1: Pullback trend momentum)
#   - "PullbackContinuation"    (Strategy 2: RSI-filtered pullback continuation)
#   - "MeanReversion"           (Strategy 3: Quiet market Bollinger breakout)
#   - "VolatilityBreakout"      (Strategy 4: Bollinger squeeze / Donchian breakout)
#   - "LondonSessionMomentum"   (Strategy 5: London session opening momentum breakout)
SELECTED_STRATEGIES = [
    "LondonSessionMomentum",
    "PullbackContinuation"
]
# =====================================================================


def main():
    print("=" * 65)
    print("🚀 QUANT RESEARCH BACKTEST PIPELINE RUNNER")
    print("=" * 65)
    print(f"Target Symbol:     {SYMBOL}")
    print(f"Date Range:        {START_DATE} to {END_DATE}")
    print(f"Initial Capital:   ${INITIAL_CAPITAL:,.2f}")
    print(f"Active Portfolio:  {', '.join(SELECTED_STRATEGIES)}")
    print("-" * 65)

    # 1. Initialize data loaders & engines
    try:
        from data_loader import DataLoader
        from strategy_engine import StrategyEngine
        import strategy_engine as se
    except ImportError as e:
        print(f"❌ Import Error: Make sure you run this script in the root directory. Detail: {e}")
        sys.exit(1)

    loader = DataLoader()
    engine = StrategyEngine(loader)

    # Dictionary of strategy builders
    STRATEGIES_MAP = {
        "AdaptiveTrendFollowing": se.AdaptiveTrendFollowing,
        "PullbackContinuation": se.PullbackContinuation,
        "MeanReversion": se.MeanReversion,
        "VolatilityBreakout": se.VolatilityBreakout,
        "LondonSessionMomentum": se.LondonSessionMomentum
    }

    # Verify choices
    for s_name in SELECTED_STRATEGIES:
        if s_name not in STRATEGIES_MAP:
            print(f"❌ Error: Strategy '{s_name}' is not recognized.")
            print(f"Available options: {list(STRATEGIES_MAP.keys())}")
            sys.exit(1)

    # 2. Run backtest loop
    combined_trades = []
    pip_value = 10.0

    print("⏳ Executing strategy backtests on market data...")
    for s_name in SELECTED_STRATEGIES:
        strat_class = STRATEGIES_MAP[s_name]
        strategy = strat_class()
        
        try:
            _, trades = engine.run_backtest(strategy, SYMBOL, START_DATE, END_DATE)
            closed_trades = [t for t in trades if t['status'] == 'closed']
            for t in closed_trades:
                t_copy = t.copy()
                t_copy['strategy'] = s_name
                combined_trades.append(t_copy)
            print(f"  ✅ {s_name:25} -> Generated {len(closed_trades):3} trades.")
        except Exception as e:
            print(f"  ❌ Error executing {s_name}: {e}")

    if not combined_trades:
        print("\n⚠️ No trades were executed across the selected strategy portfolio.")
        sys.exit(0)

    # 3. Sort trades chronologically by exit time
    combined_trades_sorted = sorted(combined_trades, key=lambda x: x['exit_time'])
    
    # Re-index trade IDs
    for idx, t in enumerate(combined_trades_sorted):
        t['trade_id'] = idx + 1

    # 4. Calculate portfolio performance metrics
    current_equity = INITIAL_CAPITAL
    equity_curve = [{'time': START_DATE, 'equity': INITIAL_CAPITAL}]
    
    for t in combined_trades_sorted:
        pnl_usd = t['pnl_pips'] * pip_value
        current_equity += pnl_usd
        equity_curve.append({
            'time': t['exit_time'],
            'equity': current_equity
        })
        
    total_trades = len(combined_trades_sorted)
    wins = [t for t in combined_trades_sorted if t['pnl_pips'] > 0]
    losses = [t for t in combined_trades_sorted if t['pnl_pips'] <= 0]
    win_rate = (len(wins) / total_trades * 100.0)
    
    total_pips = sum(t['pnl_pips'] for t in combined_trades_sorted)
    avg_pips = (total_pips / total_trades)
    
    avg_win_pips = sum(t['pnl_pips'] for t in wins) / len(wins) if wins else 0.0
    avg_loss_pips = sum(t['pnl_pips'] for t in losses) / len(losses) if losses else 0.0
    risk_reward = avg_win_pips / abs(avg_loss_pips) if abs(avg_loss_pips) > 0 else 0.0
    expectancy = (win_rate / 100.0 * avg_win_pips) + ((1 - win_rate / 100.0) * avg_loss_pips)
    
    best_trade_pips = max(t['pnl_pips'] for t in combined_trades_sorted)
    worst_trade_pips = min(t['pnl_pips'] for t in combined_trades_sorted)
    
    # Win / loss streaks
    consec_wins = 0
    consec_losses = 0
    current_consec_wins = 0
    current_consec_losses = 0
    for t in combined_trades_sorted:
        pnl = t['pnl_pips']
        if pnl > 0:
            current_consec_wins += 1
            current_consec_losses = 0
            consec_wins = max(consec_wins, current_consec_wins)
        else:
            current_consec_losses += 1
            current_consec_wins = 0
            consec_losses = max(consec_losses, current_consec_losses)

    # Drawdown calculations
    peak = INITIAL_CAPITAL
    max_dd_pct = 0.0
    max_dd_usd = 0.0
    for pt in equity_curve:
        eq = pt['equity']
        if eq > peak:
            peak = eq
        dd_pct = ((peak - eq) / peak) * 100.0
        dd_usd = peak - eq
        max_dd_pct = max(max_dd_pct, dd_pct)
        max_dd_usd = max(max_dd_usd, dd_usd)

    profit_factor = sum(t['pnl_pips'] * pip_value for t in wins) / abs(sum(t['pnl_pips'] * pip_value for t in losses)) if losses else 1.0
    recovery_factor = (current_equity - INITIAL_CAPITAL) / max_dd_usd if max_dd_usd > 0 else 0.0
    
    # CAGR
    start_dt = pd.to_datetime(START_DATE)
    end_dt = pd.to_datetime(END_DATE)
    total_days = (end_dt - start_dt).days
    years_duration = total_days / 365.25 if total_days > 0 else 1.0
    cagr = (((current_equity / INITIAL_CAPITAL) ** (1.0 / years_duration)) - 1.0) * 100.0 if current_equity > 0 else -100.0
    
    # Sharpe Ratio (daily returns)
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
                curr_eq += t['pnl_pips'] * pip_value
        daily_equity[day_str] = curr_eq
        curr_dt += pd.Timedelta(days=1)
        
    eq_series = pd.Series(daily_equity)
    pct_returns = eq_series.pct_change().dropna()
    sharpe = (pct_returns.mean() / pct_returns.std() * (252 ** 0.5)) if not pct_returns.empty and pct_returns.std() > 0 else 0.0

    # Objective Score
    score = 0.35 * cagr + 0.25 * sharpe + 0.20 * profit_factor - 0.20 * max_dd_pct

    # Monthly Performance Detailed Table
    monthly_performance = []
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for m in range(1, 13):
        m_trades = [t for t in combined_trades_sorted if t['exit_time'].month == m]
        if not m_trades:
            monthly_performance.append((month_names[m-1], 0, 0.0, 0.0, 1.0, 0.0))
            continue
        m_wins = [t for t in m_trades if t['pnl_pips'] > 0]
        m_losses = [t for t in m_trades if t['pnl_pips'] <= 0]
        m_wr = len(m_wins) / len(m_trades) * 100.0
        m_profit = sum(t['pnl_pips'] for t in m_trades)
        
        m_gp = sum(t['pnl_pips'] for t in m_wins)
        m_gl = abs(sum(t['pnl_pips'] for t in m_losses))
        m_pf = m_gp / m_gl if m_gl > 0 else (m_gp if m_gp > 0 else 1.0)
        
        # Monthly DD
        m_eq = 10000.0
        m_curve = [m_eq]
        for t in m_trades:
            m_eq += t['pnl_pips'] * pip_value
            m_curve.append(m_eq)
        m_peak = 10000.0
        m_dd = 0.0
        for val in m_curve:
            m_peak = max(m_peak, val)
            dd_pct = (m_peak - val) / m_peak * 100.0
            m_dd = max(m_dd, dd_pct)
            
        monthly_performance.append((month_names[m-1], len(m_trades), m_profit, m_wr, m_pf, m_dd))

    # 5. Output Results Dashboard
    print("\n" + "=" * 65)
    print("📈 PORTFOLIO BACKTEST SUMMARY REPORT")
    print("=" * 65)
    print(f"Net Return:         +${(current_equity - INITIAL_CAPITAL):,.2f} ({((current_equity - INITIAL_CAPITAL)/INITIAL_CAPITAL * 100):+.2f}%)")
    print(f"Final Account Val:  ${current_equity:,.2f}")
    print(f"Total Trades:       {total_trades}")
    print(f"Win Rate:           {win_rate:.2f}%")
    print(f"Profit Factor:      {profit_factor:.2f}")
    print(f"Max Drawdown (Pct): {max_dd_pct:.2f}%")
    print(f"Max Drawdown (USD): ${max_dd_usd:,.2f}")
    print(f"Sharpe Ratio:       {sharpe:.2f}")
    print(f"CAGR:               {cagr:.2f}%")
    print(f"Recovery Factor:    {recovery_factor:.2f}")
    print("-" * 65)
    print(f"🏆 PORTFOLIO SCORE:  {score:+.4f}")
    print(f"   (Formula: 0.35*CAGR + 0.25*Sharpe + 0.20*PF - 0.20*MaxDD)")
    print("=" * 65)

    print("\n📊 ADVANCED PERFORMANCE METRICS")
    print("-" * 65)
    print(f"Average Win / Loss:  +{avg_win_pips:+.1f} / {avg_loss_pips:+.1f} pips")
    print(f"Risk-Reward Ratio:   1:{risk_reward:.2f}")
    print(f"Expectancy:          {expectancy:+.2f} pips/trade")
    print(f"Max Win / Max Loss:  {best_trade_pips:+.1f} / {worst_trade_pips:+.1f} pips")
    print(f"Win/Loss Streaks:    {consec_wins} wins / {consec_losses} losses")
    print("-" * 65)

    print("\n📅 MONTHLY PERFORMANCE MATRIX")
    print("-" * 65)
    print("Month | Trades | Profit (Pips) | Win Rate | PF   | DD")
    print("-" * 65)
    for m_data in monthly_performance:
        name, trd, prof, wr, pf_m, dd_m = m_data
        print(f"{name:5} | {trd:6} | {prof:+13.2f} | {wr:7.1f}% | {pf_m:4.2f} | {dd_m:3.1f}%")
    print("-" * 65)


if __name__ == "__main__":
    main()
