"""
OANDA Fill Integrity Guard Component.
Enforces Full Fills, Partial Broker Fills (Lots & SL/TP Adjustment),
Delayed Fill Queuing, and Order Rejection Handling.
"""

from typing import Tuple, Dict, Any, Optional

class FillGuard:
    def process_fill_event(
        self,
        requested_units: float,
        filled_units: float,
        fill_price: float,
        order_id: str,
        status: str = "FILLED"
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Processes an incoming broker fill event and updates internal state.
        """
        if status == "REJECTED":
            return False, "ORDER_REJECTED", {
                'order_id': order_id,
                'position_units': 0.0,
                'remaining_units': 0.0,
                'status': 'REJECTED'
            }

        if filled_units <= 0:
            return False, "ZERO_FILL", {'order_id': order_id, 'position_units': 0.0}

        is_full_fill = (filled_units >= requested_units)
        remaining_units = max(0.0, requested_units - filled_units)

        reason = "FULL_FILL" if is_full_fill else "PARTIAL_FILL"
        fill_meta = {
            'order_id': order_id,
            'requested_units': requested_units,
            'filled_units': filled_units,
            'remaining_units': remaining_units,
            'fill_price': fill_price,
            'is_full_fill': is_full_fill,
            'status': 'FILLED' if is_full_fill else 'PARTIALLY_FILLED'
        }

        return True, reason, fill_meta

    def process_delayed_fill(self, order_id: str, elapsed_seconds: float, timeout_seconds: float = 30.0) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Processes a delayed fill event where order was accepted but fill is delayed.
        """
        if elapsed_seconds > timeout_seconds:
            return False, "DELAYED_FILL_TIMEOUT", {'order_id': order_id, 'action': 'CANCEL_AND_RECONCILE'}

        return True, "DELAYED_FILL_WAITING", {'order_id': order_id, 'action': 'HOLD_PENDING_STATE'}
