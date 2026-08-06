import numpy as np
import logging

logger = logging.getLogger("ExecutionPolicyEngine")

class ExecutionPolicyEngine:
    """
    AI 3 — Execution Policy Engine (Refined Institutional Policy).
    Translates Market State Vectors & Macro Context Scores into bounded execution parameters.
    
    Refined Institutional Safety Principles:
    - Defensive Risk Sizing (Phase 1): Risk multiplier is capped between 0.50x and 1.00x base risk.
    - Level 1 Event Risk Reduction: High event risk (>= 80.0) applies 0.50x risk + 6h tight exit.
    - Full Explainability: Generates audit-ready JSON diagnostic payload for every trade execution.
    """
    def __init__(self, allow_risk_expansion: bool = False) -> None:
        self.allow_risk_expansion = allow_risk_expansion

    def determine_policy(self, state_vector: dict) -> dict:
        macro_ctx = state_vector.get('macro_context', {})
        m_state = state_vector.get('market_state', {})
        
        event_risk = float(macro_ctx.get('event_risk', state_vector.get('event_risk', 10.0)))
        trend_align = float(state_vector.get('trend_alignment', m_state.get('trend_strength', 50.0)))
        vol_state = float(state_vector.get('volatility_state', m_state.get('volatility_score', 50.0)))
        mci = float(state_vector.get('market_context_index', macro_ctx.get('market_context_index', 50.0)))
        rationale = macro_ctx.get('summary_rationale', f"Market Context Index {mci:.1f}")

        # Level 1 Event Risk Reduction (High news proximity: 0.50x risk + 6h tight exit)
        if event_risk >= 80.0:
            return {
                "action": "EXECUTE_REDUCED",
                "risk_multiplier": 0.50,
                "tp_r_multiple": 1.5,
                "time_exit_hours": 6,
                "trailing_stop": False,
                "reason": f"Level 1 Event Risk Reduction (Event Risk {event_risk:.1f}): 0.50x Risk + 6h Exit Horizon",
                "explainability": {
                    "event_risk": event_risk,
                    "market_context_index": mci,
                    "risk_multiplier": 0.50,
                    "rationale": rationale
                }
            }

        # 1. TP Target Escalation (1.5R to 2.8R)
        if mci >= 75.0 or (trend_align >= 75.0 and vol_state >= 60.0):
            tp_r = 2.8
            risk_mult = 1.25 if self.allow_risk_expansion else 1.00
        elif mci >= 60.0 or (trend_align >= 60.0):
            tp_r = 2.4
            risk_mult = 1.00
        elif mci >= 45.0:
            tp_r = 2.0
            risk_mult = 0.85
        else:
            tp_r = 1.5
            risk_mult = 0.50

        # Phase 1 Safety Constraint: Cap risk_multiplier to 1.00x max unless expansion explicitly enabled
        if not self.allow_risk_expansion:
            risk_mult = min(risk_mult, 1.00)

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
            "reason": rationale,
            "explainability": {
                "trend_macro": macro_ctx.get("trend_macro", 50.0),
                "risk_sentiment": macro_ctx.get("risk_sentiment", 50.0),
                "cb_divergence": macro_ctx.get("cb_divergence", 50.0),
                "event_risk": event_risk,
                "cot_score": macro_ctx.get("cot_score", 50.0),
                "liquidity": macro_ctx.get("liquidity", 50.0),
                "market_context_index": mci,
                "risk_multiplier": round(risk_mult, 2),
                "tp_multiplier": round(tp_r, 1),
                "rationale": rationale
            }
        }
