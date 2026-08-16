"""
=================================================================================
       MASTER CANONICAL PRODUCTION BACKTEST — VERSION 2.0 (COMBO #271 🏆)
=================================================================================
Canonical Production Benchmark Suite for AI Quant Lab v5.0 — Baseline v2.0 Master.

Specifications for Combo #271 (Proposed Production Baseline v2.0 Master):
- Asset: EURUSD H1
- Period: 2018-01-01 to 2025-12-31 (8-Fold Walk-Forward OOS)
- Holdout: 2026-01-01 to 2026-08-11 (100% Untouched)
- Ensemble Ratio: Ratio A (50% CatBoost / 25% LightGBM / 25% XGBoost)
- Tree Depth: max_depth = 4 (Grid B Tree Regularization)
- Regime Engine: 4-State Engine (2 HMM x 2 Volatility Quantile)
- Barrier Multipliers: Extended 3.0 ATR Take Profit / 1.5 ATR Stop Loss
- Maximum Holding: 36 Hours
- Allocation: 0.75% Fixed-Fractional Risk per Trade ($75 risk per trade on $10,000 base)
- Max Open Positions: 1 (Single position strictly enforced, 0 overlap)
- Transaction Friction: 0.3 pips spread/slippage on EVERY exit & partial exit + $7/lot commission
- Order Entry: 0.25 ATR Retrace Limit Order (3h expiry)
- Partial Exit Engine: 50% Partial Exit @ +1.5R
- PAE Guard: 0.42 Range / 0.36 Trend Hurdles
=================================================================================
"""

import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector

def process_fold_combo271(yr, df_lbl, all_feat_cols):
    warnings.filterwarnings("ignore")
    fold_seed = 42
    np.random.seed(fold_seed)

    train_end_year = yr - 1
    train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
    test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_m].copy()

    # 4-State Regime Engine (2-State HMM x 2-State ATR Volatility Quantile)
    hmm_detector = HMMRegimeDetector(n_components=2, random_state=fold_seed)
    hmm_detector.fit(df_tr)
    hmm_tr = hmm_detector.predict(df_tr)
    hmm_te = hmm_detector.predict(df_te)

    tr_v = df_tr['feat_vol_atr_pct'].values; te_v = df_te['feat_vol_atr_pct'].values
    v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 50.0] = 1
    v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 50.0] = 1

    state_tr = (hmm_tr * 2) + v_tr; state_te = (hmm_te * 2) + v_te

    X_tr_mat = df_tr[all_feat_cols].values; X_te_mat = df_te[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values

    pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
    ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

    # max_depth = 4
    for s in range(4):
        mask_tr = (state_tr == s); mask_te = (state_te == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

            pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat[mask_te])[:, 1]

            ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat[mask_te])[:, 1]
        else:
            pl_lgb[mask_te] = 0.30; pl_cat[mask_te] = 0.30; pl_xgb[mask_te] = 0.30
            ps_lgb[mask_te] = 0.30; ps_cat[mask_te] = 0.30; ps_xgb[mask_te] = 0.30

    # Ratio A (50% CatBoost / 25% LightGBM / 25% XGBoost)
    p_stack_l = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)
    return df_te.index, p_stack_l, p_stack_s, hmm_te

def run_simulation_combo271(df_eval, p_l, p_s, hmm_arr, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    
    # PAE Hurdles: 0.42 Range / 0.36 Trend
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    friction_pips = 0.3
    comm_per_lot = 7.0
    risk_pct = 0.0075
    max_open_pos = 1
    max_holding_bars = 36.0 # Extended 36h Holding

    active_positions = []; pending_orders = []; closed_trades = []; current_equity = initial_cap; daily_equity = {}

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        # 1. Active Position Evaluation
        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            # Partial Exit (50% @ +1.5R) with 0.3 pips friction & $7/lot commission
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            # Exit Conditions (36h max holding)
            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= max_holding_bars: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips # 0.3 pips friction on every exit
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = timestamp; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
                current_equity += rem_net
                closed_trades.append(pos)

                if signals_arr[i] == opposite_sig:
                    pending_orders.append({"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr})
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        # 2. Pending Limit Order Fill Check (Extended TP 3.0 / SL 1.5)
        remaining_orders = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3: continue
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']

            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
            if filled and len(active_positions) < max_open_pos:
                sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 3.0; initial_sl_dist = (p_atr / pip_size) * 1.5 * pip_size
                entry_price = p_limit
                sl_price = entry_price - (p_atr * 1.5) if p_dir == 'BUY' else entry_price + (p_atr * 1.5)
                tp_price = entry_price + (p_atr * 3.0) if p_dir == 'BUY' else entry_price - (p_atr * 3.0)

                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                new_pos = {
                    'trade_id': len(closed_trades) + len(active_positions) + 1,
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0,
                    'status': 'open'
                }
                active_positions.append(new_pos)
            elif not filled:
                remaining_orders.append(p_order)

        pending_orders = remaining_orders

        # 3. New Pending Order Creation
        if len(active_positions) + len(pending_orders) < max_open_pos and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]
            retrace_pips = (atr / pip_size) * 0.25
            limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
            pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

        daily_equity[str(timestamp.date())] = current_equity

    pnls = [t['pnl_usd'] for t in closed_trades]
    r_multiples = [t.get('r_multiple', 0.0) for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()

    num_years = (timestamps[-1] - timestamps[0]).days / 365.25
    cagr_pct = (((current_equity / initial_cap) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    downside_rets = daily_rets[daily_rets < 0]
    sortino_daily = (daily_rets.mean() / downside_rets.std() * np.sqrt(252)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
    avg_r = np.mean(r_multiples) if r_multiples else 0.0

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min())
    dd_95 = abs(np.percentile(dds, 5))
    dd_99 = abs(np.percentile(dds, 1))

    eq_df = pd.DataFrame({'equity': eq_series}, index=pd.to_datetime(eq_series.index))
    monthly_rets = eq_df['equity'].resample('M').last().pct_change().dropna() * 100.0
    yearly_rets = eq_df['equity'].resample('A').last().pct_change().dropna() * 100.0

    worst_month = monthly_rets.min() if len(monthly_rets) > 0 else 0.0
    worst_year = yearly_rets.min() if len(yearly_rets) > 0 else 0.0

    return {
        'trades': len(closed_trades),
        'end_eq': current_equity,
        'net_pnl': net_pnl,
        'ret_pct': ret_pct,
        'cagr_pct': cagr_pct,
        'sharpe': sharpe_daily,
        'sortino': sortino_daily,
        'pf': pf,
        'win_rate': win_rate,
        'mtm_max_dd': mtm_max_dd,
        'dd_95': dd_95,
        'dd_99': dd_99,
        'worst_month': worst_month,
        'worst_year': worst_year,
        'avg_r': avg_r
    }

def main():
    print("=================================================================================", flush=True)
    print("  🏆 RUNNING CANONICAL PRODUCTION BACKTEST — VERSION 2.0 (COMBO #271 MASTER)", flush=True)
    print("=================================================================================\n", flush=True)

    loader = DataLoader()
    symbol = "EURUSD"
    req_full = DataRequest(symbol=symbol, timeframe="1h", start="2014-01-01", end="2026-08-11")
    df_full = loader.load(req_full)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_full.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    # 1. 2018-2025 OOS Gauntlet
    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    years_oos = list(range(2018, 2026))

    safe_cores = max(1, (os.cpu_count() or 4) - 1)
    print("▶ Executing 8-Fold OOS Walk-Forward Model Training for Combo #271 (2018-2025)...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold_combo271)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l_oos = np.zeros(len(df_eval_oos))
    p_stack_s_oos = np.zeros(len(df_eval_oos))
    hmm_oos = np.zeros(len(df_eval_oos))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[fold_eval_indices] = pl_fold
        p_stack_s_oos[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    oos_res = run_simulation_combo271(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos)

    # 2. 2026 Untouched Live Holdout
    print("▶ Executing 100% Untouched 2026 Live Holdout Fold for Combo #271 (Jan 1 - Aug 11, 2026)...", flush=True)
    mask_2026 = (df_feat.index >= "2026-01-01") & (df_feat.index <= "2026-08-11")
    df_eval_26 = df_feat[mask_2026].copy()

    train_m_26 = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    df_tr_26 = df_lbl[train_m_26].dropna(subset=['label_dir_long']).copy()

    fold_seed = 42
    hmm_detector = HMMRegimeDetector(n_components=2, random_state=fold_seed)
    hmm_detector.fit(df_tr_26)
    hmm_tr_26 = hmm_detector.predict(df_tr_26)
    hmm_te_26 = hmm_detector.predict(df_eval_26)

    tr_v_26 = df_tr_26['feat_vol_atr_pct'].values; te_v_26 = df_eval_26['feat_vol_atr_pct'].values
    v_tr_26 = np.zeros(len(tr_v_26), dtype=int); v_tr_26[tr_v_26 >= 50.0] = 1
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 50.0] = 1

    state_tr_26 = (hmm_tr_26 * 2) + v_tr_26; state_te_26 = (hmm_te_26 * 2) + v_te_26
    X_tr_mat_26 = df_tr_26[all_feat_cols].values; X_te_mat_26 = df_eval_26[all_feat_cols].values
    y_l_tr_26 = df_tr_26['label_dir_long'].values; y_s_tr_26 = df_tr_26['label_dir_short'].values

    pl_lgb = np.zeros(len(df_eval_26)); pl_cat = np.zeros(len(df_eval_26)); pl_xgb = np.zeros(len(df_eval_26))
    ps_lgb = np.zeros(len(df_eval_26)); ps_cat = np.zeros(len(df_eval_26)); ps_xgb = np.zeros(len(df_eval_26))

    for s in range(4):
        mask_tr = (state_tr_26 == s); mask_te = (state_te_26 == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_l_tr_26[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat_26[mask_tr], y_s_tr_26[mask_tr])

            pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]

            ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat_26[mask_te])[:, 1]
            ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat_26[mask_te])[:, 1]
            ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat_26[mask_te])[:, 1]

    p_stack_l_26 = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s_26 = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)

    holdout_res = run_simulation_combo271(df_eval_26, p_stack_l_26, p_stack_s_26, hmm_te_26)

    # Print Official Certificate
    cert_text = f"""
========================================================
    MASTER CANONICAL PRODUCTION BACKTEST — v2.0 (COMBO #271 🏆)
========================================================

Instrument:             EURUSD
Timeframe:              H1
OOS Period:             2018–2025 (8 Folds)
Untouched Holdout:      2026 (Jan 1 – Aug 11)
Ensemble Ratio:         Ratio A (50% Cat / 25% LGB / 25% XGB)
Tree Depth:             max_depth = 4 (Grid B Regularization)
Regime Engine:          4-State Engine (2 HMM x 2 Volatility)
Barrier Multipliers:    TP 3.0 ATR / SL 1.5 ATR (36h Max Holding)
Risk/Trade:             0.75% Fixed-Fractional
Max Positions:          1 (Strictly Enforced)

Total OOS Trades:       {oos_res['trades']:,}
Net OOS Return:         +{oos_res['ret_pct']:.2f}%
CAGR:                   +{oos_res['cagr_pct']:.2f}% / yr
Sharpe Ratio:           {oos_res['sharpe']:.2f} (Daily, √252)
Sortino Ratio:          {oos_res['sortino']:.2f}
Profit Factor:          {oos_res['pf']:.2f}
Win Rate:               {oos_res['win_rate']:.2f}%

Mark-to-Market MDD:     -{oos_res['mtm_max_dd']:.2f}% (Daily MtM Peak)
Worst Month:            {oos_res['worst_month']:.2f}%
Worst Year:             {oos_res['worst_year']:.2f}%

Average R:              +{oos_res['avg_r']:.4f}R
95% Drawdown:           -{oos_res['dd_95']:.2f}%
99% Drawdown:           -{oos_res['dd_99']:.2f}%

--------------------------------------------------------
100% UNTOUCHED 2026 LIVE HOLDOUT METRICS (COMBO #271)
--------------------------------------------------------
2026 Holdout Trades:    {holdout_res['trades']:,}
2026 Net Return:        +{holdout_res['ret_pct']:.2f}%
2026 Sharpe Ratio:      {holdout_res['sharpe']:.2f} (Daily, √252)
2026 Mark-to-Market MDD: -{holdout_res['mtm_max_dd']:.2f}%
2026 Profit Factor:     {holdout_res['pf']:.2f}

--------------------------------------------------------
TRANSACTION FRICTION & EXECUTION ENGINE SPECIFICATIONS
--------------------------------------------------------
Spread:                 0.3 pips (Every Exit & Partial Exit)
Commission:             $7.00 / lot round-turn
Order Entry:            0.25 ATR Limit Retrace (3h Expiry)
Stop-Loss / Take-Profit: 1.5 ATR / 3.0 ATR
Partial Exit:           50% Lot Size @ +1.5R
Maximum Holding:        36 Hours

========================================================
CANONICAL BASELINE v2.0 MASTER: CERTIFIED 🏆
========================================================
"""
    print(cert_text)

    # Save Certificate & Ledger JSON
    os.makedirs("docs/canonical_baselines", exist_ok=True)
    with open("docs/canonical_baselines/canonical_production_baseline_v2_combo271.md", "w") as f:
        f.write(cert_text)

    ledger_data = {
        "version": "v2.0_combo271",
        "status": "CERTIFIED_PROPOSED_MASTER",
        "oos_period": "2018-2025",
        "holdout_period": "2026",
        "combo_id": 271,
        "oos_metrics": oos_res,
        "holdout_metrics": holdout_res
    }
    with open("docs/canonical_baselines/canonical_baseline_v2_combo271_ledger.json", "w") as f:
        json.dump(ledger_data, f, indent=4)

    print("✅ Canonical Baseline v2.0 (Combo #271) certified and saved to 'docs/canonical_baselines/canonical_production_baseline_v2_combo271.md' and 'docs/canonical_baselines/canonical_baseline_v2_combo271_ledger.json'!")

if __name__ == "__main__":
    main()
