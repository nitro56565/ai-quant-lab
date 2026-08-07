"""
Trade Decision Engine Module.
Evaluates model probability predictions, strategy threshold rules, and emits SIGNAL_GENERATED events.
"""

import logging
from live_trading_engine.events.event_bus import EventBus, Event, EventType
from live_trading_engine.persistence.prediction_ledger import PredictionLedger

logger = logging.getLogger(__name__)

class TradeDecisionReason:
    PROBABILITY_THRESHOLD = "PROBABILITY_THRESHOLD"
    EXPECTED_VALUE_FILTER = "EXPECTED_VALUE_FILTER"
    VOLATILITY_FILTER = "VOLATILITY_FILTER"
    RISK_VETO = "RISK_VETO"
    KILL_SWITCH = "KILL_SWITCH"

class TradeDecisionEngine:
    def __init__(self, event_bus: EventBus, ledger: PredictionLedger):
        self.event_bus = event_bus
        self.ledger = ledger
        self.event_bus.subscribe(EventType.MODEL_PREDICTION, self.on_model_prediction)

    def on_model_prediction(self, event: Event):
        data = event.data
        prob_long = data['prob_long']
        prob_short = data['prob_short']
        ev_long = data['net_ev_long']
        ev_short = data['net_ev_short']
        symbol = data['symbol']
        timestamp = data['timestamp']

        signal = None
        reason = "NO_SIGNAL"
        expected_ev = 0.0

        if prob_long >= 0.35 and ev_long > 0:
            signal = 'BUY'
            expected_ev = ev_long
            reason = f"Probability Long {prob_long:.4f} >= 0.35 & Net EV +{ev_long:.2f}p > 0"
        elif prob_short >= 0.34 and ev_short > 0:
            signal = 'SELL'
            expected_ev = ev_short
            reason = f"Probability Short {prob_short:.4f} >= 0.34 & Net EV +{ev_short:.2f}p > 0"

        # Record prediction to ledger
        self.ledger.record_prediction(
            timestamp=timestamp,
            symbol=symbol,
            prob_long=prob_long,
            prob_short=prob_short,
            expected_ev=expected_ev,
            atr=data['atr'],
            vol_rank_pct=data['vol_rank_pct'],
            model_version=data['model_id'],
            decision=signal or "REJECT",
            reason=reason
        )

        if signal:
            sig_data = {
                "timestamp": timestamp,
                "symbol": symbol,
                "signal_type": signal,
                "prob_long": prob_long,
                "prob_short": prob_short,
                "expected_ev": expected_ev,
                "atr": data['atr'],
                "vol_rank_pct": data['vol_rank_pct'],
                "ask": data['ask'],
                "bid": data['bid'],
                "model_id": data['model_id'],
                "reason": reason
            }
            # Publish SIGNAL_GENERATED event to Event Bus
            self.event_bus.publish(Event(EventType.SIGNAL_GENERATED, sig_data))
