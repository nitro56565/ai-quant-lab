"""
Abstract Market Data Provider Interface v5.0.
Decouples market data sources (OANDA, Polygon, TwelveData, Interactive Brokers, CSV Replay)
from downstream feature engineering, ML signal inference, and execution pipelines.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, Optional
import pandas as pd

class BaseMarketDataProvider(ABC):
    """
    Abstract Interface for Real-Time Streaming & Historical Market Data Providers.
    """
    @abstractmethod
    def fetch_historical_candles(self, symbol: str, timeframe: str = "1h", count: int = 48) -> pd.DataFrame:
        """
        Fetches historical candles as a pandas DataFrame with datetime index.
        """
        pass

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Returns latest market quote: {'ask': float, 'bid': float, 'mid': float, 'spread': float, 'timestamp': datetime}
        """
        pass

    @abstractmethod
    def start_streaming(self, symbol: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Starts tick/candle streaming loop.
        """
        pass

    @abstractmethod
    def stop_streaming(self):
        """
        Stops tick streaming gracefully.
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Returns operational status metrics (provider_name, connected, tick_count, last_tick_time).
        """
        pass

# Backward-compatible alias
MarketDataProvider = BaseMarketDataProvider

