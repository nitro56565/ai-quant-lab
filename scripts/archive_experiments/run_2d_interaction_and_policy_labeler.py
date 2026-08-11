import sys
sys.path.append('/Users/mahesh.patil/Desktop/Mahesh/ai-quant-lab')

import pandas as pd
import numpy as np
import logging
from lightgbm import LGBMClassifier
from sklearn.model_selection import TimeSeriesSplit

from data_loader import DataLoader
from strategy_engine.institutional_ai import InstitutionalAIStrategy
from market_state_engine.execution_context import ExecutionContextEngine
from execution_engine import ExecutionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InteractionAndPolicyLabeler")

def main():
    print("=================================================================================")
    print("  🤖 AI QUANT LAB — 2D INTERACTION MATRIX & ML POLICY LABELER (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    # 1. Load Strategy Signals & Context Engine
    strat = InstitutionalAIStrategy()
    df_signals = strat.prepare_data(loader, symbol, start_date, end_date)

    ctx_engine = ExecutionContextEngine(rolling_window=1000)
    df_context = ctx_engine.prepare_rolling_ranks(df_signals)

    n_rows = len(df_context)
    trend_alignments = np.zeros(n_rows)
    volatility_states = np.zeros(n_rows)

    signals = df_context['signal'].values
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    for i in range(n_rows):
        sig = signals[i]
        trade_dir = sig if sig in ['BUY', 'SELL'] else 'BUY'
        ctx = ctx_engine.compute_context(df_context, i, trade_dir)
        trend_alignments[i] = ctx['trend_alignment']
        volatility_states[i] = ctx['volatility_state']

    df_context['trend_alignment'] = trend_alignments
    df_context['volatility_state'] = volatility_states

    # 2. Run Baseline Simulation & Record Trade Context + Holding Times
    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    config_base = {
        'sl_multiplier': strat.sl_atr_multiplier,
        'tp_multiplier': None,
        'trail_multiplier': strat.trail_atr_multiplier
    }

    trades_base = exec_engine.run_simulation(
        df=df_context,
        signals=signals,
        config=config_base,
        symbol=symbol,
        pip_size=pip_size,
        strategy_name='BaselineForPolicyLabeling'
    )

    closed = [t for t in trades_base if t['status'] == 'closed']
    df_trades = pd.DataFrame(closed)

    # Attach context and holding time metrics
    entry_indices = [df_context.index.get_loc(t['entry_time']) for t in closed]
    df_trades['trend_alignment'] = df_context['trend_alignment'].iloc[entry_indices].values
    df_trades['volatility_state'] = df_context['volatility_state'].iloc[entry_indices].values
    
    # Calculate holding time in hours
    df_trades['holding_hours'] = (pd.to_datetime(df_trades['exit_time']) - pd.to_datetime(df_trades['entry_time'])).dt.total_seconds() / 3600.0

    # 3. 2D Interaction Matrix: Trend Alignment x Volatility State
    print("=== 📊 1. TWO-DIMENSIONAL INTERACTION MATRIX (TREND x VOLATILITY) ===")
    
    # Bins: Low (0-40), Med (40-70), High (70-100)
    bins = [-0.1, 40.0, 70.0, 100.1]
    labels = ['Low (0-40)', 'Med (40-70)', 'High (70-100)']
    
    df_trades['trend_cat'] = pd.cut(df_trades['trend_alignment'], bins=bins, labels=labels)
    df_trades['vol_cat'] = pd.cut(df_trades['volatility_state'], bins=bins, labels=labels)

    grid_summary = []

    for t_cat in labels:
        for v_cat in labels:
            sub = df_trades[(df_trades['trend_cat'] == t_cat) & (df_trades['vol_cat'] == v_cat)]
            n_sub = len(sub)
            if n_sub == 0:
                continue
            wins = sub[sub['pnl_pips'] > 0]
            win_rate = (len(wins) / n_sub) * 100.0
            avg_pips = sub['pnl_pips'].mean()
            avg_hours = sub['holding_hours'].mean()
            win_cash = sub[sub['pnl_usd'] > 0]['pnl_usd'].sum()
            loss_cash = abs(sub[sub['pnl_usd'] <= 0]['pnl_usd'].sum())
            pf = win_cash / loss_cash if loss_cash > 0 else 1.0

            grid_summary.append({
                'Trend Alignment': t_cat,
                'Volatility State': v_cat,
                'Trades': n_sub,
                'Win Rate %': round(win_rate, 1),
                'Avg Pips': round(avg_pips, 2),
                'Avg Holding (h)': round(avg_hours, 1),
                'Profit Factor': round(pf, 2)
            })

    df_grid = pd.DataFrame(grid_summary)
    print(df_grid.to_string(index=False))
    print("\n")

    # 4. Granular Smooth R:R Escalation Experiment (2.0R -> 2.2R -> 2.4R -> 2.6R -> 2.8R)
    print("=== 🎯 2. GRANULAR R:R ESCALATION EXPERIMENT ===")
    
    rr_targets = [2.0, 2.2, 2.4, 2.6, 2.8]
    for rr in rr_targets:
        # Evaluate performance when high-alignment trades use target rr
        df_trades['sim_pnl_pips'] = df_trades['pnl_pips']
        # If high alignment (>=70), evaluate potential target
        high_align_mask = df_trades['trend_alignment'] >= 70.0
        # Scaling gain for winners
        df_trades.loc[high_align_mask & (df_trades['pnl_pips'] > 0), 'sim_pnl_pips'] = df_trades['pnl_pips'] * (rr / 2.0)
        
        net_pips = df_trades['sim_pnl_pips'].sum()
        win_pips = df_trades[df_trades['sim_pnl_pips'] > 0]['sim_pnl_pips'].sum()
        loss_pips = abs(df_trades[df_trades['sim_pnl_pips'] <= 0]['sim_pnl_pips'].sum())
        pf = win_pips / loss_pips if loss_pips > 0 else 1.0
        
        print(f"Target R: {rr:<4.1f}R | Total Net Pips: {net_pips:<+8.1f} | Simulated Profit Factor: {pf:<5.2f}")

    print("\n")

    # 5. Machine-Labeling Historical Optimal Policy & LightGBM Training (AI 3)
    print("=== 🤖 3. AI 3 MACHINE-LEARNED EXECUTION POLICY PREDICTOR ===")
    
    # 3 Policy Classes based on realized trade performance & holding time:
    # 0: Quick Exit (Choppy/Failed setup -> Exit early within 6h)
    # 1: Standard Hold (12h holding horizon, 2.0R target)
    # 2: Extended Trend Hold (24h holding horizon, 2.4R target, ATR Trail)
    
    policy_labels = []
    for idx, t in df_trades.iterrows():
        pnl = t['pnl_pips']
        hours = t['holding_hours']
        align = t['trend_alignment']
        
        if pnl > 15.0 and align >= 60.0:
            policy_labels.append(2)  # Extended Trend Hold
        elif pnl > 0.0:
            policy_labels.append(1)  # Standard Hold
        else:
            policy_labels.append(0)  # Quick Exit
            
    df_trades['optimal_policy'] = policy_labels

    X = df_trades[['trend_alignment', 'volatility_state']].values
    y = df_trades['optimal_policy'].values

    clf = LGBMClassifier(n_estimators=50, max_depth=3, learning_rate=0.05, random_state=42, verbose=-1)
    
    # Evaluate 5-fold Time Series Cross Validation Accuracy
    tscv = TimeSeriesSplit(n_splits=5)
    accs = []
    for train_idx, val_idx in tscv.split(X):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]
        clf.fit(X_tr, y_tr)
        accs.append(clf.score(X_val, y_val))
        
    print(f"LightGBM Policy Engine (AI 3) Cross-Validation Accuracy: {np.mean(accs)*100:.1f}%")
    print("Class Distribution: [0: Quick Exit, 1: Standard Hold, 2: Extended Trend Hold]")
    print(pd.Series(y).value_counts(normalize=True).round(3).to_dict())
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
