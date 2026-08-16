import os
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.execution.order_manager import OrderManager
from live_execution_engine.execution.oanda_execution_engine import OANDAExecutionEngine
from live_execution_engine.events import EventBus, Event, EventType
from live_execution_engine.clock import RealClock

class TestE2ECrashRecovery(unittest.TestCase):
    def setUp(self):
        # Setup clean test environment
        self.config = LiveTradingConfig()
        self.config.log_dir = "tests/test_logs"
        os.makedirs(self.config.log_dir, exist_ok=True)
        
        self.state_file = os.path.join(self.config.log_dir, "paper_positions_state.json")
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
            
        self.event_bus = EventBus()
        self.clock = RealClock()

    @patch("urllib.request.urlopen")
    def test_submit_crash_recover_sequence(self, mock_urlopen):
        # -------------------------------------------------------------
        # Phase 1: Submit -> OANDA accepts -> Process Crashes
        # -------------------------------------------------------------
        om_1 = OrderManager(config=self.config, clock=self.clock)
        engine_1 = OANDAExecutionEngine(config=self.config, order_manager=om_1, clock=self.clock, event_bus=self.event_bus)
        
        # Inject fake OANDA credentials to bypass guards
        engine_1.api_key = "FAKE_KEY"
        engine_1.account_id = "FAKE_ACC"

        # Mock OANDA Order Creation Response
        mock_res_create = MagicMock()
        mock_res_create.read.return_value = json.dumps({
            "orderCreateTransaction": {"id": "5001"}
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_res_create

        # Submit Order
        signal_time = datetime.now(timezone.utc)
        engine_1.place_order(
            symbol="EURUSD", signal_type="BUY", signal_time=signal_time,
            ask=1.1500, bid=1.1499, atr=0.0010, risk_pct=0.75
        )

        # Verify state saved locally before crash
        self.assertEqual(len(om_1.pending_orders), 1)
        self.assertEqual(om_1.pending_orders[0]["oanda_transaction_id"], "5001")
        
        # SIMULATE CRASH: Destroy instances completely
        del engine_1
        del om_1
        
        # -------------------------------------------------------------
        # Phase 2: Restart -> Reconcile OANDA -> Reconstruct State
        # -------------------------------------------------------------
        
        # New instances (Restarted process)
        om_2 = OrderManager(config=self.config, clock=self.clock)
        engine_2 = OANDAExecutionEngine(config=self.config, order_manager=om_2, clock=self.clock, event_bus=self.event_bus)
        engine_2.api_key = "FAKE_KEY"
        engine_2.account_id = "FAKE_ACC"

        # Verify local state reloaded from JSON disk successfully
        self.assertEqual(len(om_2.pending_orders), 1)
        self.assertEqual(om_2.pending_orders[0]["oanda_transaction_id"], "5001")
        self.assertEqual(len(om_2.open_positions), 0)

        # Mock OANDA REST API responses during Reconciler Sync:
        # 1. Pending orders payload (Empty: order was filled!)
        mock_res_pending = MagicMock()
        mock_res_pending.read.return_value = json.dumps({"orders": []}).encode("utf-8")
        
        # 2. Open trades payload (Contains our filled trade!)
        mock_res_trades = MagicMock()
        mock_res_trades.read.return_value = json.dumps({
            "trades": [
                {
                    "id": "5001", # Trade ID matches the order create transaction ID
                    "price": "1.1498",
                    "initialUnits": "20000",
                    "currentUnits": "20000"
                }
            ]
        }).encode("utf-8")
        
        # Assign side effects to handle the two consecutive API calls in sync_broker_events
        mock_urlopen.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=mock_res_pending)),
            MagicMock(__enter__=MagicMock(return_value=mock_res_trades))
        ]

        # Track Events Emitted
        emitted_events = []
        def track_events(event: Event):
            emitted_events.append(event)
        self.event_bus.subscribe(EventType.ORDER_FILLED, track_events)
        
        # Execute Reconciliation (Happens on first tick after restart)
        engine_2.sync_broker_events()

        # -------------------------------------------------------------
        # Phase 3: Assert 0 Duplicates, 0 Phantoms, 0 Divergence
        # -------------------------------------------------------------
        
        # The reconciler should have created exactly 1 position and removed the pending order
        self.assertEqual(len(om_2.open_positions), 1, "Failed: State reconstructed incorrect number of positions.")
        self.assertEqual(len(om_2.pending_orders), 0, "Failed: Pending order was not cleared after broker fill.")
        
        # Ensure it's correctly linked to OANDA trade
        pos = om_2.open_positions[0]
        self.assertEqual(pos["oanda_trade_id"], "5001")
        self.assertEqual(pos["position_id"], "POS_5001")
        self.assertEqual(pos["type"], "BUY")
        self.assertEqual(pos["entry_price"], 1.1498)
        
        # Ensure exactly 1 ORDER_FILLED event was emitted for Telegram/Logging
        self.assertEqual(len(emitted_events), 1, "Failed: Emitted duplicate or 0 ORDER_FILLED events.")
        
        # Ensure no divergence alerts triggered
        self.assertFalse(engine_2.reconciler.divergence_frozen, "Failed: Engine panicked with silent divergence!")
        
        print("\n✅ E2E Crash Recovery Test Passed Successfully:")
        print("  - 0 Duplicate Orders")
        print("  - 0 Phantom Fills")
        print("  - 0 Orphan Positions")
        print("  - 0 Silent State Divergence")
        print("  - 100% Broker-Authoritative State Reconstructed on Reboot")

if __name__ == "__main__":
    unittest.main()
