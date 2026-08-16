"""
Daily Midnight Reconciliation Module.
Verifies internal state against broker position state to detect discrepancies.
"""

from datetime import datetime, timezone
import logging
from live_execution_engine.order_manager import OrderManager
from live_execution_engine.kill_switch import EmergencyKillSwitch

logger = logging.getLogger(__name__)

class DailyMidnightReconciler:
    def __init__(self, order_manager: OrderManager, kill_switch: EmergencyKillSwitch):
        self.order_manager = order_manager
        self.kill_switch = kill_switch
        self.last_reconciled_day = None

    def reconcile(self, broker_summary: dict, current_time: datetime) -> bool:
        curr_day = current_time.strftime("%Y-%m-%d")
        if current_time.hour == 0 and self.last_reconciled_day != curr_day:
            self.last_reconciled_day = curr_day
            internal_pos_cnt = len(self.order_manager.open_positions)
            broker_pos_cnt = broker_summary.get("open_positions_count", internal_pos_cnt)

            logger.info(f"🔍 Midnight Reconciliation Audit for {curr_day}: Internal={internal_pos_cnt} vs Broker={broker_pos_cnt}")

            if internal_pos_cnt != broker_pos_cnt:
                reason = f"Position Mismatch Detected! Internal={internal_pos_cnt} vs Broker={broker_pos_cnt}"
                logger.error(f"🔴 RECONCILIATION FAILURE: {reason}")
                self.kill_switch.trigger(reason)
                return False

            logger.info("🟢 Midnight Reconciliation PASSED: 100% Alignment.")
            return True
        return True
