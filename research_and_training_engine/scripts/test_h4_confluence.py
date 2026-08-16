import os
import sys
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath("."))
from historical_data_ingestion import DataLoader, DataRequest
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from core_machine_learning.regime_hmm import HMMRegimeDetector
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from xgboost import XGBClassifier
from research_and_training_engine.labeler import TripleBarrierLabeler

def main():
    print("=================================================================================")
    print("  🔬 RESEARCH: TESTING H4 MACRO CONFLUENCE IMPACT ON 2026 HOLDOUT")
    print("=================================================================================\n")

    loader = DataLoader()
    req_1h = DataRequest(symbol="EURUSD", timeframe="1h", start="2014-01-01", end="2026-08-11")
    req_4h = DataRequest(symbol="EURUSD", timeframe="4h", start="2014-01-01", end="2026-08-11")
    
    print("Loading 1H and 4H Data...")
    df_1h = loader.load(req_1h)
    df_4h = loader.load(req_4h)

    print("Building 1H and 4H Feature Matrices...")
    fb = FeatureMatrixBuilder()
    df_feat_1h = fb.build(df_1h.copy())
    df_feat_4h = fb.build(df_4h.copy())

    # Safely shift 4H features by 4 hours to prevent lookahead bias
    # (Assuming 4H bars are labeled by their open time, they close 4 hours later)
    df_feat_4h.index = df_feat_4h.index + pd.Timedelta(hours=4)
    
    # Select key macro confluence features
    macro_cols = [
        'feat_trend_ema50_slope', 'feat_trend_ema200_slope', 
        'feat_vol_atr_pct', 'feat_trend_adx', 'feat_struct_dist_vwap'
    ]
    df_macro = df_feat_4h[macro_cols].add_suffix('_H4')

    # Merge into 1H
    df_joined = df_feat_1h.join(df_macro, how='left')
    df_joined[df_macro.columns] = df_joined[df_macro.columns].ffill()

    # Re-calculate required columns for labeler & regime
    atr_series = df_joined['feat_vol_atr'] if 'feat_vol_atr' in df_joined.columns else df_joined['high'] - df_joined['low']
    df_joined['feat_vol_atr'] = atr_series
    df_joined['feat_vol_atr_pct'] = atr_series.expanding(min_periods=100).rank(pct=True).bfill().ffill().fillna(50.0) * 100.0

    print("Generating Labels...")
    tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
    df_lbl = tb_lab.label(df_joined.copy())
    df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
    df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)
    
    all_feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
    df_lbl[all_feat_cols] = df_lbl[all_feat_cols].bfill().ffill().fillna(0.0)

    mask_2026 = (df_joined.index >= "2026-01-01") & (df_joined.index <= "2026-08-11")
    df_eval_26 = df_joined[mask_2026].copy()

    train_m_26 = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= "2025-12-31")
    df_tr_26 = df_lbl[train_m_26].dropna(subset=['label_dir_long']).copy()

    print("Fitting HMM...")
    fold_seed = 42
    hmm_detector = HMMRegimeDetector(n_components=2, random_state=fold_seed)
    hmm_detector.fit(df_tr_26)
    hmm_tr_26 = hmm_detector.predict(df_tr_26)
    hmm_te_26 = hmm_detector.predict(df_eval_26)

    tr_v_26 = df_tr_26['feat_vol_atr_pct'].values; te_v_26 = df_eval_26['feat_vol_atr_pct'].values
    v_tr_26 = np.zeros(len(tr_v_26), dtype=int); v_tr_26[tr_v_26 >= 50.0] = 1
    v_te_26 = np.zeros(len(te_v_26), dtype=int); v_te_26[te_v_26 >= 50.0] = 1
    state_tr_26 = (hmm_tr_26 * 2) + v_tr_26; state_te_26 = (hmm_te_26 * 2) + v_te_26

    X_tr = df_tr_26[all_feat_cols].values; X_te = df_eval_26[all_feat_cols].values
    y_l = df_tr_26['label_dir_long'].values; y_s = df_tr_26['label_dir_short'].values

    pl_lgb = np.zeros(len(df_eval_26)); pl_cat = np.zeros(len(df_eval_26)); pl_xgb = np.zeros(len(df_eval_26))
    ps_lgb = np.zeros(len(df_eval_26)); ps_cat = np.zeros(len(df_eval_26)); ps_xgb = np.zeros(len(df_eval_26))

    print(f"Training on {len(all_feat_cols)} features (including {len(df_macro.columns)} H4 Confluence features)...")
    for s in range(4):
        m_tr = (state_tr_26 == s); m_te = (state_te_26 == s)
        if not np.any(m_te): continue
        if np.sum(m_tr) >= 20:
            ml_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr[m_tr], y_l[m_tr])
            ml_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=-1, verbose=False).fit(X_tr[m_tr], y_l[m_tr])
            ml_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr[m_tr], y_l[m_tr])

            ms_lgb = LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, verbose=-1).fit(X_tr[m_tr], y_s[m_tr])
            ms_cat = CatBoostClassifier(iterations=100, depth=4, learning_rate=0.03, random_seed=fold_seed, thread_count=-1, verbose=False).fit(X_tr[m_tr], y_s[m_tr])
            ms_xgb = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.03, random_state=fold_seed, n_jobs=-1, eval_metric="logloss").fit(X_tr[m_tr], y_s[m_tr])

            pl_lgb[m_te] = ml_lgb.predict_proba(X_te[m_te])[:, 1]
            pl_cat[m_te] = ml_cat.predict_proba(X_te[m_te])[:, 1]
            pl_xgb[m_te] = ml_xgb.predict_proba(X_te[m_te])[:, 1]

            ps_lgb[m_te] = ms_lgb.predict_proba(X_te[m_te])[:, 1]
            ps_cat[m_te] = ms_cat.predict_proba(X_te[m_te])[:, 1]
            ps_xgb[m_te] = ms_xgb.predict_proba(X_te[m_te])[:, 1]

    p_stack_l = (pl_cat * 0.5) + (pl_lgb * 0.25) + (pl_xgb * 0.25)
    p_stack_s = (ps_cat * 0.5) + (ps_lgb * 0.25) + (ps_xgb * 0.25)

    hmm_te_26_arr = np.zeros(len(df_eval_26))
    hmm_te_26_arr[:] = hmm_te_26

    def custom_run(df_eval, p_l, p_s, hmm_arr):
        req_p_arr = np.where(hmm_arr == 1.0, 0.42, 0.38) # 0.38 Trend, 0.42 Range
        
        total_bars = len(df_eval)
        timestamps = df_eval.index
        closes = df_eval['close'].values; highs = df_eval['high'].values; lows = df_eval['low'].values; atrs = df_eval['feat_vol_atr'].values
        hours = np.array([ts.hour for ts in timestamps])
        trading_window = ~((hours >= 13) & (hours <= 16))
        vol_pass = (df_eval['feat_vol_atr_pct'].values >= 40.0)

        signals_buy = (p_l >= req_p_arr) & vol_pass & trading_window
        signals_sell = (p_s >= req_p_arr) & vol_pass & trading_window

        pip_size = 0.0001; friction_pips = 0.3; comm_per_lot = 7.0; risk_pct = 0.0075
        active_positions = []; pending_orders = []; closed_trades = []; current_equity = 10000.0; daily_equity = {}

        signals_arr = np.full(total_bars, "NONE", dtype=object)
        for i in range(total_bars):
            if signals_buy[i]: signals_arr[i] = "BUY"
            elif signals_sell[i]: signals_arr[i] = "SELL"

        for i in range(total_bars):
            timestamp = timestamps[i]; close = closes[i]; high = highs[i]; low = lows[i]
            atr = atrs[i] if not np.isnan(atrs[i]) else 0.0012

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
                elif (timestamp - entry_time).total_seconds() / 3600.0 >= 36.0: stop_out = True; exit_price = close
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

                    pos['pnl_usd'] = total_trade_net
                    current_equity += rem_net
                    closed_trades.append(pos)

                    if signals_arr[i] == opposite_sig:
                        pending_orders.append({"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr})
                else:
                    remaining_positions.append(pos)

            active_positions = remaining_positions

            remaining_orders = []
            for p_order in pending_orders:
                if (i - p_order['signal_idx']) > 3: continue
                p_dir = p_order['direction']; p_limit = p_order['limit_price']; p_atr = p_order['atr']

                filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                if filled and len(active_positions) < 3:
                    sl_pips = (p_atr / pip_size) * 1.5; tp_pips = (p_atr / pip_size) * 3.0; initial_sl_dist = (p_atr / pip_size) * 1.5 * pip_size
                    entry_price = p_limit
                    sl_price = entry_price - (p_atr * 1.5) if p_dir == 'BUY' else entry_price + (p_atr * 1.5)
                    tp_price = entry_price + (p_atr * 3.0) if p_dir == 'BUY' else entry_price - (p_atr * 3.0)

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

            if len(active_positions) + len(pending_orders) < 3 and signals_arr[i] in ('BUY', 'SELL'):
                sig = signals_arr[i]
                retrace_pips = (atr / pip_size) * 0.25
                limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
                pending_orders.append({'direction': sig, 'limit_price': limit_price, 'signal_idx': i, 'atr': atr})

            daily_equity[str(timestamp.date())] = current_equity

        pnls = [t['pnl_usd'] for t in closed_trades]
        wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
        net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0

        eq_series = pd.Series(daily_equity)
        eq_series.index = pd.to_datetime(eq_series.index)
        daily_rets = eq_series.pct_change().dropna()

        sharpe_daily = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 0 and daily_rets.std() > 0 else 0.0
        gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0
        pf = gross_win / gross_loss
        win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0

        peaks = eq_series.cummax()
        dds = (eq_series - peaks) / peaks * 100.0
        mtm_max_dd = abs(dds.min())

        return {
            'trades': len(closed_trades),
            'ret_pct': ret_pct,
            'sharpe': sharpe_daily,
            'mtm_max_dd': mtm_max_dd,
            'pf': pf
        }

    res = custom_run(df_eval_26, p_stack_l, p_stack_s, hmm_te_26_arr)
    print("=================================================================================")
    print("  🏆 H4 CONFLUENCE HOLDOUT METRICS (2026)")
    print("=================================================================================")
    print(f"Trades: {res['trades']}")
    print(f"Return: {res['ret_pct']:.2f}%")
    print(f"MDD: -{res['mtm_max_dd']:.2f}%")
    print(f"Sharpe: {res['sharpe']:.2f}")
    print(f"Profit Factor: {res['pf']:.2f}")
    print("=================================================================================")

if __name__ == "__main__":
    main()
