"""
Stage 16 Follow-Up: 5-Pair Portfolio (Excluding USDCHF) with USD-Factor Exposure Capping.
Evaluates portfolio performance when USDCHF is removed and Net USD Directional Exposure is capped at 1.0%.
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

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import TripleBarrierLabeler
from ai_engine.regime_hmm import HMMRegimeDetector

# 5-Pair Portfolio (Excluding Fragile USDCHF)
ASSETS_5 = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

BASE_FRICTION_PIPS = {
    "EURUSD": 0.3,
    "GBPUSD": 0.5,
    "USDJPY": 0.4,
    "AUDUSD": 0.5,
    "USDCAD": 0.6,
}

USD_FACTOR_MAP = {
    ("EURUSD", "BUY"): -1,  ("EURUSD", "SELL"): +1,
    ("GBPUSD", "BUY"): -1,  ("GBPUSD", "SELL"): +1,
    ("AUDUSD", "BUY"): -1,  ("AUDUSD", "SELL"): +1,
    ("USDJPY", "BUY"): +1,  ("USDJPY", "SELL"): -1,
    ("USDCAD", "BUY"): +1,  ("USDCAD", "SELL"): -1,
}

def process_asset_predictions(symbol):
    warnings.filterwarnings("ignore")
    loader = DataLoader()
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

    eval_mask = (df_feat.index >= "2018-01-01") & (df_feat.index <= "2025-12-31")
    df_eval = df_feat[eval_mask].copy()
    total_h1_bars = len(df_eval)
    years_oos = list(range(2018, 2026))

    p_stack_l = np.zeros(total_h1_bars)
    p_stack_s = np.zeros(total_h1_bars)
    hmm_oos = np.zeros(total_h1_bars)

    for yr in years_oos:
        fold_seed = 42
        np.random.seed(fold_seed)
        train_end_year = yr - 1
        train_m = (df_lbl.index >= "2014-01-01") & (df_lbl.index <= f"{train_end_year}-12-31")
        test_m = (df_lbl.index >= f"{yr}-01-01") & (df_lbl.index <= f"{yr}-12-31")

        df_tr = df_lbl[train_m].dropna(subset=['label_dir_long']).copy()
        df_te = df_lbl[test_m].copy()

        if len(df_te) == 0 or len(df_tr) < 100: continue

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

        fold_eval_indices = [df_eval.index.get_loc(idx) for idx in df_te.index if idx in df_eval.index]
        p_stack_l[fold_eval_indices] = (pl_lgb + pl_cat + pl_xgb) / 3.0
        p_stack_s[fold_eval_indices] = (ps_lgb + ps_cat + ps_xgb) / 3.0
        hmm_oos[fold_eval_indices] = hmm_te

    df_eval['p_stack_l'] = p_stack_l
    df_eval['p_stack_s'] = p_stack_s
    df_eval['hmm_state'] = hmm_oos
    return symbol, df_eval

def run_5pair_test():
    safe_cores = max(1, (os.cpu_count() or 4) - 2)
    print("=================================================================================", flush=True)
    print("  🚀 5-PAIR PORTFOLIO TEST (EXCLUDING FRAGILE USDCHF)", flush=True)
    print("=================================================================================", flush=True)

    t0 = time.time()
    asset_data_list = Parallel(n_jobs=safe_cores)(
        delayed(process_asset_predictions)(sym) for sym in ASSETS_5
    )

    asset_dfs = {sym: df for sym, df in asset_data_list}

    master_index = asset_dfs["EURUSD"].index
    for sym in ASSETS_5:
        master_index = master_index.intersection(asset_dfs[sym].index)
    master_index = master_index.sort_values()
    total_bars = len(master_index)

    asset_closes = {sym: asset_dfs[sym].loc[master_index, 'close'].values for sym in ASSETS_5}
    asset_highs = {sym: asset_dfs[sym].loc[master_index, 'high'].values for sym in ASSETS_5}
    asset_lows = {sym: asset_dfs[sym].loc[master_index, 'low'].values for sym in ASSETS_5}
    asset_atrs = {sym: asset_dfs[sym].loc[master_index, 'feat_vol_atr'].values for sym in ASSETS_5}
    asset_atr_pcts = {sym: asset_dfs[sym].loc[master_index, 'feat_vol_atr_pct'].values for sym in ASSETS_5}

    asset_pl = {sym: asset_dfs[sym].loc[master_index, 'p_stack_l'].values for sym in ASSETS_5}
    asset_ps = {sym: asset_dfs[sym].loc[master_index, 'p_stack_s'].values for sym in ASSETS_5}
    asset_hmm = {sym: asset_dfs[sym].loc[master_index, 'hmm_state'].values for sym in ASSETS_5}

    pip_sizes = {sym: (0.01 if "JPY" in sym else 0.0001) for sym in ASSETS_5}
    lot_value_mults = {sym: (100.0 if "JPY" in sym else 10.0) for sym in ASSETS_5}

    hours = np.array([ts.hour for ts in master_index])
    trading_window = ~((hours >= 13) & (hours <= 16))

    signals = {}
    for sym in ASSETS_5:
        req_p = np.where(asset_hmm[sym] == 1.0, 0.42, 0.36)
        vol_p = (asset_atr_pcts[sym] >= 40.0)
        sig_buy = (asset_pl[sym] >= req_p) & vol_p & trading_window
        sig_sell = (asset_ps[sym] >= req_p) & trading_window

        sig_arr = np.full(total_bars, "NONE", dtype=object)
        sig_arr[sig_buy] = "BUY"
        sig_arr[sig_sell] = "SELL"
        signals[sym] = sig_arr

    def run_sim_5pair(usd_factor_cap):
        portfolio_equity = 10000.0
        equity_curve = [portfolio_equity]
        all_closed_trades = []
        active_positions = {sym: None for sym in ASSETS_5}
        pending_orders = {sym: None for sym in ASSETS_5}

        for i in range(total_bars):
            timestamp = master_index[i]

            # Update active positions
            for sym in ASSETS_5:
                pip_size = pip_sizes[sym]; lot_mult = lot_value_mults[sym]; friction_pips = BASE_FRICTION_PIPS[sym]
                close = asset_closes[sym][i]; high = asset_highs[sym][i]; low = asset_lows[sym][i]
                atr = asset_atrs[sym][i] if not np.isnan(asset_atrs[sym][i]) else (0.12 if "JPY" in sym else 0.0012)
                sig = signals[sym][i]

                pos = active_positions[sym]

                if pos is not None:
                    direction = pos['direction']; entry_price = pos['entry_price']; entry_time = pos['entry_time']
                    sl_price = pos['sl_price']; tp_price = pos['tp_price']; initial_sl_dist = pos['initial_sl_dist']

                    stop_out = False; exit_price = 0.0; exit_reason = None
                    opposite_sig = 'SELL' if direction == 'BUY' else 'BUY'
                    floating_pips = (high - entry_price) / pip_size if direction == 'BUY' else (entry_price - low) / pip_size
                    r_floating = floating_pips / (initial_sl_dist / pip_size) if initial_sl_dist > 0 else 0.0

                    if not pos['partial_taken'] and r_floating >= 1.5:
                        partial_lots = pos['initial_lots'] * 0.5; pos['active_lots'] -= partial_lots; pos['partial_taken'] = True
                        partial_pips = (initial_sl_dist / pip_size) * 1.5 - friction_pips
                        partial_gross = partial_pips * (partial_lots * lot_mult); partial_comm = 7.0 * partial_lots; partial_net = partial_gross - partial_comm
                        pos['partial_pnl_usd'] = partial_net; portfolio_equity += partial_net

                    if sig == opposite_sig: stop_out = True; exit_price = close; exit_reason = 'signal_reversal'
                    elif (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0: stop_out = True; exit_price = close; exit_reason = 'time_limit'
                    elif direction == 'BUY' and low <= sl_price: stop_out = True; exit_price = sl_price - (friction_pips * pip_size); exit_reason = 'stop_loss'
                    elif direction == 'SELL' and high >= sl_price: stop_out = True; exit_price = sl_price + (friction_pips * pip_size); exit_reason = 'stop_loss'
                    elif direction == 'BUY' and high >= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'
                    elif direction == 'SELL' and low <= tp_price: stop_out = True; exit_price = tp_price; exit_reason = 'take_profit'

                    if stop_out:
                        active_positions[sym] = None
                        rem_pips = (exit_price - entry_price) / pip_size if direction == 'BUY' else (entry_price - exit_price) / pip_size
                        rem_pips -= friction_pips
                        rem_lots = pos['active_lots']; rem_gross = rem_pips * (rem_lots * lot_mult); rem_comm = 7.0 * rem_lots; rem_net = rem_gross - rem_comm
                        total_trade_net = rem_net + pos.get('partial_pnl_usd', 0.0)

                        pos['exit_time'] = timestamp; pos['exit_price'] = exit_price; pos['exit_reason'] = exit_reason; pos['pnl_pips'] = rem_pips; pos['pnl_usd'] = total_trade_net; pos['status'] = 'closed'
                        all_closed_trades.append(pos)
                        portfolio_equity += rem_net

                        if sig == opposite_sig:
                            pending_orders[sym] = {"direction": opposite_sig, "limit_price": close - (0.25 * atr) if opposite_sig == 'BUY' else close + (0.25 * atr), "signal_idx": i, "atr": atr}

                # Fill Pending Orders if within USD Factor Cap
                if active_positions[sym] is None and pending_orders[sym] is not None:
                    p_order = pending_orders[sym]; p_dir = p_order["direction"]; p_limit = p_order["limit_price"]; p_atr = p_order["atr"]; sig_idx = p_order["signal_idx"]

                    if (i - sig_idx) > 3: pending_orders[sym] = None
                    else:
                        filled = (p_dir == 'BUY' and low <= p_limit) or (p_dir == 'SELL' and high >= p_limit)
                        if filled:
                            # Check USD factor exposure cap
                            cand_usd_dir = USD_FACTOR_MAP.get((sym, p_dir), 0)
                            curr_usd_dirs = [USD_FACTOR_MAP.get((s, p['direction']), 0) for s, p in active_positions.items() if p is not None]
                            proj_net_usd = abs(sum(curr_usd_dirs) + cand_usd_dir) * 0.0050

                            if usd_factor_cap is None or (proj_net_usd <= usd_factor_cap):
                                entry_price = p_limit
                                sl_pips = (p_atr / pip_size) * 2.0; tp_pips = (p_atr / pip_size) * 2.5; initial_sl_dist = sl_pips * pip_size
                                if p_dir == 'BUY': sl_price = entry_price - initial_sl_dist; tp_price = entry_price + (tp_pips * pip_size)
                                else: sl_price = entry_price + initial_sl_dist; tp_price = entry_price - (tp_pips * pip_size)

                                risk_amt = portfolio_equity * 0.0050
                                lots = round(max(0.01, min(10.0, risk_amt / (sl_pips * lot_mult))), 2)

                                active_positions[sym] = {
                                    'trade_id': len(all_closed_trades) + 1, 'symbol': sym, 'direction': p_dir, 'entry_time': timestamp,
                                    'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price, 'initial_sl_dist': initial_sl_dist,
                                    'initial_lots': lots, 'active_lots': lots, 'partial_taken': False, 'partial_pnl_usd': 0.0, 'status': 'open'
                                }
                            pending_orders[sym] = None

                if active_positions[sym] is None and pending_orders[sym] is None and sig in ('BUY', 'SELL'):
                    retrace_pips = (atr / pip_size) * 0.25
                    limit_price = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)
                    pending_orders[sym] = {"direction": sig, "limit_price": limit_price, "signal_idx": i, "atr": atr}

            equity_curve.append(portfolio_equity)

        pnls = [t['pnl_usd'] for t in all_closed_trades]
        wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
        net_pnl = sum(pnls); ret_pct = (net_pnl / 10000.0) * 100.0
        gross_win = sum(wins) if wins else 0.0; gross_loss = abs(sum(losses)) if losses else 1.0; pf = gross_win / gross_loss

        eq_arr = np.array(equity_curve); peaks = np.maximum.accumulate(eq_arr); dds = (eq_arr - peaks) / peaks * 100.0; max_dd = abs(np.min(dds))
        returns = np.diff(eq_arr) / eq_arr[:-1]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 24) if np.std(returns) > 0 else 0.0

        # Exact HHI from positive PnL contributions
        df_tr_all = pd.DataFrame(all_closed_trades)
        pnl_by_pair = df_tr_all.groupby('symbol')['pnl_usd'].sum() if len(df_tr_all) > 0 else pd.Series()
        pos_pnls = [max(0, pnl_by_pair.get(s, 0)) for s in ASSETS_5]
        tot_pos = sum(pos_pnls)
        hhi = sum((p / tot_pos) ** 2 for p in pos_pnls) if tot_pos > 0 else 0.0

        return {"trades": len(all_closed_trades), "ret_pct": ret_pct, "sharpe": sharpe, "max_dd": max_dd, "pf": pf, "hhi": hhi, "end_eq": portfolio_equity}

    m_5_uncapped = run_sim_5pair(None)
    m_5_usd_cap10 = run_sim_5pair(0.010)

    total_elapsed = time.time() - t0

    print("=========================================================================================================================================")
    print(f"  🏆 5-PAIR PORTFOLIO SCORECARD (EXCLUDING USDCHF) (TOTAL TIME: {total_elapsed:.1f}s)")
    print("=========================================================================================================================================")
    print(f"{'5-Pair Portfolio Configuration':<52} | {'Trades':<7} | {'Ending Equity ($)':<16} | {'Net Return (%)':<15} | {'Sharpe':<8} | {'MDD (%)':<8} | {'PF':<6} | {'Exact HHI':<8}")
    print("-" * 135)
    print(f"{'1. 5-Pair Portfolio (Uncapped Risk)':<52} | {m_5_uncapped['trades']:<7} | ${m_5_uncapped['end_eq']:<15,.2f} | +{m_5_uncapped['ret_pct']:<14.2f}% | {m_5_uncapped['sharpe']:<8.2f} | {m_5_uncapped['max_dd']:<7.2f}% | {m_5_uncapped['pf']:<6.2f} | {m_5_uncapped['hhi']:<8.4f}")
    print(f"{'2. 5-Pair Portfolio + USD Directional Cap <= 1.0%':<52} | {m_5_usd_cap10['trades']:<7} | ${m_5_usd_cap10['end_eq']:<15,.2f} | +{m_5_usd_cap10['ret_pct']:<14.2f}% | {m_5_usd_cap10['sharpe']:<8.2f} | {m_5_usd_cap10['max_dd']:<7.2f}% | {m_5_usd_cap10['pf']:<6.2f} | {m_5_usd_cap10['hhi']:<8.4f}")
    print("=========================================================================================================================================")

if __name__ == "__main__":
    run_5pair_test()
