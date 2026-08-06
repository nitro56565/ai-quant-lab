import pandas as pd
import numpy as np
import logging
from risk_engine import Order, RiskEngine

logger = logging.getLogger("ExecutionEngine")

class ExecutionEngine:
    """
    Simulates high-fidelity bar-by-bar execution of orders, tracks positions,
    and computes advanced portfolio performance metrics.
    """
    def __init__(self, initial_capital: float = 10000.0, default_pip_value: float = 1.0, risk_fraction: float = 0.01):
        self.initial_capital = initial_capital
        self.default_pip_value = default_pip_value
        self.risk_fraction = risk_fraction
        self.risk_engine = RiskEngine(risk_fraction=risk_fraction, default_pip_value=default_pip_value)

    def run_simulation(
        self,
        df: pd.DataFrame,
        signals: np.ndarray,
        config: Dict[str, Any],
        symbol: str = "EURUSD",
        pip_size: float = 0.0001,
        strategy_name: str = "BaseStrategy",
        limit_retrace_atr_mult: float = 0.25,
        latency_ms: int = 300,
        asymmetric_slippage_pips: float = 0.30,
        last_look_rejection_rate: float = 0.035,
        commission_per_lot_usd: float = 7.00
    ) -> List[Dict[str, Any]]:

        """
        Runs bar-by-bar execution matching for signals and returns a list of trade dictionaries.
        """
        trades = []
        in_trade = False
        
        # Position states
        direction = None
        entry_price = 0.0
        entry_time = None
        sl_price = 0.0
        tp_price = None
        trail_multiplier = config.get('trail_multiplier')
        sl_multiplier = config.get('sl_multiplier', 2.0)
        tp_multiplier = config.get('tp_multiplier')
        
        # Trailing trackers
        highest_high = 0.0
        lowest_low = 0.0
        current_equity = self.initial_capital
        
        timestamps = df.index
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        atrs = df['feat_vol_atr'].values
        bb_mids = df['feat_vol_bb_mid'].values if 'feat_vol_bb_mid' in df.columns else np.zeros(len(df))
        trend_scores = df['feat_trend_score'].values if 'feat_trend_score' in df.columns else np.zeros(len(df))
        swing_lows = df['feat_price_swing_low'].values if 'feat_price_swing_low' in df.columns else np.zeros(len(df))
        
        for i in range(len(df)):
            timestamp = timestamps[i]
            close = closes[i]
            high = highs[i]
            low = lows[i]
            atr = atrs[i]
            
            # Capital tracking for size calculation
            capital = current_equity
            if capital <= 0 and not in_trade:
                continue
                
            if not in_trade:
                # Evaluate entries
                sig = signals[i]
                if sig in ('BUY', 'SELL'):
                    # Check for dynamic target_risk_pct from strategy
                    row_risk_frac = None
                    if 'target_risk_pct' in df.columns:
                        r_val = df['target_risk_pct'].values[i]
                        if not np.isnan(r_val) and r_val > 0:
                            row_risk_frac = r_val / 100.0

                    # Call Risk Engine to formulate Order
                    order = self.risk_engine.calculate_order(
                        direction=sig,
                        current_price=close,
                        atr=atr,
                        pip_size=pip_size,
                        capital=capital,
                        sl_multiplier=sl_multiplier,
                        tp_multiplier=tp_multiplier,
                        trail_multiplier=trail_multiplier,
                        strategy_name=strategy_name,
                        risk_fraction=row_risk_frac
                    )
                    
                    # 1. LP Last-Look Rejection Check (3.5% toxicity rejection)
                    if last_look_rejection_rate > 0 and np.random.random() < last_look_rejection_rate:
                        continue # Order rejected by LP Last-Look protocol

                    in_trade = True
                    direction = sig
                    retrace_pips = (atr / pip_size) * limit_retrace_atr_mult
                    base_entry = close - (retrace_pips * pip_size) if sig == 'BUY' else close + (retrace_pips * pip_size)

                    # 2. Latency Repricing (100-500ms transmission delay penalty)
                    latency_drag_pips = (latency_ms / 1000.0) * 0.50 # ~0.15 pips per 300ms

                    # 3. Asymmetric Slippage Penalty (volatility-scaled adverse drag)
                    vol_scale = min(2.0, max(0.5, atr / (df['feat_vol_atr'].mean() if 'feat_vol_atr' in df.columns else atr)))
                    total_adverse_drag_pips = (asymmetric_slippage_pips * vol_scale) + latency_drag_pips

                    if sig == 'BUY':
                        entry_price = base_entry + (total_adverse_drag_pips * pip_size)
                    else:
                        entry_price = base_entry - (total_adverse_drag_pips * pip_size)

                    entry_time = timestamp


                    
                    if strategy_name in ('MLConsensusStrategy', 'InstitutionalAIStrategy'):
                        if sig == 'BUY':
                            pred_mfes = df['pred_mfe_long'].values if 'pred_mfe_long' in df.columns else np.zeros(len(df))
                            pred_maes = df['pred_mae_long'].values if 'pred_mae_long' in df.columns else np.zeros(len(df))
                            dynamic_tp_pips = max(pred_mfes[i], 5.0)
                            dynamic_sl_pips = max(pred_maes[i], 5.0)
                            min_sl_pips = (atr / pip_size) * 1.0
                            dynamic_sl_pips = max(dynamic_sl_pips, min_sl_pips)
                            sl_price = close - (dynamic_sl_pips * pip_size)
                            tp_price = close + (dynamic_tp_pips * pip_size)
                        else: # SELL
                            pred_mfes = df['pred_mfe_short'].values if 'pred_mfe_short' in df.columns else np.zeros(len(df))
                            pred_maes = df['pred_mae_short'].values if 'pred_mae_short' in df.columns else np.zeros(len(df))
                            dynamic_tp_pips = max(pred_mfes[i], 5.0)
                            dynamic_sl_pips = max(pred_maes[i], 5.0)
                            min_sl_pips = (atr / pip_size) * 1.0
                            dynamic_sl_pips = max(dynamic_sl_pips, min_sl_pips)
                            sl_price = close + (dynamic_sl_pips * pip_size)
                            tp_price = close - (dynamic_tp_pips * pip_size)
                    else:
                        sl_price = order.sl_price
                        tp_price = order.tp_price
                    
                    highest_high = high
                    lowest_low = low
                    
                    trades.append({
                        'trade_id': len(trades) + 1,
                        'symbol': symbol,
                        'strategy': strategy_name,
                        'direction': direction,
                        'entry_time': entry_time,
                        'entry_price': entry_price,
                        'initial_sl': sl_price,
                        'exit_time': None,
                        'exit_price': None,
                        'exit_reason': None,
                        'pnl_pips': 0.0,
                        'pnl_usd': 0.0,
                        'size': order.size,
                        'status': 'open'
                    })
            else:
                # We are in a trade, evaluate exits and update trailing stops
                t_log = trades[-1]
                size = t_log['size']
                
                # Check Stop Out Conditions
                stop_out = False
                exit_price = 0.0
                exit_reason = None
                
                if direction == 'BUY':
                    highest_high = max(highest_high, high)
                    
                    # Update Trailing Stop
                    if trail_multiplier:
                        trail_sl = highest_high - (trail_multiplier * atr)
                        sl_price = max(sl_price, trail_sl)
                        
                    # Check exits
                    if strategy_name == 'MeanReversion' and high >= bb_mids[i]:
                        stop_out = True
                        exit_price = bb_mids[i]
                        exit_reason = 'take_profit'
                    elif strategy_name == 'AdaptiveMomentumPullback' and trend_scores[i] < 45.0:
                        stop_out = True
                        exit_price = close
                        exit_reason = 'trend_score_collapse'
                    elif strategy_name == 'AdaptiveMomentumPullback' and low <= swing_lows[i]:
                        stop_out = True
                        exit_price = min(close, swing_lows[i])
                        exit_reason = 'lower_low_break'
                    elif strategy_name in ('MLConsensusStrategy', 'InstitutionalAIStrategy') and (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0:
                        stop_out = True
                        exit_price = close
                        exit_reason = 'time_limit'
                    elif low <= sl_price:
                        stop_out = True
                        exit_price = sl_price
                        exit_reason = 'stop_loss'
                    elif tp_price and high >= tp_price:
                        stop_out = True
                        exit_price = tp_price
                        exit_reason = 'take_profit'
                else: # SELL
                    lowest_low = min(lowest_low, low)
                    
                    # Update Trailing Stop
                    if trail_multiplier:
                        trail_sl = lowest_low + (trail_multiplier * atr)
                        sl_price = min(sl_price, trail_sl)
                        
                    # Check exits
                    if strategy_name == 'MeanReversion' and low <= bb_mids[i]:
                        stop_out = True
                        exit_price = bb_mids[i]
                        exit_reason = 'take_profit'
                    elif strategy_name in ('MLConsensusStrategy', 'InstitutionalAIStrategy') and (timestamp - entry_time).total_seconds() / 3600.0 >= 12.0:
                        stop_out = True
                        exit_price = close
                        exit_reason = 'time_limit'
                    elif high >= sl_price:
                        stop_out = True
                        exit_price = sl_price
                        exit_reason = 'stop_loss'
                    elif tp_price and low <= tp_price:
                        stop_out = True
                        exit_price = tp_price
                        exit_reason = 'take_profit'
                        
                # Perform exit execution
                if stop_out:
                    in_trade = False
                    
                    # Calculate PnL in pips
                    if direction == 'BUY':
                        pnl_pips = (exit_price - entry_price) / pip_size
                    else:
                        pnl_pips = (entry_price - exit_price) / pip_size
                        
                    # Apply lot size scaling to PnL and deduct ECN commission ($7/lot)
                    t_log['exit_time'] = timestamp
                    t_log['exit_price'] = exit_price
                    t_log['exit_reason'] = exit_reason
                    t_log['pnl_pips'] = pnl_pips
                    gross_usd = pnl_pips * size * self.default_pip_value
                    comm_usd = commission_per_lot_usd * size
                    t_log['pnl_usd'] = gross_usd - comm_usd
                    t_log['status'] = 'closed'

                    
                    current_equity += t_log['pnl_usd']
                    
        return trades


    def calculate_performance(self, trades: list, start_date: str, end_date: str) -> dict:
        """
        Compiles all closed trades and outputs standard metrics.
        """
        closed_trades = [t for t in trades if t['status'] == 'closed']
        total_trades = len(closed_trades)
        
        if total_trades == 0:
            return {
                'return_pct': 0.0,
                'trades': 0,
                'win_rate': 0.0,
                'pf': 1.0,
                'sharpe': 0.0,
                'max_dd': 0.0,
                'score': 0.0
            }
            
        # Re-index trade IDs
        for idx, t in enumerate(closed_trades):
            t['trade_id'] = idx + 1
            
        current_equity = self.initial_capital
        equity_curve = [{'time': start_date, 'equity': self.initial_capital}]
        
        for t in closed_trades:
            pnl_usd = t['pnl_usd']
            current_equity += pnl_usd
            equity_curve.append({
                'time': t['exit_time'],
                'equity': current_equity
            })
            
        wins = [t for t in closed_trades if t['pnl_pips'] > 0]
        losses = [t for t in closed_trades if t['pnl_pips'] <= 0]
        win_rate = (len(wins) / total_trades * 100.0)
        
        # Drawdowns
        peak = self.initial_capital
        max_dd_pct = 0.0
        max_dd_usd = 0.0
        for pt in equity_curve:
            eq = pt['equity']
            if eq > peak:
                peak = eq
            dd_pct = ((peak - eq) / peak) * 100.0
            dd_usd = peak - eq
            max_dd_pct = max(max_dd_pct, dd_pct)
            max_dd_usd = max(max_dd_usd, dd_usd)
            
        win_cash = sum(t['pnl_usd'] for t in wins)
        loss_cash = sum(t['pnl_usd'] for t in losses)
        profit_factor = win_cash / abs(loss_cash) if abs(loss_cash) > 0 else (win_cash if win_cash > 0 else 1.0)
        
        # CAGR & MAR / Calmar
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        total_days = (end_dt - start_dt).days
        years_duration = total_days / 365.25 if total_days > 0 else 1.0
        cagr = (((current_equity / self.initial_capital) ** (1.0 / years_duration)) - 1.0) * 100.0 if current_equity > 0 else -100.0
        mar_ratio = cagr / max_dd_pct if max_dd_pct > 0 else cagr

        # Expected Value per trade
        ev_pips = pd.Series([t['pnl_pips'] for t in closed_trades]).mean()
        ev_usd = pd.Series([t['pnl_usd'] for t in closed_trades]).mean()

        # Avg Win Pips / Avg Loss Pips (R:R Ratio)
        avg_win_pips = pd.Series([t['pnl_pips'] for t in wins]).mean() if wins else 0.0
        avg_loss_pips = abs(pd.Series([t['pnl_pips'] for t in losses]).mean()) if losses else 1.0
        rr_ratio = avg_win_pips / avg_loss_pips if avg_loss_pips > 0 else 0.0

        # Drawdown Duration (hours underwater)
        running_peak = self.initial_capital
        max_dd_duration_hours = 0
        underwater_start = None
        for pt in equity_curve:
            eq = pt['equity']
            if eq >= running_peak:
                running_peak = eq
                if underwater_start:
                    dur = (pd.to_datetime(pt['time']) - pd.to_datetime(underwater_start)).total_seconds() / 3600.0
                    max_dd_duration_hours = max(max_dd_duration_hours, dur)
                    underwater_start = None
            else:
                if not underwater_start:
                    underwater_start = pt['time']
        if underwater_start:
            dur = (pd.to_datetime(equity_curve[-1]['time']) - pd.to_datetime(underwater_start)).total_seconds() / 3600.0
            max_dd_duration_hours = max(max_dd_duration_hours, dur)

        # Daily Returns & Risk Ratios (Sortino, Calmar, CVaR 95%, Skewness, Kurtosis)
        daily_equity = {}
        curr_eq = self.initial_capital
        trades_by_day = {}
        for t in closed_trades:
            day_str = pd.to_datetime(t['exit_time']).strftime('%Y-%m-%d')
            trades_by_day.setdefault(day_str, []).append(t)
            
        curr_dt = start_dt
        while curr_dt <= end_dt:
            day_str = curr_dt.strftime('%Y-%m-%d')
            if day_str in trades_by_day:
                for t in trades_by_day[day_str]:
                    curr_eq += t['pnl_usd']
            daily_equity[day_str] = curr_eq
            curr_dt += pd.Timedelta(days=1)
            
        eq_series = pd.Series(daily_equity)
        pct_returns = eq_series.pct_change().dropna()
        
        sharpe = 0.0
        sortino = 0.0
        cvar_95 = 0.0
        sk = 0.0
        kt = 0.0
        
        if not pct_returns.empty and pct_returns.std() > 0:
            std_ret = pct_returns.std()
            sharpe = (pct_returns.mean() / std_ret * (252 ** 0.5))
            
            # Sortino Ratio (downside risk only)
            downside_returns = pct_returns[pct_returns < 0]
            downside_std = downside_returns.std() if not downside_returns.empty else std_ret
            sortino = (pct_returns.mean() / downside_std * (252 ** 0.5)) if downside_std > 0 else sharpe
            
            # CVaR 95% (Expected Shortfall)
            cvar_95 = abs(np.percentile(pct_returns, 5)) * 100.0
            
            from scipy.stats import skew, kurtosis
            sk = float(skew(pct_returns))
            kt = float(kurtosis(pct_returns, fisher=False))
        
        # Probabilistic Sharpe Ratio (PSR) & Deflated Sharpe Ratio (DSR)
        # Ref: Marcos Lopez de Prado (2014) - "The Deflated Sharpe Ratio", Journal of Portfolio Management
        psr = 0.5
        dsr = 0.5
        min_trl_days = 0
        if not pct_returns.empty and len(pct_returns) > 5 and pct_returns.std() > 0:
            from scipy.stats import norm
            n_ret = len(pct_returns)
            sr_daily = pct_returns.mean() / pct_returns.std()
            sr_std_daily = np.sqrt((1.0 - sk * sr_daily + ((kt - 1.0) / 4.0) * (sr_daily ** 2)) / max(n_ret - 1, 1))
            
            if sr_std_daily > 0:
                psr = float(norm.cdf(sr_daily / sr_std_daily))
                num_trials = 10
                euler_mascheroni = 0.5772156649
                e_max_sr_daily = (1.0 - euler_mascheroni) * norm.ppf(1.0 - 1.0 / num_trials) + euler_mascheroni * norm.ppf(1.0 - 1.0 / (num_trials * np.e))
                sr_benchmark_daily = (e_max_sr_daily / np.sqrt(252))
                dsr_z = (sr_daily - sr_benchmark_daily) / sr_std_daily
                dsr = float(norm.cdf(dsr_z))
                
                sr_annual = sharpe
                min_trl_days = int(1.0 + (1.0 - sk * sr_annual + ((kt - 1.0) / 4.0) * (sr_annual ** 2)) * (norm.ppf(0.95) / max(sr_annual, 0.01)) ** 2)


        # Yearly YoY Breakdown Matrix (2018 - 2025)
        df_trades = pd.DataFrame(closed_trades)
        df_trades['year'] = pd.to_datetime(df_trades['exit_time']).dt.year
        yearly_metrics = {}
        curr_cap = self.initial_capital

        for yr in range(2018, 2026):
            yr_trades = df_trades[df_trades['year'] == yr]
            n_tr = len(yr_trades)

            if n_tr == 0:
                yearly_metrics[yr] = {
                    'trades': 0,
                    'win_rate': 0.0,
                    'net_pnl': 0.0,
                    'return_pct': 0.0,
                    'pf': 1.0,
                    'max_dd': 0.0
                }
                continue

            wins_yr = yr_trades[yr_trades['pnl_pips'] > 0]
            losses_yr = yr_trades[yr_trades['pnl_pips'] <= 0]
            win_rate_yr = (len(wins_yr) / n_tr) * 100.0
            net_pnl_yr = yr_trades['pnl_usd'].sum()
            ret_pct_yr = (net_pnl_yr / curr_cap) * 100.0

            win_cash_yr = wins_yr['pnl_usd'].sum() if len(wins_yr) > 0 else 0.0
            loss_cash_yr = abs(losses_yr['pnl_usd'].sum()) if len(losses_yr) > 0 else 0.0
            pf_yr = win_cash_yr / loss_cash_yr if loss_cash_yr > 0 else 1.0

            # Annual Max Drawdown
            eq_yr = curr_cap + yr_trades['pnl_usd'].cumsum()
            pk_yr = eq_yr.cummax()
            dd_yr = ((pk_yr - eq_yr) / pk_yr) * 100.0
            max_dd_yr = dd_yr.max() if len(dd_yr) > 0 else 0.0

            curr_cap += net_pnl_yr

            yearly_metrics[yr] = {
                'trades': n_tr,
                'win_rate': round(win_rate_yr, 1),
                'net_pnl': round(net_pnl_yr, 2),
                'return_pct': round(ret_pct_yr, 2),
                'pf': round(pf_yr, 2),
                'max_dd': round(max_dd_yr, 2)
            }

        score = 0.35 * cagr + 0.25 * sharpe + 0.20 * profit_factor - 0.20 * max_dd_pct
        
        metrics = {
            'return_pct': ((current_equity - self.initial_capital) / self.initial_capital) * 100.0,
            'net_pnl': current_equity - self.initial_capital,
            'trades': total_trades,
            'win_rate': win_rate,
            'pf': profit_factor,
            'cagr': cagr,
            'ev_pips': ev_pips,
            'ev_usd': ev_usd,
            'rr_ratio': rr_ratio,
            'sharpe': sharpe,
            'sortino': sortino,
            'calmar': mar_ratio,
            'mar_ratio': mar_ratio,
            'cvar_95': cvar_95,
            'skewness': sk,
            'kurtosis': kt,
            'psr': psr,
            'dsr': dsr,
            'min_trl_days': min_trl_days,
            'max_dd': max_dd_pct,
            'max_dd_duration_hours': max_dd_duration_hours,
            'score': score,
            'yearly_metrics': yearly_metrics
        }
        
        metrics['sanity_warnings'] = self.run_sanity_checks(closed_trades, metrics)
        
        return metrics

    def run_sanity_checks(self, trades: list, metrics: dict, pip_size: float = 0.0001) -> list:
        """
        Runs automated sanity checks on backtest results to flag impossible outputs.
        """
        warnings = []
        
        # 1. Check Drawdown
        if metrics['max_dd'] > 100.0:
            warnings.append(f"❌ Impossible drawdown detected: {metrics['max_dd']:.2f}% (must be <= 100% with risk sizing)")
            
        for t in trades:
            t_id = t['trade_id']
            # 2. Check position size
            if t['size'] <= 0:
                warnings.append(f"❌ Invalid position size on trade #{t_id}: {t['size']}")
                
            # 3. Check stop loss presence
            if t.get('initial_sl') is None or t['initial_sl'] == 0.0:
                warnings.append(f"❌ Missing stop loss value on trade #{t_id}")
                
            # 4. Check catastrophic loss (> 500 pips)
            if t['pnl_pips'] < -500.0:
                warnings.append(f"❌ Catastrophic loss detected on trade #{t_id}: {t['pnl_pips']:.1f} pips")
                
            # 5. Check trade duration (longer than 30 days)
            if t.get('exit_time') and t.get('entry_time'):
                duration_days = (t['exit_time'] - t['entry_time']).days
                if duration_days > 30:
                    warnings.append(f"⚠️ Trade #{t_id} held for {duration_days} days (longer than 30-day limit)")
                    
            # 6. Check PnL price consistency
            if t['status'] == 'closed':
                direction = t['direction']
                entry = t['entry_price']
                exit = t['exit_price']
                pips = t['pnl_pips']
                
                if direction == 'BUY':
                    expected_pips = (exit - entry) / pip_size
                else:
                    expected_pips = (entry - exit) / pip_size
                    
                if abs(expected_pips - pips) > 0.5:
                    warnings.append(f"❌ PnL calculation mismatch on trade #{t_id}: entry={entry:.5f}, exit={exit:.5f}, logged_pips={pips:.1f}, expected={expected_pips:.1f}")
                    
        return warnings
