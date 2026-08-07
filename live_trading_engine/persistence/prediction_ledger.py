"""
Prediction Ledger & Trade Explainability Module.
Persists every single H1 prediction and generates comprehensive Trade Decision Reports.
"""

import json
import os
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class PredictionLedger:
    def __init__(self, log_dir: str = "live_trading_engine/logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.ledger_file = os.path.join(self.log_dir, "prediction_ledger.parquet")
        self.json_ledger_file = os.path.join(self.log_dir, "prediction_ledger.json")
        self.records = []

    def record_prediction(self, timestamp: str, symbol: str, prob_long: float, prob_short: float,
                          expected_ev: float, atr: float, vol_rank_pct: float, model_version: str,
                          decision: str, reason: str, order_id: str = None) -> dict:
        entry = {
            "timestamp": timestamp,
            "symbol": symbol,
            "prob_long": float(prob_long),
            "prob_short": float(prob_short),
            "expected_ev": float(expected_ev),
            "atr": float(atr),
            "vol_rank_pct": float(vol_rank_pct),
            "model_version": model_version,
            "decision": decision,
            "reason": reason,
            "order_id": order_id or "N/A"
        }
        self.records.append(entry)
        self._flush_to_disk()
        return entry

    def print_trade_decision_report(self, entry: dict, meta_label: str = "PASS", macro_score: float = 65.0, regime_state: str = "BULL"):
        report = f"""
=================================================================================
  🤖 TRADE DECISION REPORT — {entry['decision']} {entry['symbol']}
=================================================================================
  Timestamp:         {entry['timestamp']}
  Probability Long:  {entry['prob_long']:.4f} (Threshold: 0.35)
  Probability Short: {entry['prob_short']:.4f} (Threshold: 0.34)
  Expected Value:    +{entry['expected_ev']:.2f} pips
  ATR Volatility:    {entry['atr']:.5f} (Vol Percentile: {entry['vol_rank_pct']:.1f}%)
  Meta Label Status: {meta_label}
  Macro Context:     {macro_score:.1f} Index
  HMM Regime:        {regime_state}
  Model Version:     {entry['model_version']}
  Order ID:          {entry['order_id']}
  Decision Reason:   {entry['reason']}
=================================================================================
"""
        logger.info(report)

    def _flush_to_disk(self):
        try:
            df = pd.DataFrame(self.records)
            df.to_parquet(self.ledger_file, index=False)
            with open(self.json_ledger_file, "w") as f:
                json.dump(self.records, f, indent=2)
        except Exception as e:
            logger.error(f"Error flushing prediction ledger: {e}")
