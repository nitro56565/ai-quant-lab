import os
import sys
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

def run_sim(df_eval, p_l, p_s, hmm_arr, use_sizing_bug=False):
    total_bars = len(df_eval); timestamps = df_eval.index
    closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values
    atrs = df_eval['feat_vol_atr'].values
    hours = np.array([ts.hour for ts in timestamps])
    trading_window = ~((hours >= 13) & (hours <= 16))
    vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)
    
    # Baseline 0.36/0.42
    req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.36)

    signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
    signals_sell = (p_s >= req_p_arr) & trading_window


    pip_size = 0.0001; friction_pips = 0.3; risk_pct = 0.0075
    active_positions = []; pending_orders = []; closed_trades = []; current_equity = 10000.0; daily_equity = {}
    
    signals_arr = np.full(total_bars, "NONE", dtype=object)
    for i in range(total_bars):
        if signals_buy[i]: signals_arr[i] = "BUY"
        elif signals_sell[i]: signals_arr[i] = "SELL"

    for i in range(total_bars):
        timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]
        atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

        rem_pos = []
        for pos in active_positions:
            direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
            sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']
            stop_out = False; exit_price = 0.0
            opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
            
            # Partial Exit (50% @ +1.5R)
            floating_pnl_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
            r_floating = floating_pnl_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0
            if not pos['partial_taken'] and r_floating >= 1.5:
                partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                partial_gross = partial_pips * (partial_lots * 10.0); partial_comm = 7.0 * partial_lots; partial_net = partial_gross - partial_comm
                pos['partial_pnl_usd'] = partial_net; current_equity += partial_net

            # Exit logic
            if signals_arr[i] == opposite_sig: stop_out = True; exit_price = close
            elif (timestamp - entry_time).total_seconds() / 3600.0 >= 36.0: stop_out = True; exit_price = close
            elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size)
            elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size)
            elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price
            elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price

            if stop_out:
                rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                rem_pips -= friction_pips
                rem_lots = pos['active_lots']
                rem_net = (rem_pips * rem_lots * 10.0) - (7.0 * rem_lots)
                total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)
                pos['pnl_usd'] = total_trade_net
                current_equity += rem_net
                closed_trades.append(pos)
                if signals_arr[i] == opposite_sig:
                    pending_orders.append({"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr})
            else: rem_pos.append(pos)
        active_positions = rem_pos

        # Fill pending
        rem_ord = []
        for p_order in pending_orders:
            if (i - p_order['signal_idx']) > 3: continue
            p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']
            filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
            if filled and len(active_positions) < 3:
                # Sizing logic
                if use_sizing_bug:
                    # The official canonical script sizing bug!
                    sl_pips = (p_atr / pip_size) * 2.0
                else:
                    # Correct sizing!
                    sl_pips = (p_atr / pip_size) * 1.5
                    
                entry_price = p_limit
                sl_price = entry_price - (p_atr * 1.5) if p_dir == 'BUY' else entry_price + (p_atr * 1.5)
                tp_price = entry_price + (p_atr * 3.0) if p_dir == 'BUY' else entry_price - (p_atr * 3.0)
                initial_sl_dist = (p_atr * 1.5)
                
                risk_amt = current_equity * risk_pct
                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * 10.0))), 2)

                active_positions.append({
                    'entry_time': timestamp, 'direction': p_dir, 'entry_price': entry_price,
                    'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0
                })
            elif not filled: rem_ord.append(p_order)
        pending_orders = rem_ord

        if len(active_positions) + len(pending_orders) < 3 and signals_arr[i] in ('BUY', 'SELL'):
            sig = signals_arr[i]
            limit_price = close - (0.25 * atr) if sig == 'BUY' else close + (0.25 * atr)
            pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

        daily_equity[str(timestamp.date())] = current_equity

    pnls = [t['pnl_usd'] for t in closed_trades]
    net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0
    eq_series = pd.Series(daily_equity)
    peaks = eq_series.cummax()
    dds = (eq_series - peaks) / peaks * 100.0
    return len(closed_trades), ret_pct, abs(dds.min())

if __name__ == "__main__":
    loader = DataLoader()
    df_full = loader.load(DataRequest(symbol="EURUSD", timeframe="1h", start="2014-01-01", end="2025-12-31"))
    fb = FeatureMatrixBuilder(); df_feat = fb.build(df_full.copy())
    atr_series = df_feat['feat_vol_atr'] if 'feat_vol_atr' in df_feat.columns else df_feat['high'] - df_feat['low']
    df_feat['feat_vol_atr'] = atr_series
    df_feat['feat_vol_atr_pct'] = atr_series.expanding(min_periods=100).rank(pct=True).bfill().ffill().fillna(50.0) * 100.0
    
    tb_lab = TripleBarrierLabeler(tp_atr_mult=3.0, sl_atr_mult=1.5, max_holding_bars=36)
    df_lbl = tb_lab.label(df_feat.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)
    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    df_eval_oos = df_feat[(df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")].copy()
    
    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    results = Parallel(n_jobs=safe_cores)(delayed(process_fold)(yr, df_lbl, all_feat_cols) for yr in range(2018, 2026))

    pl = np.zeros(len(df_eval_oos)); ps = np.zeros(len(df_eval_oos)); hm = np.zeros(len(df_eval_oos))
    for ti, l, s, h in results:
        idx = [df_eval_oos.index.get_loc(i) for i in ti if i in df_eval_oos.index]
        pl[idx] = l; ps[idx] = s; hm[idx] = h

    t1, r1, m1 = run_sim(df_eval_oos, pl, ps, hm, use_sizing_bug=True)
    t2, r2, m2 = run_sim(df_eval_oos, pl, ps, hm, use_sizing_bug=False)
    
    print("=" * 80)
    print("1) Official Baseline Script (WITH 2.0 ATR sizing bug):")
    print(f"Trades: {t1}, Return: {r1:.2f}%, MDD: -{m1:.2f}%")
    print("\n2) Correct Baseline True OOS (WITH 1.5 ATR true sizing):")
    print(f"Trades: {t2}, Return: {r2:.2f}%, MDD: -{m2:.2f}%")
    print("=" * 80)
