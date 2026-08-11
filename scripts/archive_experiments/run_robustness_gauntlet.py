import numpy as np
import pandas as pd
import json
import time
import logging

# Suppress verbose logger outputs
logging.getLogger("data_loader").setLevel(logging.ERROR)
logging.getLogger("ExecutionEngine").setLevel(logging.ERROR)
logging.getLogger("RegimeDetector").setLevel(logging.ERROR)

from data_loader import DataLoader
from strategy_engine.ml_consensus import MLConsensusStrategy
from execution_engine import ExecutionEngine

def run_monte_carlo(trades, initial_capital=10000.0, n_simulations=5000):
    if len(trades) == 0:
        return {}
        
    pnl_usd_array = np.array([t['pnl_usd'] for t in trades])
    n_trades = len(pnl_usd_array)
    
    final_equities = np.zeros(n_simulations)
    max_drawdowns = np.zeros(n_simulations)
    profit_factors = np.zeros(n_simulations)
    
    rng = np.random.default_rng(seed=42)
    
    for s in range(n_simulations):
        # Bootstrap sample trade PnLs with replacement
        sample_pnl = rng.choice(pnl_usd_array, size=n_trades, replace=True)
        equity_curve = initial_capital + np.cumsum(sample_pnl)
        equity_curve = np.insert(equity_curve, 0, initial_capital)
        
        final_equities[s] = equity_curve[-1]
        
        # Calculate Peak to Trough Drawdown
        peak = np.maximum.accumulate(equity_curve)
        dd = (peak - equity_curve) / peak
        max_drawdowns[s] = np.max(dd) * 100.0
        
        wins = sample_pnl[sample_pnl > 0]
        losses = sample_pnl[sample_pnl < 0]
        gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
        gross_loss = abs(np.sum(losses)) if len(losses) > 0 else 1e-9
        profit_factors[s] = gross_profit / gross_loss
        
    return {
        "n_simulations": n_simulations,
        "n_trades_per_sim": n_trades,
        "final_equity_median": float(np.median(final_equities)),
        "final_equity_5th": float(np.percentile(final_equities, 5)),
        "final_equity_95th": float(np.percentile(final_equities, 95)),
        "max_dd_median": float(np.median(max_drawdowns)),
        "max_dd_95th": float(np.percentile(max_drawdowns, 95)),
        "max_dd_99th": float(np.percentile(max_drawdowns, 99)),
        "profit_factor_median": float(np.median(profit_factors)),
        "prob_of_loss": float(np.mean(final_equities < initial_capital) * 100.0)
    }

def main():
    print("=================================================================================")
    print("  🚀 AI QUANT LAB — STRATEGY ROBUSTNESS & SENSITIVITY GAUNTLET")
    print("=================================================================================\n")
    
    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"
    
    # 1. Pre-compute rolling ML predictions once
    print("⚡ Pre-computing rolling walk ML models and feature matrix (single pass)...")
    t_start = time.time()
    strat = MLConsensusStrategy(ev_threshold=34.0)
    df_prepared = strat.prepare_data(loader, symbol, start_date, end_date)
    print(f"   Done in {time.time() - t_start:.1f}s! Data shape: {df_prepared.shape}\n")
    
    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)
    
    config = {
        'sl_multiplier': strat.sl_atr_multiplier,
        'tp_multiplier': None,
        'trail_multiplier': strat.trail_atr_multiplier
    }
    
    def evaluate_signals_for_threshold(threshold, extra_pip_cost=0.0):
        df_copy = df_prepared.copy()
        df_copy['ev_threshold'] = float(threshold)
        df_signals = strat.generate_signals(df_copy)
        
        signals = np.full(len(df_signals), None, dtype=object)
        if 'signal' in df_signals.columns:
            signals = df_signals['signal'].values
        else:
            signals[df_signals['entry_signal'].values] = 'BUY'
            
        trades = exec_engine.run_simulation(
            df=df_signals,
            signals=signals,
            config=config,
            symbol=symbol,
            pip_size=pip_size,
            strategy_name="MLConsensusStrategy"
        )
        
        closed_trades = [t for t in trades if t['status'] == 'closed']
        if extra_pip_cost > 0:
            for t in closed_trades:
                t['pnl_pips'] -= extra_pip_cost
                t['pnl_usd'] = t['pnl_pips'] * t['size'] * 10.0
                
        metrics = exec_engine.calculate_performance(closed_trades, start_date, end_date) if closed_trades else {}
        return closed_trades, metrics

    # ---------------------------------------------------------------------------
    # 1. PARAMETER SENSITIVITY SWEEP (28, 30, 32, 34, 36, 38, 40 pips)
    # ---------------------------------------------------------------------------
    print("📊 TASK 1: Parameter Sensitivity Sweep (Threshold Range: 28 to 40 pips)")
    print("-" * 81)
    thresholds = [28, 30, 32, 34, 36, 38, 40]
    sensitivity_results = []
    
    base_trades_34 = None
    
    for th in thresholds:
        t0 = time.time()
        trades, metrics = evaluate_signals_for_threshold(th)
        elapsed = time.time() - t0
        
        if th == 34:
            base_trades_34 = trades
            
        n_trades = len(trades)
        wins = [t for t in trades if t['pnl_pips'] > 0]
        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        pnl_pips = sum(t['pnl_pips'] for t in trades)
        pnl_usd = sum(t['pnl_usd'] for t in trades)
        pf = metrics.get('profit_factor', 0.0)
        max_dd = metrics.get('max_drawdown', 0.0)
        
        res = {
            "threshold": th,
            "trades": n_trades,
            "win_rate": win_rate,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
            "profit_factor": pf,
            "max_dd": max_dd,
            "elapsed_s": elapsed
        }
        sensitivity_results.append(res)
        print(f"   Threshold: {th:2d} pips | Trades: {n_trades:3d} | WR: {win_rate:5.1f}% | PnL: {pnl_pips:+7.1f} pips (${pnl_usd:+8.2f}) | PF: {pf:4.2f} | DD: {max_dd:5.2f}%")
        
    print("\n" + "=" * 81 + "\n")

    # ---------------------------------------------------------------------------
    # 2. COST SENSITIVITY / FRICTION ESCALATION (+50%, +100%, +200%)
    # ---------------------------------------------------------------------------
    print("💸 TASK 2: Cost Sensitivity Analysis (Spread & Friction Escalation)")
    print("-" * 81)
    friction_levels = [
        {"name": "Baseline (0.0 pips extra)", "extra_cost": 0.0},
        {"name": "+50% Cost (+0.5 pips/trade)", "extra_cost": 0.5},
        {"name": "+100% Cost (+1.0 pips/trade)", "extra_cost": 1.0},
        {"name": "+200% Extreme (+2.0 pips/trade)", "extra_cost": 2.0},
    ]
    cost_results = []
    
    for f_info in friction_levels:
        trades, metrics = evaluate_signals_for_threshold(34.0, extra_pip_cost=f_info['extra_cost'])
        n_trades = len(trades)
        wins = [t for t in trades if t['pnl_pips'] > 0]
        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        pnl_pips = sum(t['pnl_pips'] for t in trades)
        pnl_usd = sum(t['pnl_usd'] for t in trades)
        
        gross_win = sum(t['pnl_usd'] for t in wins)
        gross_loss = abs(sum(t['pnl_usd'] for t in trades if t['pnl_pips'] <= 0))
        pf = gross_win / gross_loss if gross_loss > 0 else 1.0
        
        res = {
            "name": f_info['name'],
            "extra_cost": f_info['extra_cost'],
            "trades": n_trades,
            "win_rate": win_rate,
            "pnl_pips": pnl_pips,
            "pnl_usd": pnl_usd,
            "profit_factor": pf
        }
        cost_results.append(res)
        print(f"   {f_info['name']:<32} | Trades: {n_trades:3d} | WR: {win_rate:5.1f}% | PnL: {pnl_pips:+7.1f} pips (${pnl_usd:+8.2f}) | PF: {pf:4.2f}")

    print("\n" + "=" * 81 + "\n")

    # ---------------------------------------------------------------------------
    # 3. MONTE CARLO SIMULATIONS (5,000 Path Resamplings)
    # ---------------------------------------------------------------------------
    print("🎲 TASK 3: Monte Carlo Simulation (5,000 Path Bootstrap Resamplings)")
    print("-" * 81)
    mc_stats = run_monte_carlo(base_trades_34, initial_capital=10000.0, n_simulations=5000)
    print(f"   Trades Sampled Per Path:  {mc_stats['n_trades_per_sim']}")
    print(f"   Median Final Equity:      ${mc_stats['final_equity_median']:,.2f}")
    print(f"   5th Percentile Equity:    ${mc_stats['final_equity_5th']:,.2f} (Worst 5% Outcome)")
    print(f"   95th Percentile Equity:   ${mc_stats['final_equity_95th']:,.2f} (Best 5% Outcome)")
    print(f"   Median Max Drawdown:      {mc_stats['max_dd_median']:.2f}%")
    print(f"   95th Percentile Max DD:   {mc_stats['max_dd_95th']:.2f}% (VaR 95%)")
    print(f"   99th Percentile Max DD:   {mc_stats['max_dd_99th']:.2f}% (Worst-Case VaR 99%)")
    print(f"   Median Profit Factor:     {mc_stats['profit_factor_median']:.2f}")
    print(f"   Probability of Net Loss:  {mc_stats['prob_of_loss']:.1f}%")

    print("\n" + "=" * 81 + "\n")

    # Save complete JSON artifact
    full_output = {
        "sensitivity": sensitivity_results,
        "cost_sensitivity": cost_results,
        "monte_carlo": mc_stats
    }
    
    with open("robustness_gauntlet_results.json", "w") as f:
        json.dump(full_output, f, indent=2)
        
    print("✅ Robustness tests completed! Raw results saved to 'robustness_gauntlet_results.json'.")

if __name__ == "__main__":
    main()
