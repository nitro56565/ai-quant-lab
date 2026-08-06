import pandas as pd
import numpy as np
import logging
from macro_engine.scores import MacroScoresCalculator
from macro_engine.context_index import MarketContextIndexCalculator

logger = logging.getLogger("MacroContextEngine")

class MacroContextEngine:
    """
    AI 1 — FAR-Certified Macro Context Engine.
    Processes ONLY admitted macroeconomic and risk sentiment features.
    Outputs certified scores, composite Market Context Index (0-100),
    and structured JSON explainability payloads.
    """
    def __init__(self, weights: dict = None) -> None:
        self.scores_calc = MacroScoresCalculator()
        self.index_calc = MarketContextIndexCalculator(weights=weights)

    def get_macro_context(self, symbol: str, timestamp: pd.Timestamp, df: pd.DataFrame, idx: int) -> dict:
        """
        Determines FAR-certified macro context scores for a given candle.
        """
        cb_divergence = self.scores_calc.calc_cb_divergence(symbol, timestamp)
        risk_sentiment = self.scores_calc.calc_risk_sentiment(df, idx)
        event_risk = self.scores_calc.calc_event_risk(timestamp)

        scores = {
            "cb_divergence": round(cb_divergence, 1),
            "risk_sentiment": round(risk_sentiment, 1),
            "event_risk": round(event_risk, 1)
        }

        # Calculate FAR-Certified Market Context Index (0-100)
        mci = self.index_calc.compute_context_index(scores)
        scores["market_context_index"] = round(mci, 1)

        # Generate structured explainability rationale
        rationale = self.index_calc.generate_rationale(scores, mci)
        scores["summary_rationale"] = rationale

        # Deprecated compatibility fields set to certified values
        scores["trend_macro"] = round(risk_sentiment, 1)
        scores["macro_alignment"] = round(cb_divergence, 1)
        scores["policy_divergence"] = round(cb_divergence, 1)
        scores["far_certified"] = True

        return scores
