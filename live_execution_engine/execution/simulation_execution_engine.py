"""
Simulation Execution Engine Module — AI Quant Lab v5.0.
Handles local simulated tick matching, limit order retrace fills, and TP/SL execution
exclusively for Backtesting, Paper Simulation, and Forensic Replay.

Architecturally decoupled from OANDA Live Broker Execution.
Prohibited from being invoked in live broker mode.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.execution.order_manager import OrderManager

logger = logging.getLogger(__name__)

class SimulationExecutionEngine:
    """
    Local Paper Simulation Execution Engine.
    Executes limit order fills and TP/SL hits against local market ticks.
    """
    def __init__(self, config: LiveTradingConfig, order_manager: OrderManager):
        self.config = config
        self.order_manager = order_manager
        logger.info("🟢 SimulationExecutionEngine Initialized: High-Fidelity Local Paper Simulator Active.")

    def place_order(
        self, symbol: str, signal_type: str, signal_time: datetime,
        ask: float, bid: float, atr: float, risk_pct: float
    ) -> Dict[str, Any]:
        """
        Creates local limit order spec in OrderManager.
        """
        return self.order_manager.create_limit_order(
            symbol=symbol,
            signal_type=signal_type,
            signal_time=signal_time,
            ask=ask,
            bid=bid,
            atr=atr,
            risk_pct=risk_pct
        )

    def on_tick(self, current_time: datetime, ask: float, bid: float) -> List[Dict[str, Any]]:
        """
        Evaluates local order state against incoming market ticks.
        """
        return self.order_manager.update_positions_on_tick(current_time, ask, bid)

    def get_account_summary(self) -> Dict[str, Any]:
        """
        Returns local simulated account summary.
        """
        closed_pnl = sum([float(t.get('pnl_usd', 0.0)) for t in self.order_manager.closed_trades])
        b = float(self.config.initial_capital) + closed_pnl
        return {
            "initial_capital": self.config.initial_capital,
            "balance": round(b, 2),
            "equity": round(b, 2),
            "unrealized_pnl": 0.0,
            "open_positions_count": len(self.order_manager.open_positions),
            "pending_orders_count": len(self.order_manager.pending_orders),
            "closed_trades_count": len(self.order_manager.closed_trades),
            "currency": "USD",
            "source": "LOCAL_SIMULATOR"
        }
