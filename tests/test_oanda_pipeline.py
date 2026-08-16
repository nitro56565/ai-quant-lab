import os
import sys
import unittest
import tempfile
import asyncio
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from live_execution_engine.data.tick_logger import PartitionedTickParquetLogger
from live_execution_engine.data.oanda_client import OANDAAsyncStreamClient
from live_execution_engine.data.hourly_aggregator import HourlyCandleAggregator
from live_execution_engine.data.replay_provider import ReplayProvider
from live_execution_engine.monitoring.health import SystemHealthTree, ComponentHealthStatus
from live_execution_engine.persistence.database import DatabaseManager

class TestOANDAPipeline(unittest.TestCase):
    def test_partitioned_tick_parquet_logger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = PartitionedTickParquetLogger(base_dir=tmpdir, chunk_size=5)
            for i in range(12):
                logger.log_tick({
                    "symbol": "EURUSD",
                    "timestamp": "2026-08-06 10:00:00 UTC",
                    "bid": 1.0850 + (i * 0.0001),
                    "ask": 1.0852 + (i * 0.0001)
                })
            logger.flush()

            day_dir = os.path.join(tmpdir, "EURUSD", "2026-08-06")
            parts = [f for f in os.listdir(day_dir) if f.startswith("part_") and f.endswith(".parquet")]
            self.assertGreaterEqual(len(parts), 2, "Expected at least 2 partition files created.")
            
            # Read first partition
            df = pd.read_parquet(os.path.join(day_dir, "part_0001.parquet"))
            self.assertEqual(len(df), 5)

    def test_oanda_client_fingerprinting(self):
        client = OANDAAsyncStreamClient(api_key="test", account_id="test")
        fp1 = client._generate_fingerprint("2026-08-06 10:00:00 UTC", 1.0850, 1.0852, 1.0, 1.0)
        fp2 = client._generate_fingerprint("2026-08-06 10:00:00 UTC", 1.0850, 1.0852, 1.0, 1.0)
        fp3 = client._generate_fingerprint("2026-08-06 10:00:01 UTC", 1.0851, 1.0853, 1.0, 1.0)

        self.assertEqual(fp1, fp2, "Identical ticks must yield identical fingerprints.")
        self.assertNotEqual(fp1, fp3, "Different ticks must yield different fingerprints.")

    def test_dual_hourly_candle_aggregator(self):
        agg = HourlyCandleAggregator(symbol="EURUSD", seal_grace_ms=0)
        
        tick1 = {"symbol": "EURUSD", "timestamp": "2026-08-06 10:05:00 UTC", "bid": 1.0850, "ask": 1.0852, "mid": 1.0851, "spread": 0.0002}
        tick2 = {"symbol": "EURUSD", "timestamp": "2026-08-06 10:55:00 UTC", "bid": 1.0860, "ask": 1.0862, "mid": 1.0861, "spread": 0.0002}
        tick3 = {"symbol": "EURUSD", "timestamp": "2026-08-06 11:01:00 UTC", "bid": 1.0855, "ask": 1.0857, "mid": 1.0856, "spread": 0.0002}

        c1 = agg.process_tick_sync(tick1)
        self.assertIsNone(c1, "First tick should not seal candle.")

        c2 = agg.process_tick_sync(tick2)
        self.assertIsNone(c2, "Second tick in same hour should not seal candle.")

        sealed_candle = agg.process_tick_sync(tick3)
        self.assertIsNotNone(sealed_candle, "Hour transition should seal the 10:00 candle.")

        self.assertEqual(sealed_candle["tick_volume"], 2)
        self.assertIn("bid_open", sealed_candle)
        self.assertIn("ask_open", sealed_candle)
        self.assertIn("open", sealed_candle)
        self.assertEqual(sealed_candle["bid_open"], 1.0850)
        self.assertEqual(sealed_candle["bid_high"], 1.0860)

    def test_system_health_tree(self):
        health = SystemHealthTree()
        summary = health.get_health_summary()
        self.assertEqual(summary["overall_system_status"], ComponentHealthStatus.HEALTHY)
        self.assertEqual(len(summary["subsystems"]), 8)

        health.update_component("model", ComponentHealthStatus.WARNING, "High latency")
        summary2 = health.get_health_summary()
        self.assertEqual(summary2["overall_system_status"], ComponentHealthStatus.WARNING)

    def test_database_ledgers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_ledgers.db")
            db = DatabaseManager(db_path)

            # Test Candle Ledger
            c_id = db.save_candle({
                "timestamp": "2026-08-06 10:00:00 UTC",
                "symbol": "EURUSD",
                "open": 1.0850, "high": 1.0860, "low": 1.0845, "close": 1.0855,
                "bid_open": 1.0849, "bid_high": 1.0859, "bid_low": 1.0844, "bid_close": 1.0854,
                "ask_open": 1.0851, "ask_high": 1.0861, "ask_low": 1.0846, "ask_close": 1.0856,
                "spread_min": 0.00012, "spread_max": 0.00020, "tick_volume": 450
            })
            self.assertTrue(c_id.startswith("CND_EURUSD"))

            # Test Decision Trace Ledger
            t_id = db.save_decision_trace({
                "timestamp": "2026-08-06 10:00:00 UTC",
                "symbol": "EURUSD",
                "prob_long": 0.65, "prob_short": 0.15,
                "ev_long": 12.5, "ev_short": -5.0,
                "outcome": "EXECUTE",
                "reason": "Probability Long 0.65 >= 0.34 & EV +12.5p > 0"
            })
            self.assertTrue(len(t_id) > 0)

            # Test Event Sourcing Ledger
            e_id = db.save_event_sourcing_record("BAR_CLOSED", {"symbol": "EURUSD", "step": 1})
            self.assertTrue(len(e_id) > 0)

    def test_replay_provider(self):
        replay = ReplayProvider(start_date="2024-01-01", end_date="2024-01-02", fast_mode=True)
        ticks_received = []
        replay.start(symbol="EURUSD", tick_callback=lambda t: ticks_received.append(t))

        self.assertGreater(len(ticks_received), 0, "ReplayProvider should stream historical steps.")
        status = replay.get_status()
        self.assertEqual(status["provider"], "ReplayProvider")

if __name__ == "__main__":
    unittest.main()
