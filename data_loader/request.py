import pandas as pd

class DataRequest:
    """
    DataRequest encapsulates the parameters for a market data query.
    """
    def __init__(self, symbol, timeframe, start=None, end=None, price_type='mid'):
        """
        Initialize a DataRequest.
        
        Args:
            symbol: Trading symbol (e.g. "EURUSD")
            timeframe: Timeframe identifier (e.g. "1m", "5m", "15m", "1h", "1d")
            start: Start date for query (datetime, string, or None)
            end: End date for query (datetime, string, or None)
            price_type: Price conversion type ('mid', 'bid', 'ask', 'raw')
        """
        self.symbol = symbol.upper().strip()
        self.timeframe = timeframe.lower().strip()
        self.start = pd.to_datetime(start) if start else None
        self.end = pd.to_datetime(end) if end else None
        self.price_type = price_type.lower().strip()
        
        self._validate()
        
    def _validate(self):
        if not self.symbol:
            raise ValueError("Symbol must be specified and cannot be empty.")
        if not self.timeframe:
            raise ValueError("Timeframe must be specified and cannot be empty.")
        if self.price_type not in ('mid', 'bid', 'ask', 'raw'):
            raise ValueError(f"Invalid price_type: '{self.price_type}'. Must be 'mid', 'bid', 'ask', or 'raw'.")
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"Start date {self.start} cannot be after end date {self.end}")

    def __repr__(self):
        return (f"DataRequest(symbol={self.symbol}, timeframe={self.timeframe}, "
                f"start={self.start}, end={self.end}, price_type={self.price_type})")
