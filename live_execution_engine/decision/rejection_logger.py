"""
Decision Trail & Primary Rejection Reason Logger.
Enforces that every rejected candidate bar outputs a structured audit trail
with EXACTLY ONE primary rejection reason code.

Supported Primary Rejection Codes:
1. LOW_PROBABILITY
2. NEGATIVE_EV
3. INVALID_REGIME
4. RISK_LIMIT_EXCEEDED
5. DAILY_DRAWDOWN_LIMIT
6. MAX_LEVERAGE_EXCEEDED
7. EXPOSURE_LIMIT_EXCEEDED
8. SPREAD_RESTRICTION
9. STALE_DATA
10. BROKER_UNAVAILABLE
11. EXISTING_CONFLICTING_POSITION
12. INVALID_MODEL_OUTPUT
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class DecisionTrailLogger:
    VALID_REJECTION_CODES = {
        "LOW_PROBABILITY",
        "NEGATIVE_EV",
        "INVALID_REGIME",
        "RISK_LIMIT_EXCEEDED",
        "DAILY_DRAWDOWN_LIMIT",
        "MAX_LEVERAGE_EXCEEDED",
        "EXPOSURE_LIMIT_EXCEEDED",
        "SPREAD_RESTRICTION",
        "STALE_DATA",
        "BROKER_UNAVAILABLE",
        "EXISTING_CONFLICTING_POSITION",
        "INVALID_MODEL_OUTPUT"
    }

    def format_decision_trail(
        self,
        timestamp: datetime,
        symbol: str,
        regime_status: str,
        pae_status: str,
        probability_status: str,
        ev_status: str,
        risk_status: str,
        broker_status: str,
        primary_rejection_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Formats a structured decision trail log object.
        """
        is_traded = (primary_rejection_code is None)

        if not is_traded:
            if primary_rejection_code not in self.VALID_REJECTION_CODES:
                raise ValueError(f"Invalid primary rejection code: {primary_rejection_code}")

        trail = {
            'timestamp': timestamp.isoformat(),
            'symbol': symbol,
            'status': 'TRADE' if is_traded else 'REJECT',
            'primary_rejection_code': primary_rejection_code if not is_traded else 'NONE',
            'audit_trail': {
                'hmm_regime': regime_status,
                'pae_model': pae_status,
                'probability': probability_status,
                'expected_value': ev_status,
                'risk_guardian': risk_status,
                'broker_connection': broker_status
            }
        }

        return trail
