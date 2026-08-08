#!/usr/bin/env python3
"""
OANDA v20 Live Broker Gateway End-to-End Test Script — AI Quant Lab v5.0.
Triggers a controlled sample limit order through OANDALiveBrokerGateway to verify direct integration
with OANDA Practice REST API (https://api-fxpractice.oanda.com).
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
from datetime import datetime, timezone
from live_trading_engine.config import LiveTradingConfig
from live_trading_engine.clock import RealClock
from live_trading_engine.execution.order_manager import OrderManager
from live_trading_engine.broker.oanda_gateway import OANDALiveBrokerGateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - INFO - [%(message)s]")
logger = logging.getLogger("OANDAGatewayTest")

def main():
    print("=================================================================================")
    print("  🧪 TESTING OANDA LIVE BROKER GATEWAY REST INTEGRATION")
    print("  Account ID: 101-001-40013710-001 | Environment: PRACTICE")
    print("=================================================================================\n")

    config = LiveTradingConfig()
    clock = RealClock()
    order_manager = OrderManager(config=config, clock=clock)
    gateway = OANDALiveBrokerGateway(config=config, order_manager=order_manager, clock=clock)

    # 1. Fetch live OANDA account summary
    logger.info("📡 Step 1: Querying live OANDA Practice Account summary...")
    summary = gateway.get_account_summary()
    print("\n--- OANDA ACCOUNT SUMMARY ---")
    print(f"  • Source:               {summary.get('source')}")
    print(f"  • Account ID:           {summary.get('account_id')}")
    print(f"  • Currency:             {summary.get('currency')}")
    print(f"  • Account Balance:      ${summary.get('balance'):,.2f}")
    print(f"  • Account NAV / Equity: ${summary.get('equity'):,.2f}")
    print(f"  • Open Positions:       {summary.get('open_positions_count')}")
    print(f"  • Pending Orders:       {summary.get('pending_orders_count')}")
    print("-----------------------------\n")

    # 2. Trigger sample trade through OANDALiveBrokerGateway
    sample_time = datetime.now(timezone.utc)
    ask_price = 1.15588
    bid_price = 1.15571
    atr_val = 0.0012

    logger.info(f"⚡ Step 2: Triggering sample BUY EURUSD limit order @ {ask_price - (atr_val * 0.25):.5f}...")
    order = gateway.place_order(
        symbol="EURUSD",
        signal_type="BUY",
        signal_time=sample_time,
        ask=ask_price,
        bid=bid_price,
        atr=atr_val,
        risk_pct=0.5
    )

    print("\n--- SAMPLE ORDER SUBMISSION RECEIPT ---")
    print(f"  • Local Order ID:         {order.get('order_id')}")
    print(f"  • Symbol:                 {order.get('symbol')}")
    print(f"  • Signal Type:            {order.get('signal_type')}")
    print(f"  • Limit Price:            {order.get('limit_price')}")
    print(f"  • Stop Loss:              {order.get('stop_loss')}")
    print(f"  • Take Profit:            {order.get('take_profit')}")
    print(f"  • OANDA Transaction ID:   {order.get('oanda_transaction_id', 'N/A (Check Logs/Response)')}")
    print("---------------------------------------\n")

    # 3. Query updated summary
    logger.info("📡 Step 3: Fetching updated OANDA account status post-submission...")
    summary_post = gateway.get_account_summary()
    print(f"  • OANDA Pending Orders Count: {summary_post.get('pending_orders_count')}")
    print(f"  • OANDA Balance: ${summary_post.get('balance'):,.2f}")
    print("\n=================================================================================")
    print("  🏆 OANDA LIVE GATEWAY TEST COMPLETED!")
    print("=================================================================================\n")

if __name__ == "__main__":
    main()
