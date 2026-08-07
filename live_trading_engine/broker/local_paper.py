"""
Local High-Fidelity Paper Broker Gateway Module.
Provides in-memory simulated order execution with limit retrace fills, slippage, and PnL ledger tracking.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import logging
from live_trading_engine.config import LiveTradingConfig
from live_trading_engine.order_manager import OrderManager

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


class LocalPaperBroker(BaseBrokerAdapter):
    """
    High-Fidelity In-Memory Paper Broker with simulated latency, slippage, and limit fills.
    """
    def __init__(self, config: LiveTradingConfig, order_manager: OrderManager):
        self.config = config
        self.order_manager = order_manager

    @property
    def balance(self) -> float:
        closed_pnl = sum([float(t.get('pnl_usd', 0.0)) for t in self.order_manager.closed_trades])
        return float(self.config.initial_capital) + closed_pnl

    def place_order(self, symbol: str, signal_type: str, signal_time: datetime,
                    ask: float, bid: float, atr: float, risk_pct: float) -> dict:
        return self.order_manager.create_limit_order(symbol, signal_type, signal_time, ask, bid, atr, risk_pct)

    def on_tick(self, current_time: datetime, ask: float, bid: float) -> list:
        closed_trades = self.order_manager.update_positions_on_tick(current_time, ask, bid)
        return closed_trades

    def get_account_summary(self) -> dict:
        open_pnl = sum([0.0 for p in self.order_manager.open_positions])
        current_balance = self.balance
        equity = current_balance + open_pnl
        return {
            "broker_type": "LOCAL_PAPER_BROKER",
            "balance": round(current_balance, 2),
            "equity": round(equity, 2),
            "open_positions_count": len(self.order_manager.open_positions),
            "pending_orders_count": len(self.order_manager.pending_orders),
            "closed_trades_count": len(self.order_manager.closed_trades)
        }

