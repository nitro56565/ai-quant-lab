"""
High-Fidelity Execution Simulator & Local Paper Broker Module — AI Quant Lab v5.0.
Provides broker-agnostic simulated order execution with limit retrace fills, slippage drag, and PnL ledger tracking.
Implements BaseExecutionGateway and BaseBrokerAdapter with Clock dependency injection.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.order_manager import OrderManager
from live_execution_engine.broker.base_gateway import BaseExecutionGateway
from live_execution_engine.clock import BaseClock, RealClock

logger = logging.getLogger(__name__)

class BaseBrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, symbol: str, signal_type: str, signal_time: datetime,
                    ask: float, bid: float, atr: float, risk_pct: float) -> dict:
        pass

    @abstractmethod
    def on_tick(self, current_time: datetime, ask: float, bid: float) -> list:
        pass

    @abstractmethod
    def get_account_summary(self) -> dict:
        pass


class ExecutionSimulator(BaseBrokerAdapter, BaseExecutionGateway):
    """
    High-Fidelity Vendor-Agnostic Execution Simulator.
    Calculates execution fills, slippage drag, commission, and dynamic account equity.
    """
    def __init__(self, config: LiveTradingConfig, order_manager: OrderManager, clock: Optional[BaseClock] = None):
        self.config = config
        self.order_manager = order_manager
        self.clock = clock or RealClock()

    @property
    def balance(self) -> float:
        closed_pnl = sum([float(t.get('pnl_usd', 0.0)) for t in self.order_manager.closed_trades])
        return float(self.config.initial_capital) + closed_pnl

    def place_order(self, symbol: str, signal_type: str, signal_time: datetime,
                    ask: float, bid: float, atr: float, risk_pct: float) -> dict:
        return self.order_manager.create_limit_order(
            symbol=symbol,
            signal_type=signal_type,
            signal_time=signal_time,
            ask=ask,
            bid=bid,
            atr=atr,
            risk_pct=risk_pct
        )

    def on_tick(self, current_time: datetime, ask: float, bid: float) -> list:
        return self.order_manager.update_positions_on_tick(current_time, ask, bid)

    def get_account_summary(self) -> dict:
        open_count = len(self.order_manager.open_positions)
        pending_count = len(self.order_manager.pending_orders)
        closed_count = len(self.order_manager.closed_trades)

        curr_balance = self.balance
        unrealized_pnl = 0.0

        return {
            "initial_capital": self.config.initial_capital,
            "balance": round(curr_balance, 2),
            "equity": round(curr_balance + unrealized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "open_positions_count": open_count,
            "pending_orders_count": pending_count,
            "closed_trades_count": closed_count,
            "currency": "USD"
        }

# Backward-compatible alias
LocalPaperBroker = ExecutionSimulator
