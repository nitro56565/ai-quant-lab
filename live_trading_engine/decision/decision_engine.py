"""
Decision Engine Module v3.0.
Decoupled decision layer evaluating signal probability, expected value, correlation, and market context.
Outputs actionable Trade Decision objects (EXECUTE, REDUCE_RISK, SKIP, DELAY, CANCEL).
"""

import logging
from typing import Dict, Any
from live_trading_engine.events.event_bus import EventBus, Event, EventType
from live_trading_engine.trade_decision import TradeDecisionReason

logger = logging.getLogger(__name__)

class DecisionOutcome:
    EXECUTE = "EXECUTE"
    REDUCE_RISK = "REDUCE_RISK"
    SKIP = "SKIP"
    DELAY = "DELAY"
    CANCEL = "CANCEL"

class DecisionEngine:
    def __init__(self, event_bus: EventBus, min_prob: float = 0.34, min_ev: float = 0.0, db_manager: Any = None):
        self.event_bus = event_bus
        self.min_prob = min_prob
        self.min_ev = min_ev
        self.db = db_manager
        self.event_bus.subscribe(EventType.SIGNAL_GENERATED, self.on_signal_generated)
        logger.info(f"🟢 Decision Engine Initialized (Min Prob: {min_prob}, Min EV: {min_ev}pips)")

    def evaluate_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates incoming ML signal and determines quantitative trade decision outcome.
        """
        symbol = signal_data.get("symbol", "EURUSD")
        prob_long = signal_data.get("probability_long", signal_data.get("prob_long", 0.0))
        prob_short = signal_data.get("probability_short", signal_data.get("prob_short", 0.0))
        ev_long = signal_data.get("ev_long_pips", signal_data.get("net_ev_long", 0.0))
        ev_short = signal_data.get("ev_short_pips", signal_data.get("net_ev_short", 0.0))

        direction = None
        probability = 0.0
        expected_value = 0.0

        if prob_long >= self.min_prob and ev_long > self.min_ev:
            direction = "BUY"
            probability = prob_long
            expected_value = ev_long
        elif prob_short >= self.min_prob and ev_short > self.min_ev:
            direction = "SELL"
            probability = prob_short
            expected_value = ev_short

        outcome = DecisionOutcome.EXECUTE if direction else DecisionOutcome.SKIP
        reason = (
            f"Probability {direction} {probability:.4f} >= {self.min_prob} & Net EV {expected_value:+.2f}p > {self.min_ev}"
            if direction
            else f"Signal below threshold (Long p={prob_long:.2f}/ev={ev_long:.1f}p, Short p={prob_short:.2f}/ev={ev_short:.1f}p)"
        )

        decision_payload = {
            "outcome": outcome,
            "symbol": symbol,
            "direction": direction,
            "probability": probability,
            "expected_value": expected_value,
            "prob_long": prob_long,
            "prob_short": prob_short,
            "ev_long": ev_long,
            "ev_short": ev_short,
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
            logger.debug(f"ℹ️ DecisionEngine SKIPPED: {result['reason']}")

