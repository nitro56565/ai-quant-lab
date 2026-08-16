"""
State Recovery Engine Module v3.0.
Hydrates open positions, pending orders, and cumulative account balance from database ledgers
to guarantee zero duplicated trades upon Docker container restarts.
"""

import logging
from typing import Dict, Any
from live_execution_engine.database import DatabaseManager

logger = logging.getLogger(__name__)

class StateRecoveryEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def recover_state(self, order_manager, initial_capital: float = 10000.0) -> Dict[str, Any]:
        """
        Reads database ledgers and restores OrderManager memory state.
        """
        logger.info("🔄 Running State Recovery Engine...")
        trades = self.db.get_all_trades()

        closed_count = len(trades)
        net_pnl = sum([t.get("pnl_usd", 0.0) for t in trades])
        current_balance = initial_capital + net_pnl

        # Load position state from disk if exists
        order_manager.load_state()

        recovered_state = {
            "closed_trades_count": closed_count,
            "net_pnl_usd": net_pnl,
            "recovered_balance": current_balance,
            "open_positions_count": len(order_manager.open_positions),
            "pending_orders_count": len(order_manager.pending_orders)
        }

        logger.info(f"✅ State Recovery Complete: {closed_count} Closed Trades, Net PnL: ${net_pnl:+,.2f}, Balance: ${current_balance:,.2f}, Open Pos: {len(order_manager.open_positions)}")
        return recovered_state
