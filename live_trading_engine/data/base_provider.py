"""
Abstract Market Data Provider Interface v3.0.
Decouples data sources (OANDA, Replay, MT5, CSV) from downstream aggregation and execution pipelines.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, Any

class MarketDataProvider(ABC):
    """
    Abstract Interface for Real-Time & Historical Replay Market Data Providers.
    """
    @abstractmethod
    def start(self, symbol: str, tick_callback: Callable[[Dict[str, Any]], None]):
        """
        Starts tick streaming or replay loop.
        """
        pass

    @abstractmethod
    def stop(self):
        """
        Stops tick streaming gracefully.
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Returns operational status metrics (connected, tick count, last tick time).
        """
        pass
