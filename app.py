from flask import Flask, jsonify, request, send_from_directory
import os
import pandas as pd
from data_loader import DataLoader
from strategy_engine import (
    StrategyEngine,
    AdaptiveTrendFollowing,
    PullbackContinuation,
    MeanReversion,
    VolatilityBreakout,
    LondonSessionMomentum
)

app = Flask(__name__, static_folder='.')

# Map strategy names to their respective classes
STRATEGIES = {
    'AdaptiveTrendFollowing': AdaptiveTrendFollowing,
    'PullbackContinuation': PullbackContinuation,
    'MeanReversion': MeanReversion,
    'VolatilityBreakout': VolatilityBreakout,
    'LondonSessionMomentum': LondonSessionMomentum
}

# Share single instance of loader and engine across requests
loader = DataLoader()
engine = StrategyEngine(loader)

@app.route('/')
def index():
    """Serve the simulator dashboard webpage."""
    return send_from_directory('.', 'simulator_dashboard.html')

@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    """Run a strategy backtest and return performance metrics and transaction logs."""
    data = request.json or {}
    strategies_input = data.get('strategies', ['AdaptiveTrendFollowing'])
    symbol = data.get('symbol', 'EURUSD')
    start_date = data.get('start_date', '2018-01-01')
    end_date = data.get('end_date', '2018-12-31')
    initial_capital = float(data.get('initial_capital', 10000.0))
    
    # Coerce to list if string
    if isinstance(strategies_input, str):
        strategies_input = [strategies_input]
        
    for s_name in strategies_input:
        if s_name not in STRATEGIES:
            return jsonify({'error': f"Strategy '{s_name}' is not recognized."}), 400
            
    try:
        combined_trades = []
        
        # 1. Execute backtests for all selected strategies
        for s_name in strategies_input:
            strategy_class = STRATEGIES[s_name]
            strategy = strategy_class()
            
            df_signals, trades = engine.run_backtest(strategy, symbol, start_date, end_date)
            
            for t in trades:
                if t['status'] == 'closed':
                    t_copy = t.copy()
                    t_copy['strategy'] = strategy.name
                    combined_trades.append(t_copy)
                    
        # 2. Sort combined trades chronologically by exit time
        combined_trades_sorted = sorted(combined_trades, key=lambda x: x['exit_time'])
        
        # Re-index trade IDs to be sequential
        for idx, t in enumerate(combined_trades_sorted):
            t['trade_id'] = idx + 1
            
        # 3. Compile the Equity Curve and formatting
        # Default leverage size is 1 lot, pip value = $10
        pip_value = 10.0
        current_equity = initial_capital
        equity_curve = [{'time': start_date, 'equity': current_equity}]
        
        for t in combined_trades_sorted:
            pnl_usd = t['pnl_pips'] * pip_value
            current_equity += pnl_usd
            equity_curve.append({
                'time': t['exit_time'].strftime('%Y-%m-%d %H:%M'),
                'equity': round(current_equity, 2)
            })
            
        # 4. Calculate stats
        total_trades = len(combined_trades_sorted)
        wins = [t for t in combined_trades_sorted if t['pnl_pips'] > 0]
        losses = [t for t in combined_trades_sorted if t['pnl_pips'] <= 0]
        
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
        total_pips = sum(t['pnl_pips'] for t in combined_trades_sorted)
        avg_pips = (total_pips / total_trades) if total_trades > 0 else 0.0
        
        avg_win_pips = sum(t['pnl_pips'] for t in wins) / len(wins) if len(wins) > 0 else 0.0
        avg_loss_pips = sum(t['pnl_pips'] for t in losses) / len(losses) if len(losses) > 0 else 0.0
        risk_reward_ratio = avg_win_pips / abs(avg_loss_pips) if abs(avg_loss_pips) > 0 else 0.0
        
        # Expectancy formula: (Win% * AvgWin) + (Loss% * AvgLoss)
        expectancy_pips = (win_rate / 100.0 * avg_win_pips) + ((1 - win_rate / 100.0) * avg_loss_pips)
        
        # Max Win / Max Loss
        best_trade_pips = max(t['pnl_pips'] for t in combined_trades_sorted) if total_trades > 0 else 0.0
        worst_trade_pips = min(t['pnl_pips'] for t in combined_trades_sorted) if total_trades > 0 else 0.0
        
        # Consecutive win/loss streaks
        consec_wins = 0
        consec_losses = 0
        current_consec_wins = 0
        current_consec_losses = 0
        
        for t in combined_trades_sorted:
            pnl = t['pnl_pips']
            if pnl > 0:
                current_consec_wins += 1
                current_consec_losses = 0
                if current_consec_wins > consec_wins:
                    consec_wins = current_consec_wins
            else:
                current_consec_losses += 1
                current_consec_wins = 0
                if current_consec_losses > consec_losses:
                    consec_losses = current_consec_losses
                    
        # Daily calendar grouping (Best/Worst day)
        day_pnl_map = {}
        for t in combined_trades_sorted:
            day_str = t['exit_time'].strftime('%Y-%m-%d')
            day_pnl_map[day_str] = day_pnl_map.get(day_str, 0.0) + t['pnl_pips']
            
        best_day_pips = max(day_pnl_map.values()) if day_pnl_map else 0.0
        worst_day_pips = min(day_pnl_map.values()) if day_pnl_map else 0.0
        profitable_days = sum(1 for v in day_pnl_map.values() if v > 0)
        losing_days = sum(1 for v in day_pnl_map.values() if v <= 0)
        
        # PnL by weekday
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        pnl_by_dow = {w: 0.0 for w in weekdays}
        for t in combined_trades_sorted:
            day_name = t['exit_time'].strftime('%A')
            pnl_by_dow[day_name] = round(pnl_by_dow.get(day_name, 0.0) + t['pnl_pips'], 2)
            
        # PnL by hour of day
        pnl_by_hour = {h: 0.0 for h in range(24)}
        for t in combined_trades_sorted:
            hour = t['exit_time'].hour
            pnl_by_hour[hour] = round(pnl_by_hour.get(hour, 0.0) + t['pnl_pips'], 2)
            
        # PnL by strategy
        pnl_by_strat = {}
        for t in combined_trades_sorted:
            strat = t['strategy']
            pnl_by_strat[strat] = round(pnl_by_strat.get(strat, 0.0) + t['pnl_pips'], 2)
            
        # Profit Factor
        gross_profit = sum(t['pnl_pips'] * pip_value for t in wins)
        gross_loss = abs(sum(t['pnl_pips'] * pip_value for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)
        
        # Max Drawdown percentage
        peak = initial_capital
        max_dd = 0.0
        max_dd_usd = 0.0
        for pt in equity_curve:
            eq = pt['equity']
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak) * 100
            dd_usd = peak - eq
            if dd > max_dd:
                max_dd = dd
            if dd_usd > max_dd_usd:
                max_dd_usd = dd_usd
                
        # Recovery Factor = Net Profit / Max Drawdown USD
        net_profit = current_equity - initial_capital
        recovery_factor = net_profit / max_dd_usd if max_dd_usd > 0.0 else (net_profit if net_profit > 0.0 else 0.0)
        
        # CAGR (Compound Annual Growth Rate)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        total_days = (end_dt - start_dt).days
        years_duration = total_days / 365.25 if total_days > 0 else 1.0
        cagr = (((current_equity / initial_capital) ** (1.0 / years_duration)) - 1.0) * 100.0 if current_equity > 0 else -100.0
        
        # Average Trade Duration
        trade_durations = []
        for t in combined_trades_sorted:
            dur = t['exit_time'] - t['entry_time']
            trade_durations.append(dur.total_seconds())
        avg_dur_sec = sum(trade_durations) / len(trade_durations) if trade_durations else 0.0
        
        if avg_dur_sec > 0:
            h = int(avg_dur_sec // 3600)
            m = int((avg_dur_sec % 3600) // 60)
            avg_duration_str = f"{h}h {m}m"
        else:
            avg_duration_str = "0h 0m"
            
        # Daily Returns Sharpe Ratio
        daily_equity = {}
        curr_eq = initial_capital
        trades_by_day = {}
        for t in combined_trades_sorted:
            day_str = t['exit_time'].strftime('%Y-%m-%d')
            trades_by_day.setdefault(day_str, []).append(t)
            
        curr_dt = start_dt
        while curr_dt <= end_dt:
            day_str = curr_dt.strftime('%Y-%m-%d')
            if day_str in trades_by_day:
                for t in trades_by_day[day_str]:
                    curr_eq += t['pnl_pips'] * pip_value
            daily_equity[day_str] = curr_eq
            curr_dt += pd.Timedelta(days=1)
            
        eq_series = pd.Series(daily_equity)
        pct_returns = eq_series.pct_change().dropna()
        if not pct_returns.empty and pct_returns.std() > 0:
            sharpe_ratio = (pct_returns.mean() / pct_returns.std()) * (252 ** 0.5)
        else:
            sharpe_ratio = 0.0
                
        # 5. Calculate monthly performance details and strategy trade counts
        monthly_performance = []
        monthly_distribution = []
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        for m_idx in range(1, 13):
            # filter trades exiting in this month
            m_trades = [t for t in combined_trades_sorted if t['exit_time'].month == m_idx]
            m_name = month_names[m_idx - 1]
            
            # 5a. Performance table
            if not m_trades:
                monthly_performance.append({
                    'month': m_name,
                    'trades': 0,
                    'profit': 0.0,
                    'win_rate': 0.0,
                    'pf': 1.0,
                    'dd': 0.0
                })
            else:
                m_wins = [t for t in m_trades if t['pnl_pips'] > 0]
                m_losses = [t for t in m_trades if t['pnl_pips'] <= 0]
                m_win_rate = (len(m_wins) / len(m_trades)) * 100.0
                m_profit = sum(t['pnl_pips'] for t in m_trades)
                
                m_gross_prof = sum(t['pnl_pips'] for t in m_wins)
                m_gross_loss = abs(sum(t['pnl_pips'] for t in m_losses))
                m_pf = (m_gross_prof / m_gross_loss) if m_gross_loss > 0 else (m_gross_prof if m_gross_prof > 0 else 1.0)
                
                # Drawdown within the month
                eq_val = 10000.0
                m_curve = [eq_val]
                for t in m_trades:
                    eq_val += t['pnl_pips'] * pip_value
                    m_curve.append(eq_val)
                peak_val = 10000.0
                m_dd = 0.0
                for val in m_curve:
                    if val > peak_val:
                        peak_val = val
                    dd_pct = ((peak_val - val) / peak_val) * 100.0
                    if dd_pct > m_dd:
                        m_dd = dd_pct
                        
                monthly_performance.append({
                    'month': m_name,
                    'trades': len(m_trades),
                    'profit': round(m_profit, 2),
                    'win_rate': round(m_win_rate, 2),
                    'pf': round(m_pf, 2),
                    'dd': round(m_dd, 2)
                })
                
            # 5b. Distribution table
            m_counts = {}
            for t in m_trades:
                strat = t['strategy']
                m_counts[strat] = m_counts.get(strat, 0) + 1
            monthly_distribution.append({
                'month': m_name,
                'counts': m_counts,
                'total': len(m_trades)
            })

        # 6. Format trades logs for browser JSON consumption
        formatted_trades = []
        for t in combined_trades_sorted:
            formatted_trades.append({
                'id': t['trade_id'],
                'strategy': t['strategy'],
                'entry_time': t['entry_time'].strftime('%Y-%m-%d %H:%M'),
                'entry_price': t['entry_price'],
                'exit_time': t['exit_time'].strftime('%Y-%m-%d %H:%M'),
                'exit_price': t['exit_price'],
                'pnl_pips': round(t['pnl_pips'], 2),
                'pnl_usd': round(t['pnl_pips'] * pip_value, 2),
                'exit_reason': t['exit_reason']
            })
            
        return jsonify({
            'summary': {
                'total_trades': total_trades,
                'win_rate': round(win_rate, 2),
                'total_pips': round(total_pips, 2),
                'avg_pips': round(avg_pips, 2),
                'profit_factor': round(profit_factor, 2),
                'max_drawdown': round(max_dd, 2),
                'final_equity': round(current_equity, 2),
                'avg_win_pips': round(avg_win_pips, 2),
                'avg_loss_pips': round(avg_loss_pips, 2),
                'risk_reward_ratio': round(risk_reward_ratio, 2),
                'expectancy_pips': round(expectancy_pips, 2),
                'best_trade_pips': round(best_trade_pips, 2),
                'worst_trade_pips': round(worst_trade_pips, 2),
                'consec_wins': consec_wins,
                'consec_losses': consec_losses,
                'best_day_pips': round(best_day_pips, 2),
                'worst_day_pips': round(worst_day_pips, 2),
                'profitable_days': profitable_days,
                'losing_days': losing_days,
                'sharpe_ratio': round(sharpe_ratio, 2),
                'cagr': round(cagr, 2),
                'recovery_factor': round(recovery_factor, 2),
                'avg_duration': avg_duration_str
            },
            'pnl_by_dow': pnl_by_dow,
            'pnl_by_hour': pnl_by_hour,
            'pnl_by_strategy': pnl_by_strat,
            'monthly_performance': monthly_performance,
            'monthly_distribution': monthly_distribution,
            'equity_curve': equity_curve,
            'trades': formatted_trades
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run server locally on port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)
