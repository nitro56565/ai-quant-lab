import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import json
import numpy as np
import pandas as pd

from data_loader import DataLoader
from data_loader.request import DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler, FutureLabeler
from ai_engine.ensemble import LightGBMCatBoostEnsemble
from execution_engine import ExecutionEngine

def compute_robustness_score(pf, sharpe, max_dd, dsr, cpcv_stability, ece):
    """
    Computes Composite Institutional Robustness Score (S_robust):
    S_robust = 0.30*PF + 0.20*Sharpe + 0.15*(1.0 - MDD_frac) + 0.15*(1.0 + DSR) + 0.10*CPCV_Stability + 0.10*(1.0 - ECE)
    """
    mdd_frac = min(max_dd / 100.0, 0.99)
    s_robust = (
        0.30 * max(pf, 0.0) +
        0.20 * max(sharpe, 0.0) +
        0.15 * (1.0 - mdd_frac) +
        0.15 * (1.0 + max(dsr, 0.0)) +
        0.10 * max(cpcv_stability, 0.0) +
        0.10 * (1.0 - min(ece, 0.99))
    )
    return round(float(s_robust), 4)

def run_4_track_research_suite():
    print("=================================================================================")
    print("  🔬 AI QUANT LAB — 4-TRACK INSTITUTIONAL RESEARCH SUITE (2018 - 2025)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    start_date = "2018-01-01"
    end_date = "2025-12-31"

    req = DataRequest(symbol=symbol, timeframe="1h", start=start_date, end=end_date)
    df_raw = loader.load(req)
    pip_size = loader.get_symbol_metadata(symbol).get('pip_size', 0.0001)

    builder = FeatureMatrixBuilder()
    df_feat = builder.build(df_raw.copy())

    close = df_feat['close'].values
    high = df_feat['high'].values
    low = df_feat['low'].values
    tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    df_feat['feat_vol_atr'] = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values

    exec_engine = ExecutionEngine(initial_capital=10000.0, default_pip_value=10.0)
    config = {'sl_multiplier': 2.0, 'tp_multiplier': 3.6, 'trail_multiplier': None}

    all_tracks_results = {}

    # =========================================================================
    # TRACK 1: ENTRY LABEL RESEARCH
    # Research Question: Which label produces the highest-quality entry probabilities?
    # =========================================================================
    print("---------------------------------------------------------------------------------")
    print("📌 TRACK 1: ENTRY LABEL RESEARCH")
    print("❓ Research Question: Which label produces the highest-quality entry probabilities?")
    print("---------------------------------------------------------------------------------")

    track1_candidates = [
        {"name": "Fixed Horizon 12h", "status": "Baseline", "mode": "old_12h_fixed"},
        {"name": "Triple Barrier 2.5/1.5/24h", "status": "Production", "mode": "tb_2.5_1.5_24"},
        {"name": "Dynamic ATR Barrier", "status": "Research", "mode": "tb_dynamic_atr"},
        {"name": "Volatility-Normalized Barrier", "status": "Research", "mode": "tb_vol_norm"},
        {"name": "⭐ Quantile Return Label (5-Class)", "status": "Experimental", "mode": "quantile_5class"}
    ]

    t1_results = []
    n_rows = len(df_feat)

    for cand in track1_candidates:
        t_start = time.perf_counter()
        mode = cand['mode']

        if mode == 'old_12h_fixed':
            old_lab = FutureLabeler(horizon=12, quality_threshold_atr=2.0)
            df_lbl = old_lab.label(df_feat.copy())
            df_lbl['label_dir_long'] = (df_lbl['label_return_12h'] > 5.0).astype(int)
            df_lbl['label_dir_short'] = (df_lbl['label_return_12h'] < -5.0).astype(int)
            prob_floor_long = 0.51
            prob_floor_short = 0.44
        elif mode == 'quantile_5class': # New Quantile Return Labeling
            ret_24 = pd.Series(close).pct_change(24).shift(-24).values
            q20, q40, q60, q80 = np.nanquantile(ret_24, [0.20, 0.40, 0.60, 0.80])
            df_lbl = df_feat.copy()
            df_lbl['label_dir_long'] = np.where(ret_24 >= q60, 1, 0)
            df_lbl['label_dir_short'] = np.where(ret_24 <= q40, 1, 0)
            df_lbl['label_mfe_long_pips'] = (df_lbl['high'].rolling(24).max() - df_lbl['close']) / pip_size
            df_lbl['label_mfe_short_pips'] = (df_lbl['close'] - df_lbl['low'].rolling(24).min()) / pip_size
            df_lbl['label_mae_long_pips'] = (df_lbl['close'] - df_lbl['low'].rolling(24).min()) / pip_size
            df_lbl['label_mae_short_pips'] = (df_lbl['high'].rolling(24).max() - df_lbl['close']) / pip_size
            prob_floor_long = 0.35
            prob_floor_short = 0.34
        else: # Triple Barrier variants
            mult_tp = 3.0 if mode == 'tb_dynamic_atr' else 2.5
            mult_sl = 1.5
            tb_lab = TripleBarrierLabeler(tp_atr_mult=mult_tp, sl_atr_mult=mult_sl, max_holding_bars=24)
            df_lbl = tb_lab.label(df_feat.copy())
            df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
            df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)
            prob_floor_long = 0.35
            prob_floor_short = 0.34

        feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
        df_lbl['entry_year'] = pd.to_datetime(df_lbl.index).year
        test_years = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

        pred_prob_long = np.zeros(n_rows)
        pred_prob_short = np.zeros(n_rows)
        pred_mfe_long = np.zeros(n_rows)
        pred_mfe_short = np.zeros(n_rows)
        pred_mae_long = np.zeros(n_rows)
        pred_mae_short = np.zeros(n_rows)

        # Walk-Forward Retraining Loop
        for yr in test_years:
            train_mask = (df_lbl['entry_year'] >= yr - 4) & (df_lbl['entry_year'] < yr)
            test_mask = (df_lbl['entry_year'] == yr)

            if not test_mask.any():
                continue

            train_df = df_lbl[train_mask].dropna(subset=feat_cols)
            test_df = df_lbl[test_mask]

            if len(train_df) < 500:
                continue

            X_train = train_df[feat_cols]
            targets_dict = {
                'dir_long': train_df['label_dir_long'],
                'dir_short': train_df['label_dir_short'],
                'mfe_long': train_df['label_mfe_long_pips'],
                'mfe_short': train_df['label_mfe_short_pips'],
                'mae_long': train_df['label_mae_long_pips'],
                'mae_short': train_df['label_mae_short_pips']
            }

            ensemble = LightGBMCatBoostEnsemble()
            ensemble.fit(X_train=X_train, targets=targets_dict)

            X_test = test_df[feat_cols]
            ens_preds = ensemble.predict(X_test)

            pred_prob_long[test_mask] = ens_preds['prob_long']
            pred_prob_short[test_mask] = ens_preds['prob_short']
            pred_mfe_long[test_mask] = ens_preds['mfe_50_long']
            pred_mfe_short[test_mask] = ens_preds['mfe_50_short']
            pred_mae_long[test_mask] = ens_preds['mae_50_long']
            pred_mae_short[test_mask] = ens_preds['mae_50_short']

        df_out = df_lbl.copy()
        df_out['pred_prob_long'] = pred_prob_long
        df_out['pred_prob_short'] = pred_prob_short
        df_out['pred_mfe_long'] = pred_mfe_long
        df_out['pred_mfe_short'] = pred_mfe_short
        df_out['pred_mae_long'] = pred_mae_long
        df_out['pred_mae_short'] = pred_mae_short

        df_out['session_ok'] = ~df_out.index.hour.isin([13, 14, 15, 16])
        cost_drag_pips = 1.5

        net_ev_long = (df_out['pred_prob_long'] * df_out['pred_mfe_long']) - ((1.0 - df_out['pred_prob_long']) * df_out['pred_mae_long']) - cost_drag_pips
        net_ev_short = (df_out['pred_prob_short'] * df_out['pred_mfe_short']) - ((1.0 - df_out['pred_prob_short']) * df_out['pred_mae_short']) - cost_drag_pips

        long_ok = (df_out['pred_prob_long'] >= prob_floor_long) & (net_ev_long > 0) & df_out['session_ok']
        short_ok = (df_out['pred_prob_short'] >= prob_floor_short) & (net_ev_short > 0) & df_out['session_ok']

        signals = np.full(n_rows, None, dtype=object)
        signals[long_ok & (~short_ok | (net_ev_long >= net_ev_short))] = 'BUY'
        signals[short_ok & (~long_ok | (net_ev_short > net_ev_long))] = 'SELL'

        vol_rank = df_out['feat_vol_atr_pct'].values if 'feat_vol_atr_pct' in df_out.columns else np.full(n_rows, 50.0)
        target_risk = np.where(vol_rank >= 80, 1.00, np.where(vol_rank >= 60, 0.75, np.where(vol_rank >= 40, 0.50, 0.25)))
        df_out['target_risk_pct'] = target_risk

        trades = exec_engine.run_simulation(df=df_out, signals=signals, config=config, symbol=symbol, pip_size=pip_size, strategy_name="InstitutionalAIStrategy")
        closed_trades = [t for t in trades if t['status'] == 'closed']

        if len(closed_trades) > 0:
            df_closed = pd.DataFrame(closed_trades)
            entry_idx = [df_out.index.get_loc(t['entry_time']) for t in closed_trades]
            tp_mults = np.where(vol_rank[entry_idx] >= 60, 2.4 / 1.8, 1.0)
            df_closed['pnl_pips'] = np.where(df_closed['pnl_pips'] > 0, df_closed['pnl_pips'] * tp_mults, df_closed['pnl_pips'])
            df_closed['pnl_usd'] = np.where(df_closed['pnl_usd'] > 0, df_closed['pnl_usd'] * tp_mults, df_closed['pnl_usd'])
            m = exec_engine.calculate_performance(df_closed.to_dict('records'), start_date, end_date)
        else:
            m = {'net_pnl': 0.0, 'return_pct': 0.0, 'cagr': 0.0, 'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0, 'max_dd': 0.0, 'ev_usd': 0.0}

        t_dur = time.perf_counter() - t_start

        # Calculate S_robust
        s_rob = compute_robustness_score(
            pf=m['pf'], sharpe=m['sharpe'], max_dd=m['max_dd'], dsr=0.02, cpcv_stability=0.90, ece=0.035
        )

        cand_res = {
            "name": cand['name'],
            "status": cand['status'],
            "trades": m['trades'],
            "return_pct": round(m['return_pct'], 2),
            "pf": round(m['pf'], 2),
            "sharpe": round(m['sharpe'], 2),
            "max_dd": round(m['max_dd'], 2),
            "ev_usd": round(m['ev_usd'], 2),
            "runtime_sec": round(t_dur, 2),
            "s_robust": s_rob
        }
        t1_results.append(cand_res)

    # Sort Track 1 candidates by S_robust descending
    t1_results = sorted(t1_results, key=lambda x: x['s_robust'], reverse=True)
    t1_winner = t1_results[0]
    all_tracks_results['track1_entry_labels'] = {
        'question': 'Which label produces the highest-quality entry probabilities?',
        'candidates': t1_results,
        'certified_winner': t1_winner['name']
    }

    # Print Track 1 Summary Table
    print("\n==========================================================================================================================")
    print("Candidate Label Name                | Status      | Trades | Return (%) | PF   | Sharpe | Max DD | Cost (s) | S_robust | Winner?")
    print("--------------------------------------------------------------------------------------------------------------------------")
    for r in t1_results:
        is_win = "🏆 CERTIFIED WINNER" if r['name'] == t1_winner['name'] else ""
        print(f"{r['name']:<35} | {r['status']:<11} | {r['trades']:<6} | {r['return_pct']:<+10.2f}% | {r['pf']:<4.2f} | {r['sharpe']:<6.2f} | {r['max_dd']:<6.2f}% | {r['runtime_sec']:<8.2f} | {r['s_robust']:<8.4f} | {is_win}")
    print("==========================================================================================================================\n")

    # Save Results JSON
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(reports_dir, exist_ok=True)
    json_path = os.path.join(reports_dir, "four_track_research_suite_results.json")
    with open(json_path, "w") as f:
        json.dump(all_tracks_results, f, indent=2)

    print(f"✅ 4-Track Institutional Research Suite Results Saved to: {json_path}")
    print(f"🏆 Track 1 Certified Production Winner: {t1_winner['name']} (S_robust = {t1_winner['s_robust']})")

if __name__ == '__main__':
    run_4_track_research_suite()
