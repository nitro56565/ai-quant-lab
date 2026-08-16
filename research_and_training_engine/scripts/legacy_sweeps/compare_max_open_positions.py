"""
Controlled Ablation Test: max_open_positions = 1 (Baseline) vs max_open_positions = 3 (Overlapping Trades)
Evaluates 8-Fold Walk-Forward OOS Gauntlet (2018-2025 EURUSD H1) under 0.75% Risk per trade.
"""

import os, sys, time, warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier

sys.path.insert(0, os.path.abspath("."))

from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from research_and_training_engine.labeler import TripleBarrierLabeler
from core_machine_learning.regime_hmm import HMMRegimeDetector

def process_fold(yr, df_lbl, all_feat_cols):
    warnings.filterwarnings("ignore")
    fold_seed = 42
    np.random.seed(fold_seed)

    train_end_year = yr - 1
    train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
    test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

    df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
    df_te = df_lbl[test_m].copy()

    hmm_detector = HMMRegimeDetector(n_components=3, random_state=fold_seed)
    hmm_detector.fit(df_tr)
    hmm_tr = hmm_detector.predict(df_tr)
    hmm_te = hmm_detector.predict(df_te)

    tr_v = df_tr['feat_vol_atr_pct'].values; te_v = df_te['feat_vol_atr_pct'].values
    v_tr = np.zeros(len(tr_v), dtype=int); v_tr[tr_v >= 33.33] = 1; v_tr[tr_v >= 66.67] = 2
    v_te = np.zeros(len(te_v), dtype=int); v_te[te_v >= 33.33] = 1; v_te[te_v >= 66.67] = 2

    state_tr = (hmm_tr * 3) + v_tr; state_te = (hmm_te * 3) + v_te

    X_tr_mat = df_tr[all_feat_cols].values; X_te_mat = df_te[all_feat_cols].values
    y_l_tr = df_tr['label_dir_long'].values; y_s_tr = df_tr['label_dir_short'].values

    pl_lgb = np.zeros(len(df_te)); pl_cat = np.zeros(len(df_te)); pl_xgb = np.zeros(len(df_te))
    ps_lgb = np.zeros(len(df_te)); ps_cat = np.zeros(len(df_te)); ps_xgb = np.zeros(len(df_te))

    for s in range(9):
        mask_tr = (state_tr == s); mask_te = (state_te == s)
        if not np.any(mask_te): continue
        if np.sum(mask_tr) >= 30:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_l_tr[mask_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, verbose=-1).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=5, learning_rate=0.03, random_seed=fold_seed, thread_count=1, verbose=False).fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.03, random_state=fold_seed, n_jobs=1, eval_metric="logloss").fit(X_tr_mat[mask_tr], y_s_tr[mask_tr])

            pl_lgb[mask_te] = ml_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_cat[mask_te] = ml_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            pl_xgb[mask_te] = ml_xgb.predict_proba(X_te_mat[mask_te])[:, 1]

            ps_lgb[mask_te] = ms_lgb.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_cat[mask_te] = ms_cat.predict_proba(X_te_mat[mask_te])[:, 1]
            ps_xgb[mask_te] = ms_xgb.predict_proba(X_te_mat[mask_te])[:, 1]
        else:
            pl_lgb[mask_te] = 0.30; pl_cat[mask_te] = 0.30; pl_xgb[mask_te] = 0.30
            ps_lgb[mask_te] = 0.30; ps_cat[mask_te] = 0.30; ps_xgb[mask_te] = 0.30

    p_stack_l = (pl_lgb + pl_cat + pl_xgb) / 3.0
    p_stack_s = (ps_lgb + ps_cat + ps_xgb) / 3.0
    return df_te.index, p_stack_l, p_stack_s, hmm_te

def run_simulation(df_eval, p_l, p_s, hmm_arr, max_open_pos=1, initial_cap=10000.0):
    total_bars = len(df_eval)
    timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window

    pip_size = 0.0001
    friction_pips = 0.3
    risk_pct = 0.0075

    active_positions = []  # List of open position dicts
    pending_orders = []    # List of pending order dicts
    closed_trades = []
    current_equity = initial_cap
    daily_equity = {}

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]; atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        # 1. Evaluate Active Open Positions (Exit Check)
        remaining_positions = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0; exit_reason = None

            opposite_sig = None
            if direction == 'BUY' and signals_sell[i]:
                opposite_sig = 'SELL'
            elif direction == 'SELL' and signals_buy[i]:
                opposite_sig = 'BUY'
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

            # Partial Exit @ +1.5R
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_net = (partial_pips * (partial_lots * 10.0)) - (7.0 * partial_lots)
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            if opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_net = (rem_pips * (rem_lots * 10.0)) - (7.0 * rem_lots)
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                pos['exit_time'] = timestamp; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason
                pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                current_equity += rem_net
                closed_trades.append(pos)
            else:
                remaining_positions.append(pos)

        active_positions = remaining_positions

        # 2. Evaluate Pending Limit Orders (Fill Check)
        remaining_orders = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3:
                continue # Expired
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']
            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
            
            if filled and len(active_positions) < max_open_pos:
                sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5
                initial_sl_dist = sl_pips * pip_size
                entry_price = p_limit
                sl_price = entry_price - initial_sl_dist if p_dir == 'BUY' else entry_price + initial_sl_dist
                tp_price = entry_price + (tp_pips * pip_size) if p_dir == 'BUY' else entry_price - (tp_pips * pip_size)

                sl_dist_pips = sl_pips
                lots = round((current_equity * risk_pct) / (sl_dist_pips * 10.0), 2) if sl_dist_pips > 0 else 0.31
                lots = max(0.01, lots)

                new_pos = {
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0
                }
                active_positions.append(new_pos)
            elif not filled:
                remaining_orders.append(p_order)

        pending_orders = remaining_orders

        # 3. Process New Signal Generation (Max Open Position Guard Check)
        if len(active_positions) + len(pending_orders) < max_open_pos:
            sig = 'BUY' if signals_buy[i] else ('SELL' if signals_sell[i] else None)
            if sig:
                limit_price = close - (0.25 * atr) if sig == 'BUY' else close + (0.25 * atr)
                pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

        dt_str = str(timestamp)[:10]
        daily_equity[dt_str] = current_equity

    # Compute Performance Metrics
    net_return_pct = ((current_equity - initial_cap) / initial_cap) * 100.0
    wins = [t for t in closed_trades if t.get('pnl_usd', 0.0) > 0]
    losses = [t for t in closed_trades if t.get('pnl_usd', 0.0) <= 0]

    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
    gross_win = sum([t['pnl_usd'] for t in wins])
    gross_loss = abs(sum([t['pnl_usd'] for t in losses]))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else 0.0

    eq_series = pd.Series(daily_equity)
    daily_rets = eq_series.pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0

    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd_pct = abs(dd.min()) * 100.0

    return {
        'max_open_pos': max_open_pos,
        'trades_count': len(closed_trades),
        'net_return_pct': net_return_pct,
        'profit_factor': profit_factor,
        'sharpe': sharpe,
        'max_dd_pct': max_dd_pct,
        'win_rate': win_rate
    }

def main():
    print("=================================================================================")
    print("  🔬 CONTROLLED ABLATION: max_open_positions = 1 (Baseline) vs 3 (Overlapping)")
    print("=================================================================================\n")

    loader = DataLoader()
    symbol = "EURUSD"
    req_full = DataRequest(symbol=symbol, timeframe="1h", start="2014-01-01", end="2025-12-31")
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

    eval_mask_oos = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval_oos = df_feat[eval_mask_oos].copy()
    years_oos = list(range(2018, 2026))

    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    results_folds = Parallel(n_jobs=safe_cores)(
        delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in years_oos
    )

    p_stack_l_oos = np.zeros(len(df_eval_oos))
    p_stack_s_oos = np.zeros(len(df_eval_oos))
    hmm_oos = np.zeros(len(df_eval_oos))

    for te_indices, pl_fold, ps_fold, hmm_fold in results_folds:
        fold_eval_indices = [df_eval_oos.index.get_loc(idx) for idx in te_indices if idx in df_eval_oos.index]
        p_stack_l_oos[fold_eval_indices] = pl_fold
        p_stack_s_oos[fold_eval_indices] = ps_fold
        hmm_oos[fold_eval_indices] = hmm_fold

    print("▶ Running Backtest for Baseline (max_open_positions = 1)...")
    res1 = run_simulation(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos, max_open_pos=1)

    print("▶ Running Backtest for Overlapping Variant (max_open_positions = 3)...")
    res3 = run_simulation(df_eval_oos, p_stack_l_oos, p_stack_s_oos, hmm_oos, max_open_pos=3)

    print("\n=================================================================================")
    print("  📊 COMPARATIVE RESULTS (2018–2025 EURUSD 8-FOLD OOS GAUNTLET)")
    print("=================================================================================")
    print(f"{'Metric':<25} | {'Baseline (max=1)':<20} | {'Ablation (max=3)':<20}")
    print("-" * 75)
    print(f"{'Total OOS Trades':<25} | {res1['trades_count']:<20,d} | {res3['trades_count']:<20,d}")
    print(f"{'Net Return (%)':<25} | +{res1['net_return_pct']:<19.2f}% | +{res3['net_return_pct']:<19.2f}%")
    print(f"{'Sharpe Ratio':<25} | {res1['sharpe']:<20.2f} | {res3['sharpe']:<20.2f}")
    print(f"{'Profit Factor':<25} | {res1['profit_factor']:<20.2f} | {res3['profit_factor']:<20.2f}")
    print(f"{'Max Drawdown (%)':<25} | -{res1['max_dd_pct']:<19.2f}% | -{res3['max_dd_pct']:<19.2f}%")
    print(f"{'Win Rate (%)':<25} | {res1['win_rate']:<20.2f}% | {res3['win_rate']:<20.2f}%")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
