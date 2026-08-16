"""
Critical Order Idempotency & Network Timeout Recovery Guard Component.
Prevents duplicate order submissions and recovers missing responses via broker API query.
"""

from typing import Tuple, Dict, Any, Optional, Set, List

class OrderIdempotencyGuard:
    def __init__(self):
        self.processed_order_ids: Set[str] = set()
        self.active_positions: Dict[str, Dict[str, Any]] = {}

    def process_order_event(self, order_id: str, fill_units: float, fill_price: float, direction: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Processes an incoming fill event idempotently.
        """
        # 1. Idempotency Check
        if order_id in self.processed_order_ids:
            return False, "DUPLICATE_ORDER_EVENT_IGNORED", {
                'order_id': order_id,
                'is_duplicate': True,
                'updated_positions_count': len(self.active_positions)
            }

        # Mark as processed
        self.processed_order_ids.add(order_id)
        self.active_positions[order_id] = {
            'order_id': order_id,
            'direction': direction,
            'units': fill_units,
            'price': fill_price
        }

        return True, "ORDER_EVENT_PROCESSED", {
            'order_id': order_id,
            'is_duplicate': False,
            'updated_positions_count': len(self.active_positions)
        }

    def recover_from_timeout(
        self,
        attempted_order_id: str,
        attempted_direction: str,
        attempted_units: float,
        broker_account_positions: List[Dict[str, Any]]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Queries broker API after network timeout to discover whether order was executed.
        Prevents submitting duplicate orders!
        """
        # Search broker account for existing position with attempted_order_id or matching direction/units
        existing_broker_match = None
        for p in broker_account_positions:
            if p.get('order_id') == attempted_order_id or (p.get('direction') == attempted_direction and abs(p.get('units', 0) - attempted_units) < 1e-4):
                existing_broker_match = p
                break

        if existing_broker_match is not None:
            # Order WAS executed on broker! Reconcile internally without submitting new order.
            self.processed_order_ids.add(attempted_order_id)
            self.active_positions[attempted_order_id] = existing_broker_match

            return True, "RECONCILED_EXISTING_BROKER_ORDER", {
                'duplicate_submitted': False,
                'reconciled': True,
                'order_id': attempted_order_id,
                'action': 'DO_NOT_SUBMIT_SECOND_BUY'
            }
        else:
            # Order was NOT executed on broker. Safe to handle cleanly.
            return False, "BROKER_ORDER_NOT_EXECUTED", {
                'duplicate_submitted': False,
                'reconciled': False,
                'order_id': attempted_order_id,
                'action': 'SAFE_TO_RETRY_OR_CANCEL'
            }
