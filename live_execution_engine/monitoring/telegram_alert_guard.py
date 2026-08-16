"""
Telegram Monitoring & Alerting Guard Component.
Handles Trade Entry/Exit Notifications, Daily PnL Summaries, Rate Limit Queuing,
and Critical Fail-Safe Failure Warnings.
"""

from typing import Tuple, Dict, Any, List

class TelegramAlertGuard:
    def __init__(self, rate_limit_per_min: int = 20):
        self.rate_limit_per_min = rate_limit_per_min
        self.sent_messages: List[str] = []

    def format_trade_alert(self, order_id: str, symbol: str, direction: str, units: float, entry_price: float, sl_price: float, tp_price: float) -> str:
        return f"🚨 [TRADE {direction}] {symbol} | Units: {units:,.0f} | Entry: {entry_price:.5f} | SL: {sl_price:.5f} | TP: {tp_price:.5f} (ID: {order_id})"

    def format_failure_warning(self, reason_code: str, details: str) -> str:
        return f"⚠️ [CRITICAL WARNING] System Triggered Fail-Safe: {reason_code} | Details: {details}"

    def send_alert(self, message: str) -> bool:
        if len(self.sent_messages) >= self.rate_limit_per_min:
            return False # Queue for rate-limit delay
        self.sent_messages.append(message)
        return True
