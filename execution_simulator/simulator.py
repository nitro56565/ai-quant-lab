import time

class Position:
    """
    Represents an open trading position.
    """
    def __init__(self, symbol: str, side: str, size: float, entry_price: float):
        self.symbol = symbol.upper()
        self.side = side.lower()  # 'buy' (long) or 'sell' (short)
        self.size = size  # lot size
        self.entry_price = entry_price
        self.unrealized_pnl = 0.0

class ExecutionSimulator:
    """
    ExecutionSimulator simulates market execution (Buy, Sell, Close, Partial Close, Reverse)
    and handles account balances, netting, and order books.
    """
    def __init__(self, initial_balance=10000.0, pip_size=0.0001, pip_value_standard_lot=10.0):
        self.balance = initial_balance
        self.equity = initial_balance
        self.pip_size = pip_size
        self.pip_value_standard_lot = pip_value_standard_lot
        self.positions = {}  # symbol -> Position
        self.orders = []  # List of execution records
        
    def get_equity(self, current_prices: dict) -> float:
        """Calculate current equity including unrealized P&L."""
        unrealized = 0.0
        for symbol, pos in self.positions.items():
            if symbol in current_prices:
                price = current_prices[symbol]
                pips = (price - pos.entry_price) / self.pip_size if pos.side == 'buy' else (pos.entry_price - price) / self.pip_size
                pos.unrealized_pnl = pips * self.pip_value_standard_lot * pos.size
                unrealized += pos.unrealized_pnl
        self.equity = self.balance + unrealized
        return self.equity

    def buy(self, symbol: str, size: float, price: float):
        """Execute a buy order."""
        symbol = symbol.upper()
        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos.side == 'sell':
                # Netting opposite position
                self._handle_netting(pos, 'buy', size, price)
            else:
                # Add to existing long position (re-calculate average entry price)
                new_size = pos.size + size
                pos.entry_price = ((pos.entry_price * pos.size) + (price * size)) / new_size
                pos.size = new_size
        else:
            self.positions[symbol] = Position(symbol, 'buy', size, price)
            
        self._record_order('BUY', symbol, size, price)

    def sell(self, symbol: str, size: float, price: float):
        """Execute a sell order."""
        symbol = symbol.upper()
        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos.side == 'buy':
                # Netting opposite position
                self._handle_netting(pos, 'sell', size, price)
            else:
                # Add to existing short position (re-calculate average entry price)
                new_size = pos.size + size
                pos.entry_price = ((pos.entry_price * pos.size) + (price * size)) / new_size
                pos.size = new_size
        else:
            self.positions[symbol] = Position(symbol, 'sell', size, price)
            
        self._record_order('SELL', symbol, size, price)

    def close(self, symbol: str, price: float):
        """Fully close an open position."""
        symbol = symbol.upper()
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        
        # Realize P&L
        pips = (price - pos.entry_price) / self.pip_size if pos.side == 'buy' else (pos.entry_price - price) / self.pip_size
        realized_pnl = pips * self.pip_value_standard_lot * pos.size
        
        self.balance += realized_pnl
        del self.positions[symbol]
        
        self._record_order('CLOSE', symbol, pos.size, price, realized_pnl)

    def partial_close(self, symbol: str, size_to_close: float, price: float):
        """Partially close an open position."""
        symbol = symbol.upper()
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        
        if size_to_close >= pos.size:
            self.close(symbol, price)
            return
            
        # Realize partial P&L
        pips = (price - pos.entry_price) / self.pip_size if pos.side == 'buy' else (pos.entry_price - price) / self.pip_size
        realized_pnl = pips * self.pip_value_standard_lot * size_to_close
        
        self.balance += realized_pnl
        pos.size -= size_to_close
        
        self._record_order('PARTIAL_CLOSE', symbol, size_to_close, price, realized_pnl)

    def reverse(self, symbol: str, price: float):
        """Reverse the current position (e.g. flip Buy to Sell with same size)."""
        symbol = symbol.upper()
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        old_side = pos.side
        old_size = pos.size
        
        # Close current
        self.close(symbol, price)
        
        # Open opposite
        new_side = 'sell' if old_side == 'buy' else 'buy'
        if new_side == 'buy':
            self.buy(symbol, old_size, price)
        else:
            self.sell(symbol, old_size, price)
            
        self._record_order('REVERSE', symbol, old_size, price)

    def _handle_netting(self, pos: Position, order_side: str, order_size: float, price: float):
        """Helper to net off opposite positions."""
        pips = (price - pos.entry_price) / self.pip_size if pos.side == 'buy' else (pos.entry_price - price) / self.pip_size
        
        if order_size >= pos.size:
            # Fully close existing and open leftover in new direction
            realized_pnl = pips * self.pip_value_standard_lot * pos.size
            self.balance += realized_pnl
            
            leftover_size = order_size - pos.size
            if leftover_size > 0:
                pos.side = order_side
                pos.size = leftover_size
                pos.entry_price = price
            else:
                del self.positions[pos.symbol]
        else:
            # Partially net off position
            realized_pnl = pips * self.pip_value_standard_lot * order_size
            self.balance += realized_pnl
            pos.size -= order_size

    def _record_order(self, action: str, symbol: str, size: float, price: float, realized_pnl=0.0):
        """Log order history record."""
        self.orders.append({
            'timestamp': time.strftime('%H:%M:%S'),
            'action': action,
            'symbol': symbol,
            'size': round(size, 2),
            'price': round(price, 5),
            'realized_pnl': round(realized_pnl, 2)
        })
