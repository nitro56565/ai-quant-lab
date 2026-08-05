import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import json
import logging

from data_loader import DataLoader
from strategy_engine.volatility_breakout import VolatilityBreakout
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import FutureLabeler
from context_engine.aggregator import MarketContextAggregator
from execution_policy_engine.policy import ExecutionPolicyEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DecoupledAblation")

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — DECOUPLED AI MARKET CONTEXT ABLATION GAUNTLET (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # 1. Primary Strategy: Volatility Breakout
    vb = VolatilityBreakout()
    df_primary = vb.prepare_data(loader, symbol, "2014-01-01", end_date)

    # 2. Build Feature Matrix
    builder = FeatureMatrixBuilder()
    df_feat = builder.build(df_primary)

    # 3. Labeler
    labeler = FutureLabeler(horizon=12, quality_threshold_atr=2.0)
    df_labeled = labeler.label(df_feat)

    candidate_mask = (df_labeled['entry_signal'] == True)
    dates = df_labeled.index
    years = dates.year

    aggregator = MarketContextAggregator()
    policy_engine = ExecutionPolicyEngine()

    print(f"✅ Data Preparation Complete: {len(df_labeled)} candles, {candidate_mask.sum()} candidate breakouts.\n")

    # Evaluate Experiments
    # Exp A: Baseline Fixed Rules
    # Exp B: + Market State AI (AI 2)
    # Exp C: + Macro AI (AI 1 Event Risk Skip)
    # Exp D: Full Decoupled AI Architecture (AI 1 + AI 2 + AI 3 Bounded Policy)

    experiments = ["Exp A (Baseline Rules)", "Exp B (+ Market State AI)", "Exp C (+ Macro AI)", "Exp D (Full Decoupled AI)"]
    results = {}

    for exp in experiments:
        df_exp = df_labeled.copy()
        df_exp['signal'] = None
        df_exp['target_risk_pct'] = 0.50

        exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)

        for i in range(len(df_exp)):
            if not candidate_mask.iloc[i] or years[i] < 2018:
                continue

            # Build state vector
            state_vec = aggregator.build_state_vector(
                df=df_exp,
                idx=i,
                symbol=symbol,
                candidate_direction="BUY",
                meta_confidence=0.65
            )

            # Apply Experiment Filters
            if exp == "Exp A (Baseline Rules)":
                df_exp.iat[i, df_exp.columns.get_loc('signal')] = 'BUY'
            
            elif exp == "Exp B (+ Market State AI)":
                # Market State Filter: Trend Strength >= 40 & Quality >= 40
                if state_vec['market_state']['trend_strength'] >= 40 and state_vec['market_state']['trend_quality'] >= 40:
                    df_exp.iat[i, df_exp.columns.get_loc('signal')] = 'BUY'

            elif exp == "Exp C (+ Macro AI)":
                # Macro Event Risk Filter: Skip if event risk >= 80
                if state_vec['macro_context']['event_risk'] < 80.0:
                    df_exp.iat[i, df_exp.columns.get_loc('signal')] = 'BUY'

            elif exp == "Exp D (Full Decoupled AI)":
                # Policy Engine Bounded Output
                policy = policy_engine.determine_policy(state_vec)
                if policy['action'] != 'SKIP_TRADE':
                    df_exp.iat[i, df_exp.columns.get_loc('signal')] = 'BUY'
                    df_exp.iat[i, df_exp.columns.get_loc('target_risk_pct')] = 0.50 * policy['risk_multiplier']

        signals = df_exp['signal'].values
        pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

        config = {
            'sl_multiplier': 2.0,
            'tp_multiplier': None,
            'trail_multiplier': 3.0
        }

        trades = exec_engine.run_simulation(
            df=df_exp,
            signals=signals,
            config=config,
            symbol=symbol,
            pip_size=pip_size,
            strategy_name='DecoupledAIStrategy'
        )

        closed = [t for t in trades if t['status'] == 'closed']
        metrics = exec_engine.calculate_performance(closed, start_date, end_date)
        results[exp] = metrics

    print("=================================================================================")
    print("  📊 ABLATION EXPERIMENT PERFORMANCE MATRIX (2018 - 2025)")
    print("=================================================================================")
    print(f"{'Experiment':<30} | {'Trades':<8} | {'Win Rate':<10} | {'Net Return':<12} | {'PF':<8} | {'Max DD':<10}")
    print("-" * 85)

    for exp_name, m in results.items():
        print(f"{exp_name:<30} | {m['trades']:<8} | {m['win_rate']:<9.1f}% | {m['return_pct']:<+11.2f}% | {m['pf']:<8.2f} | {m['max_dd']:<9.2f}%")

    print("=================================================================================\n")

if __name__ == "__main__":
    main()
