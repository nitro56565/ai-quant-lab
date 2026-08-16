"""
Unit Test Suite for TelegramNotifier & Notification Ledger Audit Engine.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import time
import tempfile
import sqlite3
from datetime import datetime, timezone

from live_execution_engine.events.event_bus import EventBus, Event, EventType
from live_execution_engine.persistence.database import DatabaseManager
from live_execution_engine.monitoring.telegram_notifier import TelegramNotifier

class TestTelegramNotifier(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_ledger.db")
        self.db = DatabaseManager(self.db_path)
        self.event_bus = EventBus()
        
        os.environ["TELEGRAM_BOT_TOKEN"] = "123456789:TEST_BOT_TOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "-100123456789"
        os.environ["TELEGRAM_ALERTS_ENABLED"] = "true"

    def tearDown(self):
        if hasattr(self, "notifier"):
            self.notifier.stop()

    def test_queue_and_worker_dispatch(self):
        self.notifier = TelegramNotifier(event_bus=self.event_bus, db=self.db)
        
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99881}}
            mock_post.return_value = mock_resp

            self.notifier.enqueue_message("TEST_EVENT", "<b>Test Payload</b>", {"trade_id": "TRD_001"})
            
            # Wait for worker queue to process
            self.notifier.queue.join()

            mock_post.assert_called_once()
            call_args = mock_post.call_args[1]
            self.assertEqual(call_args["json"]["parse_mode"], "HTML")
            self.assertIn("Test Payload", call_args["json"]["text"])

            # Verify SQLite audit logging
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT status, telegram_message_id, event_type FROM notifications_ledger")
            row = cursor.fetchone()
            conn.close()

            self.assertIsNotNone(row)
            self.assertEqual(row[0], "DELIVERED")
            self.assertEqual(row[1], "99881")
            self.assertEqual(row[2], "TEST_EVENT")

    def test_html_escaping(self):
        self.notifier = TelegramNotifier(event_bus=self.event_bus, db=self.db)
        
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99882}}
            mock_post.return_value = mock_resp

            # Trigger Risk Veto with raw HTML characters '<script>alert("hack")</script> & risk'
            self.event_bus.publish(Event(EventType.RISK_VETOED, {
                "reason": '<script>alert("hack")</script> & risk',
                "symbol": "EURUSD"
            }))

            self.notifier.queue.join()
            
            call_args = mock_post.call_args[1]
            escaped_text = call_args["json"]["text"]
            
            self.assertNotIn("<script>", escaped_text)
            self.assertIn("&lt;script&gt;", escaped_text)
            self.assertIn("&amp; risk", escaped_text)

    def test_exponential_backoff_retry(self):
        self.notifier = TelegramNotifier(event_bus=self.event_bus, db=self.db)

        with patch("requests.post") as mock_post, patch("time.sleep") as mock_sleep:
            # Simulate 2 failures followed by 1 success
            resp_fail = MagicMock()
            resp_fail.status_code = 500
            resp_fail.text = "Internal Server Error"

            resp_ok = MagicMock()
            resp_ok.status_code = 200
            resp_ok.json.return_value = {"ok": True, "result": {"message_id": 99883}}

            mock_post.side_effect = [resp_fail, resp_fail, resp_ok]

            self.notifier.enqueue_message("RETRY_EVENT", "Retry Test Payload")
            self.notifier.queue.join()

            self.assertEqual(mock_post.call_count, 3)
            # Verify sleep delays were called (1.0s, 5.0s)
            mock_sleep.assert_any_call(1.0)
            mock_sleep.assert_any_call(5.0)

if __name__ == "__main__":
    unittest.main()
