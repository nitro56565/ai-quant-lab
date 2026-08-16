"""
Live Demo Forward Trading Telemetry Tracker Component.
Captures and persists all 33 granular trade metrics per live/demo trade for
continuous distributional parity validation against historical backtests.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class ForwardTelemetryTracker:
    def __init__(self, db_path: str = "local_data_workspace/databases/forward_telemetry.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_telemetry (
                trade_id TEXT PRIMARY KEY,
                signal_timestamp TEXT,
                hmm_state INT,
                volatility_quantile INT,
                state_9 INT,
                p_lgb REAL,
                p_cat REAL,
                p_xgb REAL,
                p_ensemble REAL,
                expected_value REAL,
                threshold REAL,
                pae_decision TEXT,
                rejection_reason TEXT,
                atr REAL,
                intended_entry REAL,
                actual_oanda_entry REAL,
                intended_sl REAL,
                actual_sl REAL,
                intended_tp REAL,
                actual_tp REAL,
                intended_lots REAL,
                actual_units REAL,
                spread_pips REAL,
                slippage_pips REAL,
                order_latency_ms REAL,
                fill_latency_ms REAL,
                partial_exit_price REAL,
                reversal_behavior TEXT,
                realized_r REAL,
                realized_pnl REAL,
                broker_transaction_id TEXT,
                local_ledger_state TEXT,
                oanda_state TEXT,
                recorded_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def record_telemetry(self, telemetry: Dict[str, Any]) -> bool:
        """
        Records all 33 granular trade metrics into SQLite telemetry store.
        """
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO trade_telemetry VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, datetime('now')
            )
        """, (
            telemetry.get('trade_id'),
            telemetry.get('signal_timestamp'),
            telemetry.get('hmm_state', 0),
            telemetry.get('volatility_quantile', 0),
            telemetry.get('state_9', 0),
            telemetry.get('p_lgb', 0.0),
            telemetry.get('p_cat', 0.0),
            telemetry.get('p_xgb', 0.0),
            telemetry.get('p_ensemble', 0.0),
            telemetry.get('expected_value', 0.0),
            telemetry.get('threshold', 0.38),
            telemetry.get('pae_decision', 'PAE_PASS'),
            telemetry.get('rejection_reason', 'NONE'),
            telemetry.get('atr', 0.0012),
            telemetry.get('intended_entry', 0.0),
            telemetry.get('actual_oanda_entry', 0.0),
            telemetry.get('intended_sl', 0.0),
            telemetry.get('actual_sl', 0.0),
            telemetry.get('intended_tp', 0.0),
            telemetry.get('actual_tp', 0.0),
            telemetry.get('intended_lots', 0.0),
            telemetry.get('actual_units', 0.0),
            telemetry.get('spread_pips', 0.3),
            telemetry.get('slippage_pips', 0.0),
            telemetry.get('order_latency_ms', 0.0),
            telemetry.get('fill_latency_ms', 0.0),
            telemetry.get('partial_exit_price', 0.0),
            telemetry.get('reversal_behavior', 'NONE'),
            telemetry.get('realized_r', 0.0),
            telemetry.get('realized_pnl', 0.0),
            telemetry.get('broker_transaction_id', 'MOCK_TX_123'),
            telemetry.get('local_ledger_state', 'CLOSED'),
            telemetry.get('oanda_state', 'CLOSED')
        ))
        conn.commit()
        conn.close()
        return True

    def get_all_telemetry(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM trade_telemetry")
        rows = cur.fetchall()
        conn.close()

        result = []
        for r in rows:
            result.append({
                'trade_id': r[0], 'signal_timestamp': r[1], 'hmm_state': r[2],
                'volatility_quantile': r[3], 'state_9': r[4], 'p_lgb': r[5],
                'p_cat': r[6], 'p_xgb': r[7], 'p_ensemble': r[8], 'expected_value': r[9],
                'threshold': r[10], 'pae_decision': r[11], 'rejection_reason': r[12],
                'atr': r[13], 'intended_entry': r[14], 'actual_oanda_entry': r[15],
                'intended_sl': r[16], 'actual_sl': r[17], 'intended_tp': r[18],
                'actual_tp': r[19], 'intended_lots': r[20], 'actual_units': r[21],
                'spread_pips': r[22], 'slippage_pips': r[23], 'order_latency_ms': r[24],
                'fill_latency_ms': r[25], 'partial_exit_price': r[26], 'reversal_behavior': r[27],
                'realized_r': r[28], 'realized_pnl': r[29], 'broker_transaction_id': r[30],
                'local_ledger_state': r[31], 'oanda_state': r[32]
            })
        return result
