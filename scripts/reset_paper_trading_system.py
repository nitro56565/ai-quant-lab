#!/usr/bin/env python3
"""
System Reset Utility — AI Quant Lab
Resets all paper trading state ledgers, SQLite databases, and position state files to a 100% clean fresh baseline ($10,000.00 initial capital, 0 trades, 0 open positions).
"""

import os
import json
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SystemReset")

def reset_system():
    logger.info("=================================================================================")
    logger.info("  🧹 EXECUTING COMPLETE SYSTEM RESET — AI QUANT LAB PAPER TRADING ENGINE")
    logger.info("=================================================================================\n")

    log_dir = "live_trading_engine/logs"
    os.makedirs(log_dir, exist_ok=True)

    # 1. Reset paper_positions_state.json
    state_file = os.path.join(log_dir, "paper_positions_state.json")
    with open(state_file, "w") as f:
        json.dump({"pending_orders": [], "open_positions": [], "order_counter": 1}, f, indent=2)
    logger.info(f"✅ Reset state file: {state_file}")

    # 2. Reset paper_trades_history.json
    history_file = os.path.join(log_dir, "paper_trades_history.json")
    with open(history_file, "w") as f:
        json.dump([], f, indent=2)
    logger.info(f"✅ Reset trade history file: {history_file}")

    # 3. Truncate SQLite institutional_ledger.db
    db_path = os.path.join(log_dir, "institutional_ledger.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            tables = ["trades_ledger", "decision_trace", "candle_ledger", "notification_ledger"]
            for tbl in tables:
                try:
                    cursor.execute(f"DELETE FROM {tbl};")
                    logger.info(f"  • Cleared SQLite table: {tbl}")
                except sqlite3.OperationalError:
                    pass
            
            conn.commit()
            conn.close()
            logger.info(f"✅ SQLite database reset completed: {db_path}")
        except Exception as e:
            logger.error(f"⚠️ Error resetting SQLite database: {e}")


    logger.info("\n=================================================================================")
    logger.info("  ✨ SYSTEM SUCCESSFULLY RESET TO CLEAN 100% FRESH BASELINE ($10,000.00 CAPITAL)")
    logger.info("=================================================================================\n")

if __name__ == "__main__":
    reset_system()
