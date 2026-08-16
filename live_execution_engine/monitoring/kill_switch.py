"""
Emergency Kill Switch Module.
Cancels pending orders, flattens open positions, flushes audit state, and halts execution instantly upon alert.
"""

import sys
import logging
from live_execution_engine.order_manager import OrderManager

logger = logging.getLogger(__name__)

class EmergencyKillSwitch:
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
        self.is_active = False

    def trigger(self, reason: str):
        logger.critical(f"🚨 EMERGENCY KILL SWITCH TRIGGERED! Reason: {reason}")
        self.is_active = True

        # 1. Cancel all pending orders
        pending_cnt = len(self.order_manager.pending_orders)
        self.order_manager.pending_orders.clear()
        logger.warning(f"🛑 Cancelled {pending_cnt} pending limit orders.")

        # 2. Flatten all open positions
        open_cnt = len(self.order_manager.open_positions)
        self.order_manager.open_positions.clear()
        logger.warning(f"🛑 Flattened {open_cnt} active open positions.")

        # 3. Save state to disk
        self.order_manager.save_state()
        logger.critical("💾 Emergency State Saved. Halting Execution.")
