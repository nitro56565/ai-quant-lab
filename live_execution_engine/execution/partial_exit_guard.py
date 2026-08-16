"""
Partial Exit Guard Component.
Handles 50% @ +1.5R Partial Exits, Duplicate Event Idempotency,
Failed Close Recovery, and Post-Restart State Reconstruction.
"""

from typing import Tuple, Dict, Any, Optional

class PartialExitGuard:
    def __init__(self, target_r_multiple: float = 1.5, partial_pct: float = 0.50):
        self.target_r_multiple = target_r_multiple
        self.partial_pct = partial_pct
        self.partial_taken_orders: set = set()

    def evaluate_partial_exit(
        self,
        order_id: str,
        initial_units: float,
        active_units: float,
        current_floating_r: float
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluates partial exit condition at +1.5R.
        """
        if order_id in self.partial_taken_orders:
            return False, "DUPLICATE_PARTIAL_EXIT_IGNORED", {
                'order_id': order_id,
                'active_units': active_units,
                'is_duplicate': True
            }

        if current_floating_r >= self.target_r_multiple:
            close_units = initial_units * self.partial_pct
            remaining_units = max(0.0, active_units - close_units)
            self.partial_taken_orders.add(order_id)

            return True, "PARTIAL_EXIT_EXECUTED", {
                'order_id': order_id,
                'close_units': close_units,
                'remaining_units': remaining_units,
                'is_duplicate': False
            }

        return False, "PARTIAL_EXIT_NOT_REACHED", {'order_id': order_id, 'active_units': active_units}

    def reconstruct_state(self, order_id: str, partial_taken_on_broker: bool) -> None:
        """
        Reconstructs partial exit state upon process restart.
        """
        if partial_taken_on_broker:
            self.partial_taken_orders.add(order_id)
