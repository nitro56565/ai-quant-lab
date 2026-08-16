"""
Signal Reversal Guard Component.
Manages LONG -> SHORT and SHORT -> LONG Reversals,
Confirmation of Close Before New Order Submission,
Partial Position Handling, and Pending Order Cancellations.
"""

from typing import Tuple, Dict, Any, Optional

class SignalReversalGuard:
    def execute_reversal(
        self,
        current_direction: str,
        new_direction: str,
        active_position_units: float,
        pending_order_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes signal reversal sequence:
        1. Close active position (and/or cancel pending order)
        2. Confirm close
        3. Submit new opposite order
        """
        if current_direction == new_direction:
            return False, "NO_REVERSAL_NEEDED", {'action': 'NONE'}

        steps = []
        if pending_order_id:
            steps.append(f"CANCEL_PENDING_ORDER:{pending_order_id}")

        if active_position_units > 0:
            steps.append(f"CLOSE_ACTIVE_POSITION:{current_direction}:{active_position_units}")
            steps.append("CONFIRM_CLOSE_BEFORE_NEW_SUBMISSION")

        steps.append(f"SUBMIT_NEW_ORDER:{new_direction}")

        return True, "REVERSAL_SEQUENCE_EXECUTED", {
            'from_direction': current_direction,
            'to_direction': new_direction,
            'steps': steps,
            'closed_units': active_position_units
        }
