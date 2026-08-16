import unittest
from unittest.mock import patch, MagicMock
from live_execution_engine.broker.broker_authoritative_sync import BrokerAuthoritativeReconciler

class TestBrokerChaos(unittest.TestCase):
    def setUp(self):
        self.mock_order_manager = MagicMock()
        self.reconciler = BrokerAuthoritativeReconciler(order_manager=self.mock_order_manager, config=None)

    def test_duplicate_fill_idempotency(self):
        # Scenario: Broker sends same fill twice (or local engine receives duplicate webhook)
        local_positions = [{"position_id": "POS_123", "oanda_trade_id": "123"}]
        broker_trades = [
            {"id": "123", "price": "1.1500", "initialUnits": "50000"}
        ]
        
        res = self.reconciler.reconcile_state(
            local_pending=[], local_positions=local_positions, 
            broker_orders=[], broker_trades=broker_trades, broker_mode=True
        )
        
        # Should deduplicate and not create a new newly_filled event
        self.assertEqual(len(res["newly_filled"]), 0)
        self.assertEqual(len(res["reconciled_positions"]), 1)

    def test_partial_close_sync(self):
        # Scenario: OANDA trade size drops from 50k to 25k locally due to partial exit
        local_positions = [{"position_id": "POS_124", "oanda_trade_id": "124", "lots": 0.50}]
        # Broker confirms trade still open
        broker_trades = [
            {"id": "124", "price": "1.1500", "initialUnits": "50000", "currentUnits": "25000"}
        ]
        
        res = self.reconciler.reconcile_state(
            local_pending=[], local_positions=local_positions, 
            broker_orders=[], broker_trades=broker_trades, broker_mode=True
        )
        
        # Position remains open, no crash
        self.assertEqual(len(res["closed_positions"]), 0)
        self.assertEqual(len(res["reconciled_positions"]), 1)
        self.assertFalse(res["divergence_frozen"])

    def test_orphan_trade_divergence_freeze(self):
        # Scenario: Engine crashed and reloaded, missing trade ID from OANDA API
        local_positions = [{"position_id": "POS_ORPHAN", "oanda_trade_id": ""}]
        
        res = self.reconciler.reconcile_state(
            local_pending=[], local_positions=local_positions, 
            broker_orders=[], broker_trades=[], broker_mode=True
        )
        
        # Should trigger critical state divergence freeze
        self.assertTrue(res["divergence_frozen"])
        self.assertIn("CRITICAL_STATE_DIVERGENCE", res["alerts"])

    def test_broker_fifo_cancellation(self):
        # Scenario: OANDA cancels a limit order due to FIFO constraint
        local_pending = [{"order_id": "ORD_001", "oanda_transaction_id": "500", "status": "PENDING"}]
        # Broker list is empty (order deleted)
        
        res = self.reconciler.reconcile_state(
            local_pending=local_pending, local_positions=[], 
            broker_orders=[], broker_trades=[], broker_mode=True
        )
        
        # Should mark local pending as cancelled
        self.assertEqual(res["reconciled_pending"][0]["status"], "CANCELLED")
        self.assertIn("BROKER_CANCELLED_ORD_001", res["alerts"])

if __name__ == "__main__":
    unittest.main()
