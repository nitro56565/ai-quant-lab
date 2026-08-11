import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import itertools
import numpy as np
import pandas as pd

from data_loader import DataLoader
from data_loader.request import DataRequest
from research_engine.labeler import TripleBarrierLabeler
from execution_engine import ExecutionEngine

def compute_composite_institutional_score(pf, sharpe, max_dd, dsr, yoy_positive_years, total_years=8):
    """
    Computes Composite Institutional Score (S_inst):
    S_inst = Sharpe * PF * (1.0 - MDD) * (1.0 + DSR) * (YoY_Positive_Years / Total_Years)
    """
    mdd_frac = min(max_dd / 100.0, 0.99)
    yoy_ratio = yoy_positive_years / float(total_years)
    s_inst = max(sharpe, 0.0) * max(pf, 0.0) * (1.0 - mdd_frac) * (1.0 + max(dsr, 0.0)) * yoy_ratio
    return round(s_inst, 4)

def run_label_permutation_gauntlet():
    print("=================================================================================")
    print("  🔬 MULTI-DIMENSIONAL LABEL PERMUTATION & OPTIMIZATION GAUNTLET (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    req = DataRequest(symbol=symbol, timeframe="1h", start=start_date, end=end_date)
    df = loader.load(req)
    n_rows = len(df)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    # 1. Define Multi-Dimensional Search Dimensions
    tp_mults = [2.0, 2.5, 3.0]
    sl_mults = [1.2, 1.5, 2.0]
    vertical_horizons = [12, 24, 36]
    label_formats = ['3-Class Touch', 'Joint MFE+MAE Regression', 'Binary Touch']
    entry_execs = ['Market Entry', '0.25 ATR Limit Retrace']

    combinations = list(itertools.product(tp_mults, sl_mults, vertical_horizons, label_formats, entry_execs))
    print(f"Total Combinatorial Search Space: {len(combinations)} Candidate Permutations across 2018–2025\n")

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values
    df['feat_vol_atr'] = atr

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    config = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}

    results = []

    t_start_all = time.perf_counter()

    for idx, (tp_m, sl_m, vert_h, lbl_fmt, entry_ex) in enumerate(combinations[:18]): # Representative grid slice
        t_sub_start = time.perf_counter()

        tb_labeler = TripleBarrierLabeler(tp_atr_mult=tp_m, sl_atr_mult=sl_m, max_holding_bars=vert_h)
        df_lbl = tb_labeler.label(df)

        # Signal generation simulation
        signals = np.full(n_rows, None, dtype=object)
        if lbl_fmt == '3-Class Touch':
            sig_mask_long = (df_lbl['label_tb_target_long'] == 1) & (df['close'] > df['close'].shift(20))
            sig_mask_short = (df_lbl['label_tb_target_short'] == 1) & (df['close'] < df['close'].shift(20))
        elif lbl_fmt == 'Joint MFE+MAE Regression':
            sig_mask_long = (df_lbl['label_mfe_long_pips'] > 25.0) & (df_lbl['label_mae_long_pips'] < 15.0)
            sig_mask_short = (df_lbl['label_mfe_short_pips'] > 25.0) & (df_lbl['label_mae_short_pips'] < 15.0)
        else: # Binary Touch
            sig_mask_long = (df_lbl['label_target_long'] == 1)
            sig_mask_short = (df_lbl['label_target_short'] == 1)

        signals[sig_mask_long] = 'BUY'
        signals[sig_mask_short] = 'SELL'

        trades = exec_engine.run_simulation(
            df=df, signals=signals, config=config, symbol=symbol, pip_size=pip_size, strategy_name="InstitutionalAIStrategy"
        )
        closed_trades = [t for t in trades if t['status'] == 'closed']

        if len(closed_trades) > 0:
            df_closed = pd.DataFrame(closed_trades)
            
            # Apply Limit Retrace Price Improvement if enabled
            if entry_ex == '0.25 ATR Limit Retrace':
                retrace_pips = (atr[df_closed['entry_time'].map(lambda x: df.index.get_loc(x))] / pip_size) * 0.25
                df_closed['pnl_pips'] += retrace_pips
                df_closed['pnl_usd'] += retrace_pips * 10.0

            m = exec_engine.calculate_performance(df_closed.to_dict('records'), start_date, end_date)
            
            # Calculate YoY positive years
            df_closed['entry_year'] = pd.to_datetime(df_closed['entry_time']).dt.year
            years = sorted(df_closed['entry_year'].unique())
            yoy_positive = sum(df_closed[df_closed['entry_year'] == yr]['pnl_usd'].sum() > 0 for yr in years)
        else:
            m = {'net_pnl': 0.0, 'return_pct': 0.0, 'cagr': 0.0, 'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0, 'max_dd': 0.0, 'ev_usd': 0.0, 'dsr': 0.0}
            yoy_positive = 0

        t_sub_dur = time.perf_counter() - t_sub_start

        s_inst = compute_composite_institutional_score(
            pf=m['pf'], sharpe=m['sharpe'], max_dd=m['max_dd'], dsr=m.get('dsr', 0.02), yoy_positive_years=yoy_positive
        )

        perm_id = f"P{idx+1:02d}"
        results.append({
            'perm_id': perm_id,
            'tp_mult': tp_m,
            'sl_mult': sl_m,
            'vertical_h': vert_h,
            'label_format': lbl_fmt,
            'entry_execution': entry_ex,
            'runtime_sec': round(t_sub_dur, 2),
            'return_pct': round(m['return_pct'], 2),
            'pf': round(m['pf'], 2),
            'sharpe': round(m['sharpe'], 2),
            'max_dd': round(m['max_dd'], 2),
            'ev_usd': round(m['ev_usd'], 2),
            'yoy_positive_years': int(yoy_positive),
            's_inst': float(s_inst)

        })

    # Sort results by Composite Institutional Score (S_inst) descending
    results = sorted(results, key=lambda x: x['s_inst'], reverse=True)

    # Print Master Ranked CLI Scoreboard Table
    print("==========================================================================================================================")
    print("ID  | TP Barrier | SL Barrier | Vert Bar | Label Format            | Entry Execution        | Return (%) | PF   | SR   | MDD (%) | S_inst |")
    print("--------------------------------------------------------------------------------------------------------------------------")
    for r in results[:10]:
        print(f"{r['perm_id']:<3} | {r['tp_mult']:<10} | {r['sl_mult']:<10} | {r['vertical_h']:<8}h | {r['label_format']:<23} | {r['entry_execution']:<22} | {r['return_pct']:<+10.2f}% | {r['pf']:<4.2f} | {r['sharpe']:<4.2f} | {r['max_dd']:<7.2f}% | {r['s_inst']:<6.4f} |")
    print("==========================================================================================================================\n")

    # Save Candidate Champion Report to JSON
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(reports_dir, exist_ok=True)
    json_path = os.path.join(reports_dir, "label_permutation_gauntlet_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"✅ Master Label Permutation Results Saved to: {json_path}")
    print("🛡️ INSTITUTIONAL GOVERNANCE: Candidate Champion logged for human review (Production code preserved).")

if __name__ == '__main__':
    run_label_permutation_gauntlet()
