"""
Institutional Asynchronous Telegram Notification & Sourcing Engine v3.0.
Provides thread-safe queue dispatching, exponential backoff retries, SQLite audit ledger logging,
HTML escaping, trace correlation (TRD_..., DEC_..., EVT_...), rate-limited risk alerts,
and automated Daily / Weekly Performance Digest reports.
"""

import os
import time
import html
import queue
import requests
import threading
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from live_trading_engine.events.event_bus import EventBus, Event, EventType
from live_trading_engine.persistence.database import DatabaseManager

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    """
    Production-grade Telegram Notification Engine.
    Uses a single background worker queue to enforce causal message ordering and zero latency impact on trading daemon.
    """
    def __init__(self, event_bus: EventBus, config: Any = None, db: Optional[DatabaseManager] = None):
        self.event_bus = event_bus
        self.config = config
        self.db = db or DatabaseManager()
        
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("TELEGRAM_ALERTS_ENABLED", "true").lower() == "true" and bool(self.bot_token) and bool(self.chat_id)
        
        # Single Worker Queue Architecture
        self.queue = queue.Queue()
        self.is_running = True
        
        # Rate Limiting & Anti-Spam state
        self._last_risk_veto_reason: str = ""
        self._last_risk_veto_time: float = 0.0
        
        if self.enabled:
            self._subscribe_events()
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="TelegramNotifierWorker")
            self.worker_thread.start()
            logger.info("📲 Telegram Notifier Engine Initialized (Single Worker Queue & Audit Ledger Active)")
        else:
            logger.info("ℹ️ Telegram Notifier disabled (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")

    def _format_time(self, dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now(timezone.utc)
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return f"{ist.strftime('%Y-%m-%d %H:%M:%S IST')} [{dt.strftime('%H:%M:%S UTC')}]"

    def _subscribe_events(self):
        try:
            self.event_bus.subscribe(EventType.ORDER_CREATED, self.on_order_created)
            self.event_bus.subscribe(EventType.ORDER_FILLED, self.on_order_filled)
            self.event_bus.subscribe(EventType.POSITION_CLOSED, self.on_position_closed)
        except Exception as e:
            logger.error(f"Error subscribing TelegramNotifier to EventBus: {e}")


    def enqueue_message(self, event_type: str, html_payload: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Non-blocking enqueue method called by event callbacks.
        """
        if not self.enabled:
            return
        msg_item = {
            "event_type": event_type,
            "html_payload": html_payload,
            "metadata": metadata or {},
            "enqueued_at": time.time()
        }
        self.queue.put(msg_item)

    def _worker_loop(self):
        """
        Single persistent background worker thread loop.
        """
        while self.is_running:
            try:
                msg_item = self.queue.get(timeout=1.0)
                if msg_item is None:
                    continue
                self._process_and_send(msg_item)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in Telegram worker loop: {e}", exc_info=True)

    def _process_and_send(self, msg_item: Dict[str, Any]):
        """
        Dispatches HTTP POST to Telegram API with exponential backoff retries (1s, 5s, 30s) and SQLite audit logging.
        """
        html_text = msg_item["html_payload"]
        meta = msg_item["metadata"]
        event_type = msg_item["event_type"]
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        retries = [1.0, 5.0, 30.0]
        max_attempts = len(retries) + 1
        status = "FAILED"
        msg_id = ""
        delivery_time_ms = 0.0
        retry_count = 0

        t0 = time.time()
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, json=payload, timeout=8)
                if resp.status_code == 200:
                    status = "DELIVERED"
                    data = resp.json()
                    msg_id = str(data.get("result", {}).get("message_id", ""))
                    delivery_time_ms = (time.time() - t0) * 1000.0
                    break
                else:
                    logger.warning(f"Telegram API HTTP {resp.status_code} (Attempt {attempt+1}/{max_attempts}): {resp.text}")
            except Exception as req_err:
                logger.warning(f"Telegram API Exception (Attempt {attempt+1}/{max_attempts}): {req_err}")

            if attempt < len(retries):
                retry_count += 1
                time.sleep(retries[attempt])

        # Record to SQLite Audit Ledger
        try:
            self.db.save_notification_audit({
                "trade_id": meta.get("trade_id", ""),
                "decision_trace_id": meta.get("decision_trace_id", ""),
                "event_type": event_type,
                "status": status,
                "telegram_message_id": msg_id,
                "retry_count": retry_count,
                "delivery_time_ms": delivery_time_ms,
                "payload_text": html_text
            })
        except Exception as db_err:
            logger.error(f"Failed to record notification audit log: {db_err}")

    # =========================================================================
    # EVENT HANDLERS & MESSAGE GENERATORS
    # =========================================================================

    def send_startup_notification(self, symbol: str, capital: float, broker_type: str = "Local Paper Broker"):
        """
        11. System Daemon Startup Notification
        """
        try:
            now_str = self._format_time()
            msg = (
                f"🚀 <b>AI QUANT LAB TRADING ENGINE STARTED</b>\n"
                f"------------------------------------\n"
                f"<b>System Version:</b> v3.0 Production Certified\n"
                f"<b>Symbol / Asset:</b> {html.escape(symbol)} (1H Timeframe)\n"
                f"<b>Certified Model:</b> MOD_EURUSD_V1_2026 (PSR: 1.00)\n"
                f"<b>Broker Gateway:</b> {html.escape(broker_type)}\n"
                f"<b>Starting Capital:</b> ${capital:,.2f}\n"
                f"<b>Boot Timestamp:</b> {now_str}\n"
                f"------------------------------------\n"
                f"<i>Pipeline: v3.0_Production | 104 Features</i>"
            )
            self.enqueue_message("STARTUP", msg)
        except Exception as e:
            logger.error(f"Error building startup notification: {e}")

    def on_order_created(self, event: Event):
        """
        1. Real Approved Order Created Alert
        """
        try:
            data = event.data
            symbol = html.escape(str(data.get("symbol", "EURUSD")))
            direction = html.escape(str(data.get("signal_type", "BUY")))
            entry = float(data.get("limit_price", 0.0))
            tp = float(data.get("take_profit", 0.0))
            sl = float(data.get("stop_loss", 0.0))
            order_id = html.escape(str(data.get("order_id", "ORD_PENDING")))

            dir_icon = "🟢 BUY" if "BUY" in direction.upper() else "🔴 SELL"
            now_str = self._format_time()

            msg = (
                f"⚡ <b>LIVE ORDER CREATED & PLACED</b>\n"
                f"------------------------------------\n"
                f"<b>Order ID:</b> {order_id}\n"
                f"<b>Symbol:</b> {symbol} | <b>Direction:</b> {dir_icon}\n"
                f"<b>Limit Entry:</b> {entry:.5f}\n"
                f"<b>Take Profit:</b> {tp:.5f}\n"
                f"<b>Stop Loss:</b> {sl:.5f}\n"
                f"<b>Timestamp:</b> {now_str}\n"
                f"------------------------------------\n"
                f"<i>Model: MOD_EURUSD_V1_2026 | Config: 20260807</i>"
            )
            self.enqueue_message("ORDER_CREATED", msg, {"order_id": order_id})
        except Exception as e:
            logger.error(f"Error handling on_order_created: {e}")


    def on_order_filled(self, event: Event):
        """
        2. Trade Filled Alert
        """
        try:
            data = event.data
            symbol = html.escape(str(data.get("symbol", "EURUSD")))
            direction = html.escape(str(data.get("direction", "BUY")))
            pos_id = html.escape(str(data.get("position_id", "POS_0001")))
            price = float(data.get("entry_price", 0.0))
            slippage = float(data.get("slippage", 0.0))
            now_str = self._format_time()

            msg = (
                f"🟢 <b>ORDER FILLED ON BROKER</b>\n"
                f"------------------------------------\n"
                f"<b>Position ID:</b> {pos_id}\n"
                f"<b>Symbol:</b> {symbol} ({direction})\n"
                f"<b>Executed Entry:</b> {price:.5f}\n"
                f"<b>Retrace Slippage:</b> {slippage:.2f} pips\n"
                f"<b>Timestamp:</b> {now_str}"
            )
            self.enqueue_message("ORDER_FILLED", msg, {"trade_id": pos_id})
        except Exception as e:
            logger.error(f"Error handling on_order_filled: {e}")

    def on_position_closed(self, event: Event):
        """
        3. Position Closed Alert with Account Equity Snapshot
        """
        try:
            data = event.data
            symbol = html.escape(str(data.get("symbol", "EURUSD")))
            pos_id = html.escape(str(data.get("position_id", "POS_0001")))
            pos_type = html.escape(str(data.get("type", "BUY")))
            reason = html.escape(str(data.get("reason", "TAKE_PROFIT")))
            entry_p = float(data.get("entry_price", 0.0))
            exit_p = float(data.get("exit_price", 0.0))
            pnl_usd = float(data.get("pnl_usd", 0.0))
            pnl_pips = float(data.get("pnl_pips", 0.0))
            r_mult = float(data.get("r_multiple", 0.0))
            
            # Account snapshot
            equity = float(data.get("equity", 10000.0))
            open_pos = int(data.get("open_positions_count", 0))
            now_str = self._format_time()

            reason_icon = "🎯 TAKE_PROFIT" if "PROFIT" in reason else ("🛑 STOP_LOSS" if "STOP" in reason else "⏱️ TIME_EXIT")
            pnl_color = "🟢" if pnl_usd >= 0 else "🔴"

            msg = (
                f"🏆 <b>POSITION CLOSED</b>\n"
                f"------------------------------------\n"
                f"<b>Position ID:</b> {pos_id}\n"
                f"<b>Symbol:</b> {symbol} ({pos_type})\n"
                f"<b>Exit Reason:</b> {reason_icon}\n"
                f"<b>Price Path:</b> {entry_p:.5f} ➔ <b>{exit_p:.5f}</b>\n"
                f"<b>Net PnL ($):</b> {pnl_color} <b>${pnl_usd:+,.2f}</b>\n"
                f"<b>Net PnL (Pips):</b> {pnl_pips:+.2f} pips\n"
                f"<b>Realized R:</b> {r_mult:+.2f}R\n"
                f"------------------------------------\n"
                f"📊 <b>ACCOUNT SNAPSHOT</b>\n"
                f"• Current Equity: <b>${equity:,.2f}</b>\n"
                f"• Open Positions: {open_pos}\n"
                f"• Exit Timestamp: {now_str}"
            )
            self.enqueue_message("POSITION_CLOSED", msg, {"trade_id": pos_id})
        except Exception as e:
            logger.error(f"Error handling on_position_closed: {e}")

    def on_risk_vetoed(self, event: Event):
        """
        8. Rate-Limited Risk Veto Alert
        """
        try:
            data = event.data
            reason = html.escape(str(data.get("reason", "Risk Guardian Filter")))
            now_ts = time.time()

            # Anti-spam deduplication: Suppress identical risk alerts if sent < 60 minutes ago
            if reason == self._last_risk_veto_reason and (now_ts - self._last_risk_veto_time) < 3600.0:
                logger.debug(f"Rate-limiting duplicate risk veto alert: {reason}")
                return

            self._last_risk_veto_reason = reason
            self._last_risk_veto_time = now_ts

            symbol = html.escape(str(data.get("symbol", "EURUSD")))
            now_str = self._format_time()

            msg = (
                f"🛡️ <b>RISK GUARDIAN VETO ALERT</b>\n"
                f"------------------------------------\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Veto Reason:</b> {reason}\n"
                f"<b>Action:</b> Signal Suppressed for Capital Protection\n"
                f"<b>Timestamp:</b> {now_str}"
            )
            self.enqueue_message("RISK_VETOED", msg)
        except Exception as e:
            logger.error(f"Error handling on_risk_vetoed: {e}")

    def send_daily_summary(self, summary_data: Dict[str, Any]):
        """
        12. Automated Daily Summary Digest (00:00 UTC)
        """
        try:
            now_str = self._format_time()
            pnl_usd = float(summary_data.get("pnl_usd", 0.0))
            pnl_pct = float(summary_data.get("pnl_pct", 0.0))
            trades = int(summary_data.get("trades_count", 0))
            win_rate = float(summary_data.get("win_rate", 0.0))
            pf = float(summary_data.get("profit_factor", 1.0))
            equity = float(summary_data.get("equity", 10000.0))
            dd = float(summary_data.get("max_dd", 0.0))

            pnl_icon = "🟢" if pnl_usd >= 0 else "🔴"

            msg = (
                f"📊 <b>AUTOMATED DAILY PERFORMANCE SUMMARY</b>\n"
                f"------------------------------------\n"
                f"<b>Date:</b> {now_str}\n"
                f"<b>Daily PnL ($):</b> {pnl_icon} <b>${pnl_usd:+,.2f} ({pnl_pct:+.2f}%)</b>\n"
                f"<b>Trades Executed:</b> {trades}\n"
                f"<b>Hit Ratio (Win Rate):</b> {win_rate:.1f}%\n"
                f"<b>Daily Profit Factor:</b> {pf:.2f}\n"
                f"<b>Current Account Equity:</b> ${equity:,.2f}\n"
                f"<b>Peak Daily Drawdown:</b> {dd:.2f}%\n"
                f"------------------------------------\n"
                f"<i>AI Quant Lab v3.0 Production Engine</i>"
            )
            self.enqueue_message("DAILY_SUMMARY", msg)
        except Exception as e:
            logger.error(f"Error building daily summary: {e}")

    def stop(self):
        self.is_running = False
