"""
Limit Retrace Execution Guard Component.
Manages 0.25x ATR Limit Order Placement, Expiration (3-bar limit),
Gap Fill Execution, and Signal Reversal Cancellation.
"""

from typing import Tuple, Dict, Any, Optional

class LimitOrderGuard:
    def __init__(self, retrace_atr_mult: float = 0.25, max_expiry_bars: int = 3, pip_size: float = 0.0001):
        self.retrace_atr_mult = retrace_atr_mult
        self.max_expiry_bars = max_expiry_bars
        self.pip_size = pip_size

    def calculate_limit_price(self, close_price: float, atr: float, direction: str) -> float:
        """
        Calculates limit retrace entry price.
        BUY Limit: Close - (0.25 * ATR)
        SELL Limit: Close + (0.25 * ATR)
        """
        retrace_dist = atr * self.retrace_atr_mult
        if direction == 'BUY':
            return round(close_price - retrace_dist, 5)
        else:
            return round(close_price + retrace_dist, 5)

    def evaluate_bar_fill(
        self,
        pending_order: Dict[str, Any],
        bar_high: float,
        bar_low: float,
        bar_open: float,
        current_bar_index: int
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Evaluates whether a pending limit order is filled, expired, or canceled.
        """
        direction = pending_order['direction']
        limit_price = pending_order['limit_price']
        signal_bar_idx = pending_order['signal_bar_idx']

        # 1. Check Expiry
        if (current_bar_index - signal_bar_idx) > self.max_expiry_bars:
            return False, "LIMIT_ORDER_EXPIRED", None

        # 2. Check Fill Condition
        is_filled = False
        fill_price = limit_price
        is_gap_fill = False

        if direction == 'BUY':
            if bar_low <= limit_price:
                is_filled = True
                # Check gap down
                if bar_open < limit_price:
                    fill_price = bar_open
                    is_gap_fill = True
        elif direction == 'SELL':
            if bar_high >= limit_price:
                is_filled = True
                # Check gap up
                if bar_open > limit_price:
                    fill_price = bar_open
                    is_gap_fill = True

        if is_filled:
            reason = "GAP_LIMIT_FILLED" if is_gap_fill else "LIMIT_ORDER_FILLED"
            fill_info = {
                'order_id': pending_order['order_id'],
                'direction': direction,
                'limit_price': limit_price,
                'fill_price': fill_price,
                'is_gap_fill': is_gap_fill,
                'fill_bar_index': current_bar_index
            }
            return True, reason, fill_info

        return False, "LIMIT_ORDER_PENDING", None

    def cancel_pending_order(self, pending_order: Dict[str, Any], reason: str = "SIGNAL_INVALIDATED") -> Dict[str, Any]:
        """
        Cancels a pending limit order cleanly.
        """
        return {
            'order_id': pending_order['order_id'],
            'status': 'CANCELED',
            'cancel_reason': f"PENDING_ORDER_CANCELED:{reason}"
        }
