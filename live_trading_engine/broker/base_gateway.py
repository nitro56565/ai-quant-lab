"""
Abstract Execution Gateway Interface — AI Quant Lab v5.0.
Decouples OrderManager from specific broker execution backends.
Enables seamless switching between ExecutionSimulator (Paper Trading) and Live Broker Gateways (OANDA, FIX Protocol, Interactive Brokers).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime

class BaseExecutionGateway(ABC):
    """
    Abstract Interface for Execution Simulator & Live Broker Gateways.
    """
    @abstractmethod
    def place_order(self, order_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submits an order specification to the execution backend.
        """
        pass

    @abstractmethod
    def on_tick(self, current_time: datetime, ask: float, bid: float) -> List[Dict[str, Any]]:
        """
        Evaluates active orders/positions against new price ticks.
        """
        pass

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """
        Returns account balance, equity, margin, and open position counts.
        """
        pass
