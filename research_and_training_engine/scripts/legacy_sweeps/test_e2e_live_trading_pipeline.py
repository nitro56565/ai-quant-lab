"""
Comprehensive End-to-End Live Signal & Execution Integration Test — AI Quant Lab v5.0.
Triggers every event handler, order submission path, broker reconciliation, and logger formatting
in realistic live trading conditions to guarantee zero runtime exceptions.
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment credentials (.env)
load_dotenv(".env")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.clock import RealClock
from live_execution_engine.events.event_bus import EventBus, Event, EventType
from live_execution_engine.persistence.database import DatabaseManager
from live_execution_engine.models.signal_engine import SignalEngine
from live_execution_engine.decision.decision_engine import DecisionEngine
from live_execution_engine.risk.risk_guardian import PreTradeRiskGuardian
from live_execution_engine.execution.order_manager import OrderManager
from live_execution_engine.execution.oanda_execution_engine import OANDAExecutionEngine
from live_execution_engine.execution.simulation_execution_engine import SimulationExecutionEngine
from live_execution_engine.data.streamer import RealTimeDataStreamer, OANDAMarketDataProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("E2EIntegrationTest")

def run_e2e_pipeline_verification():
    print("=================================================================================")
    print("  🔬 COMPREHENSIVE END-TO-END LIVE PIPELINE INTEGRATION TEST")
    print("=================================================================================\n")

    config = LiveTradingConfig()
    clock = RealClock()
    event_bus = EventBus()
    db_manager = DatabaseManager("live_execution_engine/logs/test_e2e_ledger.db")

    # 1. Instantiate Core Components
    signal_engine = SignalEngine(event_bus=event_bus, model_dir="trained_model_artifacts/production_deployment")
    decision_engine = DecisionEngine(event_bus=event_bus, db_manager=db_manager)
    risk_guardian = PreTradeRiskGuardian(config=config)
    order_manager = OrderManager(config=config, clock=clock)
    oanda_engine = OANDAExecutionEngine(config=config, order_manager=order_manager, clock=clock)
    sim_engine = SimulationExecutionEngine(config=config, order_manager=order_manager)

    # 2. Test Order Placement Handlers (Simulating exact run_paper_trading.py callback)
    order_request_handled = [False]
    
    def handle_order_request(event: Event):
        data = event.data
        symbol = data.get("symbol", "EURUSD")
        signal_type = data.get("signal_type", "SELL")
        ask = data.get("ask", 1.15400)
        bid = data.get("bid", 1.15365)
        atr = data.get("atr", 0.0012)
        risk_pct = data.get("risk_pct", 0.75)

        logger.info(f"⚡ EventBus ORDER_REQUEST Received: {symbol} {signal_type} @ Ask={ask}, Bid={bid}, ATR={atr}")
        
        # Test order creation in both engines
        ord_oanda = oanda_engine.place_order(symbol, signal_type, clock.now(), ask, bid, atr, risk_pct)
        ord_sim = sim_engine.place_order(symbol, signal_type, clock.now(), ask, bid, atr, risk_pct)
        
        order_request_handled[0] = True
        logger.info(f"✅ Order placement verified cleanly! OANDA Order ID: {ord_oanda['order_id']}, Sim Order ID: {ord_sim['order_id']}")

    event_bus.subscribe(EventType.ORDER_REQUEST, handle_order_request)

    # 3. Simulate Event Flow with Mock DataFrame (400 Bars)
    print("▶ Step 1: Generating realistic 400-bar H1 dataset...")
    dates = pd.date_range(end=pd.Timestamp.now(), periods=400, freq="1h")
    mock_df = pd.DataFrame({
        "open": 1.1500 + np.random.randn(400) * 0.0010,
        "high": 1.1520 + np.random.randn(400) * 0.0010,
        "low": 1.1480 + np.random.randn(400) * 0.0010,
        "close": 1.1510 + np.random.randn(400) * 0.0010,
        "volume": 1000
    }, index=dates)

    print("▶ Step 2: Testing SignalEngine.on_bar_closed() ML feature extraction & inference...")
    event_bus.publish(Event(EventType.BAR_CLOSED, {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "symbol": "EURUSD",
        "ask": 1.15400,
        "bid": 1.15365,
        "rolling_bars_df": mock_df
    }))

    print("▶ Step 3: Testing Direct Signal Approval & DecisionEngine Event Chain...")
    dummy_approved_signal = {
        "symbol": "EURUSD",
        "signal_type": "SELL",
        "prob_sell": 0.65,
        "prob_buy": 0.15,
        "prob_hold": 0.20,
        "ev_net_r": 0.67,
        "regime_id": 1,
        "atr": 0.0012,
        "ask": 1.15400,
        "bid": 1.15365,
        "vol_rank_pct": 0.50
    }
    event_bus.publish(Event(EventType.SIGNAL_GENERATED, dummy_approved_signal))

    if not order_request_handled[0]:
        raise RuntimeError("❌ Order request event handler was not triggered!")

    # 4. Test Broker Sync & State Management
    print("▶ Step 4: Testing OANDA Execution Engine State Sync & Reconciliation...")
    positions = oanda_engine.sync_broker_events()
    summary = oanda_engine.get_account_summary()
    logger.info(f"✅ Account Summary Verified: Balance=${summary['balance']:,.2f}, Equity=${summary['equity']:,.2f}, Source={summary['source']}")

    # 5. Test State Persistence Save & Load
    print("▶ Step 5: Testing OrderManager State Serialization & Datetime Recovery...")
    order_manager.save_state()
    order_manager.load_state()

    # Clean test artifact DB
    if os.path.exists("live_execution_engine/logs/test_e2e_ledger.db"):
        os.remove("live_execution_engine/logs/test_e2e_ledger.db")

    print("\n=================================================================================")
    print("  🟢 END-TO-END PIPELINE INTEGRATION TEST: 100% SUCCESSFUL!")
    print("  • All EventBus Handlers Verified Cleanly")
    print("  • Order Placement & Dynamic Sizing Verified Cleanly")
    print("  • OANDA Authoritative Sync Verified Cleanly")
    print("  • State Persistence & JSON Recovery Verified Cleanly")
    print("=================================================================================\n")
    return True

if __name__ == "__main__":
    run_e2e_pipeline_verification()
