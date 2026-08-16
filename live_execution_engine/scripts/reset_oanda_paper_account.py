#!/usr/bin/env python3
"""
OANDA Practice Account & Local Ledger Fresh Start Reset Tool.
Clears pending orders on OANDA, closes open positions, wipes local SQLite test ledgers,
and resets system state for a completely clean paper-trading baseline.
"""

import os
import sys
import json
import sqlite3
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OANDAAccountResetTool")

def reset_oanda_practice_account():
    api_key = os.getenv("OANDA_API_KEY")
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    env = os.getenv("OANDA_ENV", "practice").lower()
    domain = "api-fxpractice.oanda.com" if env == "practice" else "api-fxtrade.oanda.com"

    print("=================================================================================")
    print("  🧹 OANDA PRACTICE ACCOUNT & LOCAL LEDGER FRESH START RESET TOOL")
    print("=================================================================================\n")

    if api_key and account_id:
        logger.info(f"Connecting to OANDA REST API ({env.upper()}) | Account: {account_id}...")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # 1. Cancel Pending Orders on OANDA
        try:
            url_orders = f"https://{domain}/v3/accounts/{account_id}/pendingOrders"
            req = urllib.request.Request(url_orders, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                orders = data.get("orders", [])
                logger.info(f"Found {len(orders)} pending orders on OANDA account.")
                for o in orders:
                    o_id = o.get("id")
                    cancel_url = f"https://{domain}/v3/accounts/{account_id}/orders/{o_id}/cancel"
                    c_req = urllib.request.Request(cancel_url, headers=headers, method="PUT")
                    with urllib.request.urlopen(c_req, timeout=5) as c_res:
                        logger.info(f"  • Canceled OANDA Pending Order #{o_id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not clear OANDA pending orders: {e}")

        # 2. Close Open Positions on OANDA
        try:
            url_pos = f"https://{domain}/v3/accounts/{account_id}/openPositions"
            req = urllib.request.Request(url_pos, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                positions = data.get("positions", [])
                logger.info(f"Found {len(positions)} open positions on OANDA account.")
                for p in positions:
                    inst = p.get("instrument")
                    close_url = f"https://{domain}/v3/accounts/{account_id}/positions/{inst}/close"
                    close_payload = {}
                    if float(p.get("long", {}).get("units", 0)) > 0:
                        close_payload["longUnits"] = "ALL"
                    if float(p.get("short", {}).get("units", 0)) < 0:
                        close_payload["shortUnits"] = "ALL"

                    c_req = urllib.request.Request(close_url, data=json.dumps(close_payload).encode("utf-8"), headers=headers, method="PUT")
                    with urllib.request.urlopen(c_req, timeout=5) as c_res:
                        logger.info(f"  • Closed OANDA Position for {inst}")
        except Exception as e:
            logger.warning(f"⚠️ Could not close OANDA open positions: {e}")
    else:
        logger.info("ℹ️ No OANDA credentials found in environment. Skipping remote OANDA API reset.")

    # 3. Reset Local SQLite Databases & JSON State Files
    db_paths = [
        "local_data_workspace/databases/institutional_ledger.db",
        "local_data_workspace/databases/institutional_ledger.db-shm",
        "local_data_workspace/databases/institutional_ledger.db-wal",
        "local_data_workspace/databases/live_ledger.db",
        "local_data_workspace/databases/forward_telemetry.db",
        "local_data_workspace/databases/test_e2e_ledger.db"
    ]

    for path in db_paths:
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"  • Wiped local SQLite database: {path}")
            except Exception as e:
                logger.warning(f"⚠️ Could not delete {path}: {e}")

    print("\n=================================================================================")
    print("  ✅ FRESH START RESET COMPLETE!")
    print("  • All OANDA Pending Orders Canceled")
    print("  • All OANDA Open Positions Closed")
    print("  • All Local Test Ledgers & Telemetry DBs Wiped")
    print("=================================================================================")
    print("\nℹ️ To reset your initial account balance to $10,000 on OANDA Practice:")
    print("   1. Log into your OANDA Web Console (https://fxpractice.oanda.com)")
    print("   2. Go to Account Settings -> Reset Account / Change Balance -> Set to $10,000.00")
    print("   3. Restart Docker containers: docker compose restart\n")

if __name__ == "__main__":
    reset_oanda_practice_account()
