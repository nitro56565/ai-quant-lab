import numpy as np
import logging

logger = logging.getLogger("MarketContextIndexCalculator")

class MarketContextIndexCalculator:
    """
    FAR-Certified Market Context Index Calculator.
    Aggregates ONLY admitted features (cb_divergence and risk_sentiment) using configurable weights.
    Default Configurable Weights:
    - Central Bank Divergence: 60% (FAR Delta +0.26, WF 100%)
    - Risk Sentiment Metric: 40% (FAR rs +1.00, WF 71.4%)
    """
    def __init__(self, weights: dict = None) -> None:
        if weights is None:
            self.weights = {
                'cb_divergence': 0.60,
                'risk_sentiment': 0.40,
                'event_risk_penalty': 0.10
            }
        else:
            self.weights = weights

    def compute_context_index(self, scores: dict) -> float:
        """
        Computes FAR-Certified Market Context Index (0-100).
        """
        cb_divergence = scores.get('cb_divergence', 50.0)
        risk_sentiment = scores.get('risk_sentiment', 50.0)
        event_risk = scores.get('event_risk', 10.0)

        w = self.weights
        composite = (
            w.get('cb_divergence', 0.60) * cb_divergence +
            w.get('risk_sentiment', 0.40) * risk_sentiment -
            w.get('event_risk_penalty', 0.10) * event_risk
        )
        return float(np.clip(composite, 0.0, 100.0))

    def generate_rationale(self, scores: dict, index_score: float) -> str:
        """
        Generates structured 1-sentence human-readable rationale for trade logging and debugging.
        """
        event_risk = scores.get('event_risk', 10.0)
        cb_div = scores.get('cb_divergence', 50.0)
        risk_sent = scores.get('risk_sentiment', 50.0)

        reasons = []
        if event_risk >= 80.0:
            reasons.append("HIGH NEWS EVENT RISK PROXIMITY (Level 1 Risk Reduction)")
        else:
            reasons.append("Low news event risk horizon")

        if cb_div >= 75.0:
            reasons.append("strong central bank monetary policy rate divergence (FAR Admitted)")
        elif cb_div >= 50.0:
            reasons.append("moderate central bank rate divergence")

        if risk_sent >= 60.0:
            reasons.append("stable risk-on sentiment (FAR Admitted)")

        return f"Certified Market Context Index {index_score:.1f}: " + " + ".join(reasons)
