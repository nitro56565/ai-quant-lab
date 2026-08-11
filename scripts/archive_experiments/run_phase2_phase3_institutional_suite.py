import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.WARNING)

def calculate_metrics(closed_trades, initial_capital=10000.0, start_date="2018-01-01", end_date="2025-12-31"):
    if not closed_trades:
        return {'trades': 0, 'win_rate': 0.0, 'expectancy_pips': 0.0, 'net_pnl': 0.0, 'return_pct': 0.0, 'pf': 1.0, 'max_dd': 0.0, 'sharpe': 0.0}

    df_t = pd.DataFrame(closed_trades)
    n_trades = len(df_t)
    wins = df_t[df_t['pnl_pips'] > 0]
    losses = df_t[df_t['pnl_pips'] <= 0]

    win_rate = (len(wins) / n_trades) * 100.0
    expectancy_pips = df_t['pnl_pips'].mean()
    net_pnl = df_t['pnl_usd'].sum()
    return_pct = (net_pnl / initial_capital) * 100.0

    win_cash = wins['pnl_usd'].sum() if len(wins) > 0 else 0.0
    loss_cash = abs(losses['pnl_usd'].sum()) if len(losses) > 0 else 0.0
    pf = win_cash / loss_cash if loss_cash > 0 else 1.0

    equity = initial_capital + df_t['pnl_usd'].cumsum()
    peak = equity.cummax()
    dd = (peak - equity) / peak * 100.0
    max_dd = dd.max() if len(dd) > 0 else 0.0

    # Daily Sharpe
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    daily_equity = {}
    curr_eq = initial_capital
    trades_by_day = {}
    
    for _, t in df_t.iterrows():
        day_str = pd.to_datetime(t['exit_time']).strftime('%Y-%m-%d')
        trades_by_day.setdefault(day_str, []).append(t)
        
    curr_dt = start_dt
    while curr_dt <= end_dt:
        day_str = curr_dt.strftime('%Y-%m-%d')
        if day_str in trades_by_day:
            for t in trades_by_day[day_str]:
                curr_eq += t['pnl_usd']
        daily_equity[day_str] = curr_eq
        curr_dt += pd.Timedelta(days=1)

    eq_series = pd.Series(daily_equity)
    pct_returns = eq_series.pct_change().dropna()
    sharpe = (pct_returns.mean() / pct_returns.std() * np.sqrt(252)) if not pct_returns.empty and pct_returns.std() > 0 else 0.0

    return {
        'trades': n_trades,
        'win_rate': round(win_rate, 1),
        'expectancy_pips': round(expectancy_pips, 2),
        'net_pnl': round(net_pnl, 2),
        'return_pct': round(return_pct, 2),
        'pf': round(pf, 2),
        'max_dd': round(max_dd, 2),
        'sharpe': round(sharpe, 2)
    }

def run_monte_carlo_resampling(closed_trades, initial_capital=10000.0, n_simulations=1000):
    if not closed_trades:
        return {'median_return': 0.0, 'p5_return': 0.0, 'p95_return': 0.0, 'median_dd': 0.0, 'p95_worst_dd': 0.0}

    pnls_usd = np.array([t['pnl_usd'] for t in closed_trades])
    sim_returns = []
    sim_max_dds = []

    np.random.seed(42)

    for i in range(n_simulations):
        boot_indices = np.random.choice(len(pnls_usd), size=len(pnls_usd), replace=True)
        boot_usd = pnls_usd[boot_indices]
        noise_usd = np.random.normal(0.0, 5.0, size=len(boot_usd))  # $5 = 0.5 pips
        noisy_usd = boot_usd + noise_usd

        equity = initial_capital + np.cumsum(noisy_usd)
        net_ret = ((equity[-1] - initial_capital) / initial_capital) * 100.0
        
        pk = np.maximum.accumulate(equity)
        dd = (pk - equity) / pk * 100.0
        max_dd = np.max(dd)

        sim_returns.append(net_ret)
        sim_max_dds.append(max_dd)

    return {
        'median_return': round(float(np.median(sim_returns)), 2),
        'p5_return': round(float(np.percentile(sim_returns, 5)), 2),
        'p95_return': round(float(np.percentile(sim_returns, 95)), 2),
        'median_dd': round(float(np.median(sim_max_dds)), 2),
        'p95_worst_dd': round(float(np.percentile(sim_max_dds, 95)), 2)
    }

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — PHASE 2 & PHASE 3 INSTITUTIONAL RESEARCH SUITE (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # -------------------------------------------------------------------------
    # PHASE 1: FROZEN STRATEGY PREPARATION
    # -------------------------------------------------------------------------
    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    signals = np.full(len(df_signals), None, dtype=object)
    if 'signal' in df_signals.columns:
        signals = df_signals['signal'].values

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    # -------------------------------------------------------------------------
    # PHASE 2: CONTROLLED A/B COMPONENT ABLATION
    # -------------------------------------------------------------------------
    print("=================================================================================")
    print("  🧪 PHASE 2: CONTROLLED A/B COMPONENT ABLATION MATRIX")
    print("=================================================================================")

    # Baseline (Fixed Risk 0.50%, Fixed SL 2.0x ATR, Fixed TP 2.0R (tp_mult=4.0), No Trail)
    df_base = df_signals.copy()
    df_base['target_risk_pct'] = 0.50
    config_base = {'sl_multiplier': 2.0, 'tp_multiplier': 4.0, 'trail_multiplier': None}
    trades_base = exec_engine.run_simulation(df=df_base, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='Baseline')
    closed_base = [t for t in trades_base if t['status'] == 'closed']
    m_base = calculate_metrics(closed_base)

    # 1. Component 1: TP Scaling Only (Target 2.4R -> tp_mult = 4.8 vs Fixed Baseline 2.0R -> tp_mult = 4.0)
    config_exp1 = {'sl_multiplier': 2.0, 'tp_multiplier': 4.8, 'trail_multiplier': None}
    trades_exp1 = exec_engine.run_simulation(df=df_base, signals=signals, config=config_exp1, symbol=symbol, pip_size=pip_size, strategy_name='TPScaling')
    closed_exp1 = [t for t in trades_exp1 if t['status'] == 'closed']
    m_exp1 = calculate_metrics(closed_exp1)

    # 2. Volatility-Based Sizing Only (Risk 0.25% - 1.00% based on ATR percentile)
    df_exp2 = df_signals.copy()
    vol_rank = df_signals['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_signals.columns else np.full(len(df_signals), 50.0)
    risk_vol = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
    df_exp2['target_risk_pct'] = risk_vol
    trades_exp2 = exec_engine.run_simulation(df=df_exp2, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='VolSizing')
    closed_exp2 = [t for t in trades_exp2 if t['status'] == 'closed']
    m_exp2 = calculate_metrics(closed_exp2)

    # 3. Trailing Stop Only (ATR 3.0 Trail)
    config_exp3 = {'sl_multiplier': 2.0, 'tp_multiplier': 4.0, 'trail_multiplier': 3.0}
    trades_exp3 = exec_engine.run_simulation(df=df_base, signals=signals, config=config_exp3, symbol=symbol, pip_size=pip_size, strategy_name='TrailingStop')
    closed_exp3 = [t for t in trades_exp3 if t['status'] == 'closed']
    m_exp3 = calculate_metrics(closed_exp3)

    # 4. Time Exit Only (Dynamic Volatility Horizon)
    trades_exp4 = exec_engine.run_simulation(df=df_base, signals=signals, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='TimeExit')
    closed_exp4 = [t for t in trades_exp4 if t['status'] == 'closed']
    m_exp4 = calculate_metrics(closed_exp4)

    # 5. Session Filter Only (Skip NY Overlap 13:00-16:00 UTC)
    sig_exp5 = signals.copy()
    for i in range(len(df_signals)):
        if df_signals.index[i].hour in [13, 14, 15, 16]:
            sig_exp5[i] = None
    trades_exp5 = exec_engine.run_simulation(df=df_base, signals=sig_exp5, config=config_base, symbol=symbol, pip_size=pip_size, strategy_name='SessionFilter')
    closed_exp5 = [t for t in trades_exp5 if t['status'] == 'closed']
    m_exp5 = calculate_metrics(closed_exp5)

    print(f"{'Execution Component':<32} | {'PF':<6} | {'Max DD (%)':<10} | {'Return (%)':<12} | {'Exp (Pips)':<12} | {'Sharpe':<8} | {'Winner?':<8}")
    print("-" * 105)

    exp_matrix = [
        ("Baseline (All Fixed)", m_base, "-"),
        ("Component 1: TP Scaling (2.4R)", m_exp1, "YES" if m_exp1['pf'] > m_base['pf'] else "NO"),
        ("Component 2: Volatility Bet Sizing", m_exp2, "YES" if m_exp2['pf'] > m_base['pf'] else "NO"),
        ("Component 3: ATR Trailing Stop", m_exp3, "YES" if m_exp3['pf'] > m_base['pf'] else "NO"),
        ("Component 4: Dynamic Time Exit", m_exp4, "YES" if m_exp4['pf'] >= m_base['pf'] else "NO"),
        ("Component 5: Session Filter (No NY Chop)", m_exp5, "YES" if m_exp5['pf'] > m_base['pf'] else "NO"),
    ]

    for name, m, win in exp_matrix:
        print(f"{name:<32} | {m['pf']:<6.2f} | {m['max_dd']:<10.2f} | {m['return_pct']:<+11.2f}% | {m['expectancy_pips']:<+11.2f} | {m['sharpe']:<8.2f} | {win:<8}")

    print("---------------------------------------------------------------------------------\n")

    # -------------------------------------------------------------------------
    # PHASE 3: REALISTIC MICROSTRUCTURE & MONTE CARLO STRESS TESTING
    # -------------------------------------------------------------------------
    print("=================================================================================")
    print("  🔬 PHASE 3: REALISTIC MICROSTRUCTURE & MONTE CARLO STRESS TESTING")
    print("=================================================================================")

    # Real-World Microstructure Friction (Variable Spreads 1.0 to 4.0 pips + Random Slippage)
    closed_realistic = [t.copy() for t in closed_base]
    np.random.seed(42)

    for t in closed_realistic:
        entry_h = pd.to_datetime(t['entry_time']).hour
        # Variable spread model: 1.0 pip quiet, 2.5 pips NY overlap, 4.0 pips rollover (21-23 UTC)
        spread_drag = 4.0 if entry_h in [21, 22, 23] else (2.5 if entry_h in [13, 14, 15, 16] else 1.0)
        # Random slippage half-normal distribution (0.0 to 1.5 pips)
        slippage = abs(np.random.normal(0.2, 0.4))
        
        extra_drag = (spread_drag - 1.5) + slippage
        t['pnl_pips'] -= extra_drag
        t['pnl_usd'] = t['pnl_pips'] * t['size'] * 10.0

    m_real = calculate_metrics(closed_realistic)
    mc_results = run_monte_carlo_resampling(closed_realistic, initial_capital=10000.0, n_simulations=1000)

    print(f"{'Simulation Environment':<35} | {'PF':<6} | {'Max DD (%)':<10} | {'Return (%)':<12} | {'Win Rate':<10} | {'Avg Pips':<10}")
    print("-" * 95)
    print(f"{'Ideal Baseline (Fixed 1.5 Cost)':<35} | {m_base['pf']:<6.2f} | {m_base['max_dd']:<10.2f} | {m_base['return_pct']:<+11.2f}% | {m_base['win_rate']:<9.1f}% | {m_base['expectancy_pips']:<+9.2f}")
    print(f"{'Realistic (Variable Spread+Slippage)':<35} | {m_real['pf']:<6.2f} | {m_real['max_dd']:<10.2f} | {m_real['return_pct']:<+11.2f}% | {m_real['win_rate']:<9.1f}% | {m_real['expectancy_pips']:<+9.2f}")
    print("-" * 95 + "\n")

    print("=== 🎲 MONTE CARLO RESAMPLING STRESS TEST (1,000 RUNS) ===")
    print(f"   • Median Expected Net Return:         {mc_results['median_return']:+.2f}%")
    print(f"   • 95% Confidence Interval (Net Return): [{mc_results['p5_return']:+.2f}%, {mc_results['p95_return']:+.2f}%]")
    print(f"   • Median Peak-to-Trough Drawdown:      {mc_results['median_dd']:.2f}%")
    print(f"   • 95th Percentile Worst-Case Drawdown: {mc_results['p95_worst_dd']:.2f}%")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
