import pandas as pd
from data_loader import DataLoader
from .base import Strategy

class StrategyEngine:
    """
    StrategyEngine orchestrates running backtests on Strategy instances.
    Simulates trades bar-by-bar to correctly resolve initial stops and trailing stops.
    """
    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader
        
    def run_backtest(self, strategy: Strategy, symbol: str, start_date: str, end_date: str):
        """
        Run a backtest for a strategy and symbol over the specified date range.
        
        Args:
            strategy: Strategy instance
            symbol: Trading symbol (e.g. "EURUSD")
            start_date: Start date of backtest
            end_date: End date of backtest
            
        Returns:
            df_signals: DataFrame containing H1 prices, aligned indicators, and signals
            trades: List of dicts representing each executed trade's execution logs
        """
        # 1. Load metadata
        metadata = self.data_loader.get_symbol_metadata(symbol)
        pip_size = metadata.get('pip_size', 0.0001)
        
        # 2. Prepare data
        df_signals = strategy.prepare_data(self.data_loader, symbol, start_date, end_date)
        
        # 3. Simulate trades bar-by-bar
        trades = []
        in_trade = False
        
        entry_price = 0
        entry_time = None
        initial_sl = 0
        trailing_sl = 0
        highest_high = 0
        
        for timestamp, row in df_signals.iterrows():
            if not in_trade:
                # Look for entry signals
                if row['entry_signal']:
                    in_trade = True
                    entry_time = timestamp
                    entry_price = row['close']
                    
                    # Calculate initial stop loss based on entry Close - multiplier * ATR
                    atr = row[strategy.atr_col]
                    initial_sl = entry_price - (strategy.sl_atr_multiplier * atr)
                    trailing_sl = initial_sl
                    highest_high = row['high']
                    
                    trades.append({
                        'trade_id': len(trades) + 1,
                        'symbol': symbol,
                        'entry_time': entry_time,
                        'entry_price': entry_price,
                        'initial_sl': initial_sl,
                        'exit_time': None,
                        'exit_price': None,
                        'exit_reason': None,
                        'pnl_pips': None,
                        'status': 'open'
                    })
            else:
                # Update trailing stop based on highest high since entry
                highest_high = max(highest_high, row['high'])
                atr = row[strategy.atr_col]
                
                # Trailing stop level = highest high - multiplier * ATR
                current_trailing = highest_high - (strategy.trail_atr_multiplier * atr)
                trailing_sl = max(trailing_sl, current_trailing)
                
                # Check for stop out
                # Exit conditions:
                # 1. Price drops below initial Stop Loss
                # 2. Price drops below Trailing Stop Loss
                # 3. Custom strategy exit condition (e.g., take profit)
                stop_out = False
                exit_price = 0
                exit_reason = None
                
                # Check custom exit first (e.g. TP)
                custom_exit_price = strategy.check_exit(row, trades[-1])
                if custom_exit_price is not None:
                    stop_out = True
                    exit_price = custom_exit_price
                    exit_reason = 'custom_exit'
                
                # If low drops below trailing_sl (which is always >= initial_sl)
                elif row['low'] <= trailing_sl:
                    stop_out = True
                    exit_price = trailing_sl
                    exit_reason = 'trailing_stop'
                    
                    # Special check: did we hit the initial SL first (if trailing stop didn't move)?
                    if trailing_sl == initial_sl and row['low'] <= initial_sl:
                        exit_reason = 'initial_stop'
                
                if stop_out:
                    in_trade = False
                    trades[-1]['exit_time'] = timestamp
                    # Stop out execution is assumed at stop level (slippage can be added here)
                    trades[-1]['exit_price'] = exit_price
                    trades[-1]['exit_reason'] = exit_reason
                    trades[-1]['status'] = 'closed'
                    
                    # Calculate PnL in pips
                    pips = (exit_price - entry_price) / pip_size
                    trades[-1]['pnl_pips'] = round(pips, 2)
                    
        return df_signals, trades
