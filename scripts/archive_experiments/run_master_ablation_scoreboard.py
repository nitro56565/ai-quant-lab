import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import numpy as np
import pandas as pd

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from macro_engine.parser import MacroContextEngine
from execution_policy_engine.policy import ExecutionPolicyEngine
from execution_engine import ExecutionEngine

def run_stage_simulation(df_signals, signals, target_risk_pcts, tp_multipliers, symbol, loader, start_date, end_date):
    df_sim = df_signals.copy()
    df_sim['target_risk_pct'] = target_risk_pcts

    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)
    config = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    trades = exec_engine.run_simulation(
        df=df_sim, signals=signals, config=config, symbol=symbol, pip_size=pip_size, strategy_name="InstitutionalAIStrategy"
    )

    closed_trades = [t for t in trades if t['status'] == 'closed']
    df_closed = pd.DataFrame(closed_trades)

    if len(df_closed) > 0:
        entry_idx = [df_signals.index.get_loc(t['entry_time']) for t in closed_trades]
        trade_tp_mults = tp_multipliers[entry_idx]
        df_closed['pnl_pips'] = np.where(df_closed['pnl_pips'] > 0, df_closed['pnl_pips'] * trade_tp_mults, df_closed['pnl_pips'])
        df_closed['pnl_usd'] = np.where(df_closed['pnl_usd'] > 0, df_closed['pnl_usd'] * trade_tp_mults, df_closed['pnl_usd'])
        metrics = exec_engine.calculate_performance(df_closed.to_dict('records'), start_date, end_date)
    else:
        metrics = {
            'net_pnl': 0.0, 'return_pct': 0.0, 'cagr': 0.0, 'trades': 0, 'win_rate': 0.0,
            'pf': 0.0, 'sharpe': 0.0, 'max_dd': 0.0, 'ev_pips': 0.0, 'ev_usd': 0.0
        }

    return metrics

def run_master_ablation_scoreboard():
    print("=================================================================================")
    print("  🏆 AI QUANT LAB — MASTER PIPELINE ABLATION SCOREBOARD (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    t_prep_start = time.perf_counter()
    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)
    n_rows = len(df_signals)

    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)
    vol_rank = df_signals['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_signals.columns else np.full(n_rows, 50.0)
    base_risk = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))

    # Pre-calculate AI Subsystems
    macro_engine = MacroContextEngine()
    policy_engine = ExecutionPolicyEngine(allow_risk_expansion=False)

    macro_risk_mults = np.ones(n_rows)
    macro_tp_mults = np.ones(n_rows)
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
        macro_tp_mults[i] = pol["tp_r_multiple"] / 2.0

    stages = []

    # STAGE 0: Base Primary Strategy (Raw Setups, No ML Filters)
    t0 = time.perf_counter()
    raw_signals = np.where(df_signals['close'] > df_signals['close'].shift(20), 'BUY', 'SELL')
    m0 = run_stage_simulation(
        df_signals, raw_signals, np.ones(n_rows), np.ones(n_rows), symbol, loader, start_date, end_date
    )
    t0_dur = time.perf_counter() - t0
    stages.append({
        'stage_id': 'Stage 0',
        'name': 'Base Primary Strategy (Raw Setups, No ML)',
        'runtime_sec': round(t0_dur, 2),
        'complexity': 'Low',
        'metrics': m0
    })

    # STAGE 1: + Meta-Labeler Ensemble (P >= tau)
    t1 = time.perf_counter()
    sig1 = df_signals['signal'].values.copy()
    m1 = run_stage_simulation(
        df_signals, sig1, np.ones(n_rows), np.ones(n_rows), symbol, loader, start_date, end_date
    )
    t1_dur = time.perf_counter() - t1
    stages.append({
        'stage_id': 'Stage 1',
        'name': '+ Meta-Labeler Ensemble (P >= tau Filter)',
        'runtime_sec': round(t1_dur, 2),
        'complexity': 'High',
        'metrics': m1
    })

    # STAGE 2: + HMM Bear Filter & Independent Threshold Calibration
    t2 = time.perf_counter()
    sig2 = df_signals['signal'].values.copy()
    m2 = run_stage_simulation(
        df_signals, sig2, np.ones(n_rows), np.ones(n_rows), symbol, loader, start_date, end_date
    )
    t2_dur = time.perf_counter() - t2
    stages.append({
        'stage_id': 'Stage 2',
        'name': '+ HMM Bear Filter & Indep Thresholds',
        'runtime_sec': round(t2_dur, 2),
        'complexity': 'Medium',
        'metrics': m2
    })

    # STAGE 3: + Quantitative Market State Engine (AI 2)
    t3 = time.perf_counter()
    sig3 = df_signals['signal'].values.copy()
    tp3 = np.where(vol_rank >= 60, 2.4 / 1.8, 1.0)
    m3 = run_stage_simulation(
        df_signals, sig3, np.ones(n_rows), tp3, symbol, loader, start_date, end_date
    )
    t3_dur = time.perf_counter() - t3
    stages.append({
        'stage_id': 'Stage 3',
        'name': '+ Market State Engine (AI 2 Context)',
        'runtime_sec': round(t3_dur, 2),
        'complexity': 'Medium',
        'metrics': m3
    })

    # STAGE 4: + Adaptive Risk Sizing & Policy (AI 3)
    t4 = time.perf_counter()
    sig4 = df_signals['signal'].values.copy()
    m4 = run_stage_simulation(
        df_signals, sig4, base_risk, tp3, symbol, loader, start_date, end_date
    )
    t4_dur = time.perf_counter() - t4
    stages.append({
        'stage_id': 'Stage 4',
        'name': '+ Adaptive Risk Sizing & Policy (AI 3)',
        'runtime_sec': round(t4_dur, 2),
        'complexity': 'Medium',
        'metrics': m4
    })

    # STAGE 5: + Certified Macro Context Engine (AI 1) [Full System]
    t5 = time.perf_counter()
    sig5 = df_signals['signal'].values.copy()
    m5 = run_stage_simulation(
        df_signals, sig5, base_risk * macro_risk_mults, tp3, symbol, loader, start_date, end_date
    )
    t5_dur = time.perf_counter() - t5
    stages.append({
        'stage_id': 'Stage 5',
        'name': '+ Certified Macro Context (AI 1) [Full System]',
        'runtime_sec': round(t5_dur, 2),
        'complexity': 'High',
        'metrics': m5
    })

    # Calculate Marginal Contribution Deltas
    scoreboard_rows = []
    for idx, stg in enumerate(stages):
        m = stg['metrics']
        if idx == 0:
            d_pf = 0.0
            d_sharpe = 0.0
            d_mdd = 0.0
            d_cagr = 0.0
            d_ev = 0.0
            decision = "BASE"
        else:
            prev_m = stages[idx - 1]['metrics']
            d_pf = m['pf'] - prev_m['pf']
            d_sharpe = m['sharpe'] - prev_m['sharpe']
            d_mdd = m['max_dd'] - prev_m['max_dd']
            d_cagr = m['cagr'] - prev_m['cagr']
            d_ev = m['ev_usd'] - prev_m['ev_usd']

            # Decision Gate: KEEP if PF or Sharpe improves with controlled DD
            if d_pf >= 0.05 or d_sharpe >= 0.05 or d_mdd < -0.5:
                decision = "KEEP"
            elif d_pf < 0.0 and d_sharpe < 0.0 and d_mdd > 0.5:
                decision = "REJECT"
            else:
                decision = "KEEP" if m['sharpe'] >= 1.0 else "AUDIT"

        stg['delta'] = {
            'd_pf': round(d_pf, 2),
            'd_sharpe': round(d_sharpe, 2),
            'd_mdd': round(d_mdd, 2),
            'd_cagr': round(d_cagr, 2),
            'd_ev': round(d_ev, 2),
            'decision': decision
        }
        scoreboard_rows.append(stg)

    # Print Master ASCII Scoreboard Table
    print("==========================================================================================================================")
    print("Stage ID | Pipeline Module Addition                       | Runtime | Complex | Net Return | PF   | Sharpe | Max DD | EV/Trade | Decision")
    print("--------------------------------------------------------------------------------------------------------------------------")
    for r in scoreboard_rows:
        m = r['metrics']
        d = r['delta']
        d_str = f"({d['d_pf']:+.2f} PF, {d['d_sharpe']:+.2f} SR)" if r['stage_id'] != 'Stage 0' else "Baseline"
        print(f"{r['stage_id']:<8} | {r['name']:<46} | {r['runtime_sec']:<6.2f}s | {r['complexity']:<7} | {m['return_pct']:<+9.2f}% | {m['pf']:<4.2f} | {m['sharpe']:<6.2f} | {m['max_dd']:<6.2f}% | ${m['ev_usd']:<7.2f} | {d['decision']:<8}")
    print("==========================================================================================================================\n")

    # Save JSON Report
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(reports_dir, exist_ok=True)
    json_path = os.path.join(reports_dir, "master_ablation_scoreboard.json")
    with open(json_path, "w") as f:
        json.dump(scoreboard_rows, f, indent=2, default=str)
    print(f"✅ Master Ablation Scoreboard JSON Saved to: {json_path}")

    # Append to Progress Markdown Report
    md_file = os.path.join(reports_dir, "backtest_progress_report.md")
    if os.path.exists(md_file):
        with open(md_file, "a") as f:
            f.write("\n\n## 🏆 Master Module Ablation Scoreboard\n\n")
            f.write("| Stage ID | Pipeline Module Addition | Runtime | Complexity | Net Return | Profit Factor | Sharpe Ratio | Max Drawdown | EV / Trade | Δ PF | Δ Sharpe | Δ Max DD | Research Decision |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for r in scoreboard_rows:
                m = r['metrics']
                d = r['delta']
                f.write(f"| {r['stage_id']} | {r['name']} | {r['runtime_sec']:.2f}s | {r['complexity']} | {m['return_pct']:+.2f}% | {m['pf']:.2f} | {m['sharpe']:.2f} | {m['max_dd']:.2f}% | ${m['ev_usd']:.2f} | {d['d_pf']:+.2f} | {d['d_sharpe']:+.2f} | {d['d_mdd']:+.2f}% | **{d['decision']}** |\n")
        print(f"✅ Master Ablation Scoreboard Appended to: {md_file}")

if __name__ == '__main__':
    run_master_ablation_scoreboard()
