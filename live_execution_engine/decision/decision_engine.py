"""
Decision Engine Module v3.0.
Decoupled decision layer evaluating signal probability, expected value, correlation, and market context.
Outputs actionable Trade Decision objects (EXECUTE, REDUCE_RISK, SKIP, DELAY, CANCEL).
"""

import logging
from typing import Dict, Any, Optional
from live_execution_engine.events.event_bus import EventBus, Event, EventType
from live_execution_engine.trade_decision import TradeDecisionReason

logger = logging.getLogger(__name__)

from live_execution_engine.decision.pae_decision_guard import PAEDecisionGuard

class DecisionOutcome:
    EXECUTE = "EXECUTE"
    REDUCE_RISK = "REDUCE_RISK"
    SKIP = "SKIP"
    DELAY = "DELAY"
    CANCEL = "CANCEL"

class DecisionEngine:
    def __init__(self, event_bus: EventBus, min_prob: Optional[float] = None, min_ev: float = 0.0, db_manager: Any = None):
        self.event_bus = event_bus
        self.custom_min_prob = min_prob  # None means use dynamic regime-calibrated thresholds (0.42 range / 0.38 trend)
        self.min_ev = min_ev
        self.db = db_manager
        self.pae_guard = PAEDecisionGuard()
        self.event_bus.subscribe(EventType.SIGNAL_GENERATED, self.on_signal_generated)
        logger.info(f"🟢 Decision Engine Initialized with PAEDecisionGuard (Regime Thresholds: 0.42 Range / 0.38 Trend, EV > {min_ev}R)")

    def evaluate_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates incoming ML signal through PAEDecisionGuard.
        """
        symbol = signal_data.get("symbol", "EURUSD")
        prob_long = signal_data.get("probability_long", signal_data.get("prob_long", 0.0))
        prob_short = signal_data.get("probability_short", signal_data.get("prob_short", 0.0))
        regime_state_9 = signal_data.get("regime_state_9", 4)  # Default 4 (Range regime)

        # Extract individual model probabilities for proper PAE disagreement math
        p_l_lgb = signal_data.get("p_long_lgb", prob_long)
        p_l_cat = signal_data.get("p_long_cat", prob_long)
        p_l_xgb = signal_data.get("p_long_xgb", prob_long)
        p_s_lgb = signal_data.get("p_short_lgb", prob_short)
        p_s_cat = signal_data.get("p_short_cat", prob_short)
        p_s_xgb = signal_data.get("p_short_xgb", prob_short)
        vol_rank_pct = signal_data.get("vol_rank_pct", signal_data.get("feature_snapshot", {}).get("feat_vol_atr_pct", 50.0))

        # Evaluate through certified PAEDecisionGuard
        is_pass, reason_code, pae_info = self.pae_guard.evaluate_decision(
            p_long_lgb=p_l_lgb, p_long_cat=p_l_cat, p_long_xgb=p_l_xgb,
            p_short_lgb=p_s_lgb, p_short_cat=p_s_cat, p_short_xgb=p_s_xgb,
            regime_state_9=regime_state_9,
            custom_threshold=self.custom_min_prob,
            win_reward_r=1.8, loss_risk_r=1.0, friction_r=0.15,
            vol_rank_pct=vol_rank_pct
        )

        direction = None
        probability = 0.0
        expected_value = 0.0
        required_p = 0.42

        if is_pass and pae_info:
            direction = pae_info.get("direction")
            probability = pae_info.get("ensemble_prob", 0.0)
            expected_value = pae_info.get("expected_value_r", 0.0)
            required_p = pae_info.get("required_p", 0.42)
            outcome = DecisionOutcome.EXECUTE
            reason = f"Probability {direction} {probability:.4f} >= {required_p} & Net EV {expected_value:+.2f}R > {self.min_ev}"
        else:
            outcome = DecisionOutcome.SKIP
            reason = f"Rejected due to {reason_code.replace('_', ' ').title()} (Buy Prob: {prob_long*100:.1f}%, Sell Prob: {prob_short*100:.1f}%)"

        decision_payload = {
            "outcome": outcome,
            "symbol": symbol,
            "direction": direction,
            "probability": probability,
            "expected_value": expected_value,
            "required_p": required_p,
            "prob_long": prob_long,
            "prob_short": prob_short,
            "ev_long": signal_data.get("ev_long_pips", 0.0),
            "ev_short": signal_data.get("ev_short_pips", 0.0),
            "ask": signal_data.get("ask"),
            "bid": signal_data.get("bid"),
            "timestamp": signal_data.get("timestamp"),
            "rolling_bars_df": signal_data.get("rolling_bars_df"),
            "feature_snapshot": signal_data.get("feature_snapshot", {}),
            "reason": reason
        }

        if self.db and hasattr(self.db, "save_decision_trace"):
            self.db.save_decision_trace(decision_payload)

        return decision_payload

    def on_signal_generated(self, event: Event):
        signal_data = event.data
        result = self.evaluate_signal(signal_data)

        if result["outcome"] == DecisionOutcome.EXECUTE:
            logger.info(f"⚡ DecisionEngine APPROVED: {result['direction']} {result['symbol']} | Reason: {result['reason']}")
            self.event_bus.publish(Event(EventType.ORDER_REQUEST, result))
        else:
            logger.info(f"ℹ️ DecisionEngine SKIPPED: {result['reason']}")

