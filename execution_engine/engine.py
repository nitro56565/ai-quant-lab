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

    def run_simulation(self, df: pd.DataFrame, signals, config: dict, symbol: str, pip_size: float, strategy_name: str) -> list:
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
                        strategy_name=strategy_name
                    )
                    
                    in_trade = True
                    direction = sig
                    entry_price = close
                    entry_time = timestamp
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
                        
                    # Apply lot size scaling to PnL
                    # E.g., base PnL pips is matched. Size acts as multiplier on cash return.
                    t_log['exit_time'] = timestamp
                    t_log['exit_price'] = exit_price
                    t_log['exit_reason'] = exit_reason
                    t_log['pnl_pips'] = pnl_pips
                    t_log['pnl_usd'] = pnl_pips * size * self.default_pip_value
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
        
        # CAGR
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        total_days = (end_dt - start_dt).days
        years_duration = total_days / 365.25 if total_days > 0 else 1.0
        cagr = (((current_equity / self.initial_capital) ** (1.0 / years_duration)) - 1.0) * 100.0 if current_equity > 0 else -100.0
        
        # Sharpe Ratio (daily returns)
        daily_equity = {}
        curr_eq = self.initial_capital
        trades_by_day = {}
        for t in closed_trades:
            day_str = t['exit_time'].strftime('%Y-%m-%d')
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
        sharpe = (pct_returns.mean() / pct_returns.std() * (252 ** 0.5)) if not pct_returns.empty and pct_returns.std() > 0 else 0.0
        
        score = 0.35 * cagr + 0.25 * sharpe + 0.20 * profit_factor - 0.20 * max_dd_pct
        
        metrics = {
            'return_pct': ((current_equity - self.initial_capital) / self.initial_capital) * 100.0,
            'trades': total_trades,
            'win_rate': win_rate,
            'pf': profit_factor,
            'sharpe': sharpe,
            'max_dd': max_dd_pct,
            'score': score
        }
        
        # Add automated sanity checks
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
