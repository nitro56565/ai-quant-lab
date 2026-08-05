import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import itertools
import logging

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.WARNING)

def calculate_full_metrics(closed_trades, initial_capital=10000.0):
    if not closed_trades:
        return {'trades': 0, 'win_rate': 0.0, 'expectancy_pips': 0.0, 'net_pnl': 0.0, 'return_pct': 0.0, 'pf': 1.0, 'max_dd': 0.0, 'sharpe': 0.0, 'recovery_factor': 0.0, 'yearly_returns': {}}

    df_t = pd.DataFrame(closed_trades)
    df_t['year'] = pd.to_datetime(df_t['exit_time']).dt.year
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

    # Calculate Drawdown
    equity = initial_capital + df_t['pnl_usd'].cumsum()
    peak = equity.cummax()
    dd = (peak - equity) / peak * 100.0
    max_dd = dd.max() if len(dd) > 0 else 0.0
    max_dd_usd = (peak - equity).max()
    recovery_factor = net_pnl / max_dd_usd if max_dd_usd > 0 else 0.0

    # Calculate Sharpe Ratio
    returns = df_t['pnl_usd'] / initial_capital
    std_ret = returns.std()
    sharpe = (returns.mean() / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

    # Yearly breakdown
    yearly_returns = {}
    curr_cap = initial_capital
    for yr in range(2018, 2026):
        yr_t = df_t[df_t['year'] == yr]
        yr_pnl = yr_t['pnl_usd'].sum() if len(yr_t) > 0 else 0.0
        yr_ret = (yr_pnl / curr_cap) * 100.0
        curr_cap += yr_pnl
        yearly_returns[yr] = round(yr_ret, 2)

    return {
        'trades': n_trades,
        'win_rate': round(win_rate, 1),
        'expectancy_pips': round(expectancy_pips, 2),
        'net_pnl': round(net_pnl, 2),
        'return_pct': round(return_pct, 2),
        'pf': round(pf, 2),
        'max_dd': round(max_dd, 2),
        'sharpe': round(sharpe, 2),
        'recovery_factor': round(recovery_factor, 2),
        'yearly_returns': yearly_returns
    }

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — PERMUTATION & COMBINATION OPTIMIZATION ENGINE (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    ctx_engine = ExecutionContextEngine(rolling_window=1000)
    df_context = ctx_engine.prepare_rolling_ranks(df_signals)

    n_rows = len(df_context)
    signals = df_context['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    trend_alignments = np.zeros(n_rows)
    volatility_states = np.zeros(n_rows)

    for i in range(n_rows):
        sig = signals[i]
        trade_dir = sig if sig in ['BUY', 'SELL'] else 'BUY'
        ctx = ctx_engine.compute_context(df_context, i, trade_dir)
        trend_alignments[i] = ctx['trend_alignment']
        volatility_states[i] = ctx['volatility_state']

    df_context['trend_alignment'] = trend_alignments
    df_context['volatility_state'] = volatility_states

    # Define Permutation Parameter Grid
    tp_options = [
        ("Fixed_2.0R", lambda align, vol: 2.0),
        ("Fixed_2.4R", lambda align, vol: 2.4),
        ("Step_2.0_to_2.8R", lambda align, vol: 2.8 if align >= 80 and vol >= 70 else (2.6 if align >= 70 else (2.4 if align >= 50 else 2.0))),
        ("Aggressive_2.0_to_3.2R", lambda align, vol: 3.2 if align >= 80 and vol >= 70 else (2.8 if align >= 70 else (2.4 if align >= 50 else 2.0)))
    ]

    risk_options = [
        ("Fixed_0.50%", lambda align, vol: 0.50),
        ("Fixed_0.75%", lambda align, vol: 0.75),
        ("Adaptive_0.375_0.625%", lambda align, vol: 0.625 if align >= 70 and vol >= 70 else (0.375 if align < 40 else 0.50)),
        ("Vol_Weighted_0.25_1.00%", lambda align, vol: 1.00 if vol >= 80 else (0.75 if vol >= 60 else (0.50 if vol >= 40 else 0.25)))
    ]

    trail_options = [
        ("Trail_Off", False),
        ("Trail_HighContext", True)
    ]

    session_options = [
        ("All_Sessions", True),
        ("Skip_NY_Overlap", False)
    ]

    permutations = list(itertools.product(tp_options, risk_options, trail_options, session_options))
    total_perms = len(permutations)

    print(f"✅ Generated {total_perms} Permutation & Combination Configurations to Evaluate.\n")

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)

    results = []

    for idx, (tp_opt, risk_opt, trail_opt, session_opt) in enumerate(permutations):
        tp_name, tp_fn = tp_opt
        risk_name, risk_fn = risk_opt
        trail_name, trail_flag = trail_opt
        session_name, session_flag = session_opt

        df_perm = df_context.copy()
        
        # Apply risk & session filters
        risk_array = np.zeros(n_rows)
        sig_array = signals.copy()

        for i in range(n_rows):
            align = trend_alignments[i]
            vol = volatility_states[i]
            risk_array[i] = risk_fn(align, vol)
            
            # Session filter
            if not session_flag and df_perm.index[i].hour in [13, 14, 15, 16]:
                sig_array[i] = None

        df_perm['target_risk_pct'] = risk_array

        config = {
            'sl_multiplier': strat.sl_atr_multiplier,
            'tp_multiplier': None,
            'trail_multiplier': 3.0 if trail_flag else None
        }

        trades = exec_engine.run_simulation(
            df=df_perm,
            signals=sig_array,
            config=config,
            symbol=symbol,
            pip_size=pip_size,
            strategy_name=f'Perm_{idx}'
        )

        closed = [t for t in trades if t['status'] == 'closed']
        df_closed = pd.DataFrame(closed)
        
        if len(closed) > 0:
            # Adjust TP gain based on tp_fn
            entry_idx = [df_perm.index.get_loc(t['entry_time']) for t in closed]
            align_sub = trend_alignments[entry_idx]
            vol_sub = volatility_states[entry_idx]
            
            tp_mults = np.array([tp_fn(align_sub[k], vol_sub[k]) / 2.0 for k in range(len(closed))])
            df_closed['pnl_pips'] = np.where(df_closed['pnl_pips'] > 0, df_closed['pnl_pips'] * tp_mults, df_closed['pnl_pips'])
            df_closed['pnl_usd'] = np.where(df_closed['pnl_usd'] > 0, df_closed['pnl_usd'] * tp_mults, df_closed['pnl_usd'])
            closed_adj = df_closed.to_dict('records')
        else:
            closed_adj = []

        m = calculate_full_metrics(closed_adj)
        
        # Composite Quality Score
        comp_score = m['pf'] * m['recovery_factor'] * (1.0 - m['max_dd'] / 100.0)

        results.append({
            'perm_id': idx + 1,
            'tp_config': tp_name,
            'risk_config': risk_name,
            'trail_config': trail_name,
            'session_config': session_name,
            'trades': m['trades'],
            'win_rate': m['win_rate'],
            'net_return': m['return_pct'],
            'pf': m['pf'],
            'max_dd': m['max_dd'],
            'sharpe': m['sharpe'],
            'recovery_factor': m['recovery_factor'],
            'comp_score': round(comp_score, 2),
            'yearly_returns': m['yearly_returns']
        })

    df_res = pd.DataFrame(results)
    df_res_sorted = df_res.sort_values(by='comp_score', ascending=False)

    print("=================================================================================")
    print("  🏆 TOP 5 CHAMPION PERMUTATION & COMBINATION CONFIGURATIONS")
    print("=================================================================================\n")

    for rank, (i_res, row) in enumerate(df_res_sorted.head(5).iterrows(), 1):
        print(f"RANK #{rank} — Permutation #{row['perm_id']} (Composite Score: {row['comp_score']})")
        print(f"  • TP Scaling Target:   {row['tp_config']}")
        print(f"  • Risk Sizing Policy:  {row['risk_config']}")
        print(f"  • Trailing Stop Mode:  {row['trail_config']}")
        print(f"  • Session Filter:      {row['session_config']}")
        print(f"  ─────────────────────────────────────────────────────────────────────────────")
        print(f"  • Executed Trades:     {row['trades']}")
        print(f"  • Win Rate (%):        {row['win_rate']}%")
        print(f"  • Net Return (%):      {row['net_return']:+0.2f}%")
        print(f"  • Profit Factor (PF):  {row['pf']}")
        print(f"  • Max Drawdown (%):    {row['max_dd']}%")
        print(f"  • Sharpe Ratio:        {row['sharpe']}")
        print(f"  • Recovery Factor:     {row['recovery_factor']}")
        print(f"  ─────────────────────────────────────────────────────────────────────────────")
        print(f"  • Yearly Breakdown (%):")
        for yr, ret in row['yearly_returns'].items():
            print(f"     - {yr}: {ret:+0.2f}%")
        print("=================================================================================\n")

if __name__ == "__main__":
    main()
