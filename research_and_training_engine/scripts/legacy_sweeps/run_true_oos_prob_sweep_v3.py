import os
import sys
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

def calculate_mdd_duration(eq_series):
    peaks = eq_series.cummax()
    drawdowns = (eq_series - peaks) / peaks * 100.0
    underwater = drawdowns < 0
    underwater_groups = (underwater != underwater.shift()).cumsum()
    mdd_durations = []
    for k, v in eq_series.groupby(underwater_groups):
        if drawdowns.loc[v.index].min() < 0:
            duration = (v.index[-1] - v.index[0]).days
            mdd_durations.append(duration)
    return max(mdd_durations) if mdd_durations else 0

def calculate_max_losing_streak(pnls):
    max_streak = 0; current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            if current_streak > max_streak: max_streak = current_streak
        else: current_streak = 0
    return max_streak

def process_fold(yr, df_lbl, all_feat_cols):
    warnings.filterwarnings("ignore")
    fold_seed = 42
    np.random.seed(fold_seed)

    train_end_year = yr - 1
    train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
    test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_m].copy()

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

    p_stack_l = (pl_cat * 0.5) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s = (ps_cat * 0.5) + (ps_lgb * 0.25) + (ps_xgb * 0.25)
    return df_te.index, p_stack_l, p_stack_s, hmm_te

def run_simulation(df_eval, p_l, p_s, hmm_arr, trend_p, range_p, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values
    atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    
    # Official v3.1 Logic uses > 40 on BOTH
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    req_p_arr = np.where(hmm_arr == 1, range_p, trend_p)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & vol_pass & trading_window

    pip_size = 0.0001
    friction_pips = 0.3
    comm_per_lot = 7.0
    risk_pct = 0.0075
    max_open_pos = 3
    max_holding_bars = 36.0

    active_positions = []; pending_orders = []; closed_trades = []; current_equity = initial_cap; daily_equity = {}

    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]
        atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        # 1. Active Position Evaluation
        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0

            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = comm_per_lot * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= max_holding_bars: stop_out = True; exit_price = close
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size)
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size)
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_gross = rem_pips * (rem_lots * 10.0); rem_comm = comm_per_lot * rem_lots; rem_net = rem_gross - rem_comm
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)
                
                pos['r_multiple'] = total_trade_net / (pos['initial_lots'] * (pos['initial_sl_dist'] / pip_size) * 10.0) if pos['initial_sl_dist'] > 0 else 0.0
                pos['pnl_usd'] = total_trade_net
                current_equity += rem_net
                closed_trades.append(pos)
                
                if signals_arr[i] == opposite_sig:
                    pending_orders.append({"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr})
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        # 2. Pending Limit Order Fill Check
        remaining_orders = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3: continue
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']
            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)

            if filled and len(active_positions) < max_open_pos:
                # Corrected sizing bug (1.5 ATR for both)
                sl_pips = (p_atr / pip_size) * 1.5; tp_pips = (p_atr / pip_size) * 3.0; initial_sl_dist = sl_pips * pip_size
                entry_price = p_limit
                sl_price = entry_price - initial_sl_dist if p_dir == 'BUY' else entry_price + initial_sl_dist
                tp_price = entry_price + (tp_pips * pip_size) if p_dir == 'BUY' else entry_price - (tp_pips * pip_size)
                
                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                active_positions.append({
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0
                })
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

    # Compute Metrics
    pnls = [t['pnl_usd'] for t in closed_trades]
    r_multiples = [t.get('r_multiple', 0.0) for t in closed_trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    total_trades = len(closed_trades)
    net_pnl = sum(pnls); ret_pct = (net_pnl / initial_cap) * 100.0

    eq_series = pd.Series(daily_equity)
    eq_series.index = pd.to_datetime(eq_series.index)
    daily_rets = eq_series.pct_change().dropna()

    num_years = (timestamps[-1] - timestamps[0]).days / 365.25
    cagr_pct = (((current_equity / initial_cap) ** (1.0 / max(1.0, num_years))) - 1.0) * 100.0

    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
    downside_rets = daily_rets[daily_rets < 0]
    sortino = (daily_rets.mean() / downside_rets.std() * np.sqrt(252)) if len(downside_rets) > 0 and downside_rets.std() > 0 else 0.0

    gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
    pf = gross_win / gross_loss
    win_rate = (len(wins) / total_trades * 100.0) if total_trades else 0.0
    avg_r = np.mean(r_multiples) if r_multiples else 0.0

    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    mtm_max_dd = abs(dds.min()) if len(dds) > 0 else 0.0
    
    max_streak = calculate_max_losing_streak(pnls)
    mdd_dur = calculate_mdd_duration(eq_series)
    
    monthly_rets = eq_series.resample('ME').last().pct_change().dropna() * 100.0
    yearly_rets = eq_series.resample('YE').last().pct_change().dropna() * 100.0
    
    worst_month = monthly_rets.min() if len(monthly_rets) > 0 else 0.0
    worst_year = yearly_rets.min() if len(yearly_rets) > 0 else 0.0
    profitable_years = len(yearly_rets[yearly_rets > 0])

    # Add extra metrics required by user output
    dd_95 = abs(np.percentile(dds, 5)) if len(dds) > 0 else 0.0
    dd_99 = abs(np.percentile(dds, 1)) if len(dds) > 0 else 0.0

    return {
        'trend_p': trend_p, 'range_p': range_p,
        'trades': total_trades, 'net_ret': ret_pct, 'cagr': cagr_pct,
        'sharpe': sharpe, 'sortino': sortino, 'pf': pf,
        'win_rate': win_rate, 'avg_r': avg_r, 'mdd': mtm_max_dd,
        'max_streak': max_streak, 'mdd_dur': mdd_dur,
        'worst_month': worst_month, 'worst_year': worst_year,
        'prof_years': f"{profitable_years}/{len(yearly_rets)}",
        'dd_95': dd_95, 'dd_99': dd_99
    }

def main():
    print("Loading Data and Building Features for v3.1 True-OOS Probability Threshold Sweep...")
    loader = DataLoader()
    req_full = DataRequest(symbol="EURUSD", timeframe="1h", start="2014-01-01", end="2026-08-11")
    df_full = loader.load(req_full)

    feat_builder = FeatureMatrixBuilder()
    df_feat = feat_builder.build(df_full.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    expanding_rank = atr_series.expanding(min_periods=100).rank(pct=True) * 100.0
    df_feat['feat_vol_atr_pct'] = expanding_rank.bfill().ffill().fillna(50.0)

    # Official Baseline v3.1 labeler uses 2.5 ATR TP and 24 hours max holding
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

    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("▶ Executing 8-Fold OOS Walk-Forward Model Training (2018-2025) ONLY ONCE for generating True OOS Probabilities...", flush=True)
    results_folds = Parallel(n_jobs=safe_cores)(delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos)

    p_stack_l_oos = np.zeros(len(df_eval_oos))
    p_stack_s_oos = np.zeros(len(df_eval_oos))
    hmm_oos = np.zeros(len(df_eval_oos))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[fold_eval_indices] = pl_fold
        p_stack_s_oos[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    trend_thresholds = [0.32, 0.34, 0.36, 0.38, 0.40]
    range_thresholds = [0.38, 0.40, 0.42, 0.44, 0.46]

    oos_results = []
    print("\nRunning OOS Grid Search for all 25 combinations on the True OOS predictions...")
    for t_p in trend_thresholds:
        for r_p in range_thresholds:
            res = run_simulation(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos, t_p, r_p)
            oos_results.append(res)
            
    oos_results.sort(key=lambda x: x['mdd'])
    top_5 = oos_results[:5]
    top_5.sort(key=lambda x: x['cagr'], reverse=True)
    challenger = top_5[0]

    baseline = None
    for r in oos_results:
        if r['trend_p'] == 0.36 and r['range_p'] == 0.42:
            baseline = r
            break
            
    print("\n\n### 2018-2025 TRUE OOS Deep Probability Sweep Results (All 25 Combinations)")
    
    headers = ["Trend", "Range", "Trades", "NetRet%", "CAGR%", "MDD%", "Sharpe", "Sortino", "PF", "Win%", "AvgR", "MaxLoss", "MDD(d)", "WorstYr%", "ProfYrs"]
    print("-" * 140)
    print("".join(f"{h:<9}" for h in headers))
    print("-" * 140)
    
    oos_sorted = sorted(oos_results, key=lambda x: (x['trend_p'], x['range_p']))
    for r in oos_sorted:
        row = [f"{r['trend_p']:.2f}", f"{r['range_p']:.2f}", f"{r['trades']}", 
               f"{r['net_ret']:.1f}", f"{r['cagr']:.1f}", f"{r['mdd']:.1f}", 
               f"{r['sharpe']:.2f}", f"{r['sortino']:.2f}", f"{r['pf']:.2f}", 
               f"{r['win_rate']:.1f}", f"{r['avg_r']:.3f}", f"{r['max_streak']}", 
               f"{r['mdd_dur']}", f"{r['worst_year']:.1f}", f"{r['prof_years']}"]
        print("".join(f"{str(v):<9}" for v in row))
        
    print("\n\n==========================================================================================")
    print(f"🏆 CHALLENGER SELECTED (Pareto-Optimal TRUE OOS): Trend={challenger['trend_p']}, Range={challenger['range_p']}")
    print(f"🔒 FROZEN BASELINE (Current Prod v3.1): Trend=0.36, Range=0.42")
    print("==========================================================================================")
    
    # 2. 2026 Untouched Live Holdout
    print("\n▶ Executing 100% Untouched 2026 Live Holdout Fold (Jan 1 - Aug 11, 2026)...", flush=True)
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

    p_stack_l_26 = (pl_cat * 0.5) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s_26 = (ps_cat * 0.5) + (ps_lgb * 0.25) + (ps_xgb * 0.25)

    chal_26 = run_simulation(df_eval_26, p_stack_l_26, p_stack_s_26, hmm_te_26, challenger['trend_p'], challenger['range_p'])
    
    # Write challenger info to a file for easy extraction later
    with open("challenger_details.json", "w") as f:
        json.dump({"oos": challenger, "holdout": chal_26}, f)

if __name__ == "__main__":
    main()

