import numpy as np
import logging

logger = logging.getLogger("ExecutionPolicyEngine")

class ExecutionPolicyEngine:
    """
    AI 3 — Execution Policy Engine.
    Translates Context Scores (trend_alignment, volatility_state, event_risk)
    into smooth, bounded execution policy parameters:
    - Action: EXECUTE (100% signal retention)
    - Risk Multiplier: 0.75x to 1.25x base risk (capped at 1.0% max account risk)
    - TP Multiplier: Smooth step escalation (2.0R, 2.2R, 2.4R, 2.6R, 2.8R)
    - Time Exit: 6h (Low Vol), 12h (Med Vol), 24h (High Vol/Trend)
    - Trailing Stop: True when Trend Alignment >= 70 AND Volatility State >= 70
    """
    def __init__(self) -> None:
        pass

    def determine_policy(self, state_vector: dict) -> dict:
        trend_align = state_vector.get('trend_alignment', 50.0)
        vol_state = state_vector.get('volatility_state', 50.0)
        event_risk = state_vector.get('event_risk', 0.0)

        # High Event Risk Safety Override
        if event_risk >= 80.0:
            return {
                "action": "SKIP_TRADE",
                "risk_multiplier": 0.0,
                "tp_r_multiple": 0.0,
                "time_exit_hours": 0,
                "trailing_stop": False,
                "reason": "High news event risk proximity"
            }

        # 1. Smooth Granular TP Target Escalation (2.0R to 2.8R)
        if trend_align >= 80.0 and vol_state >= 70.0:
            tp_r = 2.8
            risk_mult = 1.25
        elif trend_align >= 70.0 or vol_state >= 70.0:
            tp_r = 2.6
            risk_mult = 1.15
        elif trend_align >= 50.0 and vol_state >= 50.0:
            tp_r = 2.4
            risk_mult = 1.00
        elif trend_align >= 40.0:
            tp_r = 2.2
            risk_mult = 0.85
        else:
            tp_r = 2.0
            risk_mult = 0.75

        # 2. Dynamic Holding Time Horizon (6h to 24h)
        if vol_state >= 70.0 and trend_align >= 60.0:
            time_exit_hours = 24
        elif vol_state >= 40.0:
            time_exit_hours = 12
        else:
            time_exit_hours = 6

        # 3. Trailing Stop Policy
        trailing_stop = (trend_align >= 70.0 and vol_state >= 70.0)

        return {
            "action": "EXECUTE",
            "risk_multiplier": round(risk_mult, 2),
            "tp_r_multiple": round(tp_r, 1),
            "time_exit_hours": time_exit_hours,
            "trailing_stop": trailing_stop,
            "reason": f"Context policy (Align: {trend_align}, Vol: {vol_state})"
        }

