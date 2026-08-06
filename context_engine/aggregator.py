import pandas as pd
import numpy as np
import logging

from market_state_engine.state_calculator import MarketStateEngine
from macro_engine.parser import MacroContextEngine

logger = logging.getLogger("MarketContextAggregator")

class MarketContextAggregator:
    """
    Combines outputs from:
    1. AI 1: Macro Context Engine (6 Sub-Scores, Market Context Index, Event Risk)
    2. AI 2: Quantitative Market State Engine (Trend Strength, Quality, Volatility, Liquidity)
    3. Meta-Labeler (P(Win) confidence)

    Outputs the Structured Market State Vector JSON & Edge Confidence score (0-100).
    """
    def __init__(self) -> None:
        self.market_state_engine = MarketStateEngine()
        self.macro_engine = MacroContextEngine()

    def build_state_vector(
        self,
        df: pd.DataFrame,
        idx: int,
        symbol: str,
        candidate_direction: str,
        meta_confidence: float
    ) -> dict:
        row = df.iloc[idx]
        timestamp = row.name if isinstance(row.name, pd.Timestamp) else pd.to_datetime(df.index[idx])

        # 1. AI 2: Market State
        m_state = self.market_state_engine.compute_market_state(df, idx)

        # 2. AI 1: Macro Context
        m_macro = self.macro_engine.get_macro_context(symbol, timestamp, df, idx)

        # 3. Calculate Edge Confidence (0 - 100)
        meta_score = meta_confidence * 100.0
        edge_conf = (
            (0.40 * meta_score) +
            (0.25 * m_state['trend_quality']) +
            (0.25 * max(m_macro['macro_alignment'], 0.0)) -
            (0.10 * m_macro['event_risk'])
        )
        edge_confidence = float(np.clip(edge_conf, 0.0, 100.0))

        return {
            "timestamp": str(timestamp),
            "symbol": symbol,
            "candidate_direction": candidate_direction,
            "meta_confidence": round(meta_confidence, 4),
            "market_state": m_state,
            "macro_context": m_macro,
            "market_context_index": m_macro.get("market_context_index", 50.0),
            "edge_confidence": round(edge_confidence, 1)
        }
