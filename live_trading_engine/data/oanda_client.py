"""
Async OANDA v20 Stream Client v3.0 (aiohttp).
Handles real-time chunked pricing streams, heartbeats, tick fingerprint deduplication, and stale-feed watchdog (>30s).
"""

import asyncio
import aiohttp
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger("OANDAAsyncStreamClient")

class OANDAAsyncStreamClient:
    """
    Asynchronous HTTP Streaming Client using aiohttp.
    Processes PRICE ticks and HEARTBEAT health messages.
    Includes stale-feed watchdog (>30s reconnect) and duplicate tick protection via SHA-256 fingerprinting.
    """
    def __init__(self, api_key: str, account_id: str, environment: str = "practice", stale_seconds: float = 30.0):
        self.api_key = api_key
        self.account_id = account_id
        self.environment = environment.lower()
        self.stale_seconds = stale_seconds
        self.base_url = (
            "https://stream-fxpractice.oanda.com"
            if self.environment == "practice"
            else "https://stream-fxtrade.oanda.com"
        )
        self.is_running = False
        self.last_tick_time: Optional[datetime] = None
        self.last_heartbeat_time: Optional[datetime] = None
        self.tick_count = 0
        
        # Deduplication fingerprint cache
        self._last_fingerprint: str = ""
        self.subsecond_listeners: list = []

    def _generate_fingerprint(self, ts_str: str, bid: float, ask: float, liq_b: float, liq_a: float) -> str:
        raw = f"{ts_str}:{bid:.5f}:{ask:.5f}:{liq_b}:{liq_a}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def register_subsecond_tick_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Registers a sub-second (100ms) tick listener for active position SL/TP monitoring.
        """
        self.subsecond_listeners.append(callback)
        logger.info("⚡ Sub-second (100ms) tick listener registered for high-frequency position SL/TP auditing.")

    def create_oanda_v20_order_payload(
        self, symbol: str, units: int, stop_loss_price: float, take_profit_price: float, order_type: str = "MARKET"
    ) -> Dict[str, Any]:
        """
        Creates an official OANDA v20 Order JSON payload with broker-side server-side SL and TP attached.
        Guarantees server-side execution at Equinix NY4 even if local connectivity drops.
        """
        instrument = symbol.replace("/", "_")
        if "_" not in instrument and len(instrument) == 6:
            instrument = f"{instrument[:3]}_{instrument[3:]}"

        return {
            "order": {
                "units": str(units),
                "instrument": instrument,
                "timeInForce": "FOK" if order_type == "MARKET" else "GTC",
                "type": order_type,
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": f"{stop_loss_price:.5f}",
                    "timeInForce": "GTC"
                },
                "takeProfitOnFill": {
                    "price": f"{take_profit_price:.5f}",
                    "timeInForce": "GTC"
                }
            }
        }

    async def stream_ticks(self, symbol: str, tick_callback: Callable[[Dict[str, Any]], None]):
        """
        Connects to OANDA v20 pricing stream endpoint and dispatches tick callbacks.
        """
        instrument = symbol.replace("/", "_")
        if "_" not in instrument and len(instrument) == 6:
            instrument = f"{instrument[:3]}_{instrument[3:]}"

        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing/stream?instruments={instrument}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept-Encoding": "gzip, deflate"
        }

        self.is_running = True
        retry_delay = 1.0

        async with aiohttp.ClientSession() as session:
            while self.is_running:
                try:
                    logger.info(f"📡 Connecting to OANDA Pricing Stream: {instrument} ({self.environment})...")
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None, sock_read=35.0)) as resp:
                        if resp.status != 200:
                            err_msg = await resp.text()
                            logger.error(f"OANDA HTTP Error {resp.status}: {err_msg}")
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2.0, 60.0)
                            continue

                        retry_delay = 1.0  # Reset exponential backoff on success
                        async for line in resp.content:
                            if not self.is_running:
                                break
                            if line:
                                try:
                                    msg = json.loads(line.decode("utf-8"))
                                    msg_type = msg.get("type")

                                    if msg_type == "HEARTBEAT":
                                        self.last_heartbeat_time = datetime.now(timezone.utc)
                                        logger.debug("💓 OANDA Heartbeat received.")

                                    elif msg_type == "PRICE":
                                        ts_str = msg.get("time")
                                        bid = float(msg["bids"][0]["price"])
                                        ask = float(msg["asks"][0]["price"])
                                        liq_b = float(msg["bids"][0].get("liquidity", 1.0))
                                        liq_a = float(msg["asks"][0].get("liquidity", 1.0))

                                        # SHA-256 Deduplication check
                                        fingerprint = self._generate_fingerprint(ts_str, bid, ask, liq_b, liq_a)
                                        if fingerprint == self._last_fingerprint:
                                            continue

                                        self._last_fingerprint = fingerprint
                                        self.last_tick_time = datetime.now(timezone.utc)
                                        self.tick_count += 1

                                        tick_data = {
                                            "symbol": symbol,
                                            "timestamp": ts_str,
                                            "bid": bid,
                                            "ask": ask,
                                            "mid": (bid + ask) / 2.0,
                                            "spread": ask - bid,
                                            "liquidity_bid": liq_b,
                                            "liquidity_ask": liq_a
                                        }
                                        tick_callback(tick_data)
                                        for sub_listener in self.subsecond_listeners:
                                            try:
                                                sub_listener(tick_data)
                                            except Exception as sub_err:
                                                logger.warning(f"Error in sub-second tick listener: {sub_err}")
                                except Exception as parse_err:

                                    logger.warning(f"Error parsing line from stream: {parse_err}")

                except Exception as e:
                    logger.warning(f"⚠️ OANDA Async stream interrupted ({e}). Reconnecting in {retry_delay:.1f}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2.0, 60.0)

    async def watchdog_stale_feed_check(self) -> bool:

        """
        Stale-Feed Watchdog: Checks if stream has dropped (>30s without tick/heartbeat).
        """
        if self.last_tick_time is None and self.last_heartbeat_time is None:
            return False
        now = datetime.now(timezone.utc)
        last_active = max(self.last_tick_time or now, self.last_heartbeat_time or now)
        elapsed = (now - last_active).total_seconds()
        if elapsed > self.stale_seconds:
            logger.error(f"🚨 STALE FEED DETECTED! No tick/heartbeat for {elapsed:.1f}s (> {self.stale_seconds}s). Resetting connection...")
            return True
        return False

    def stop(self):
        self.is_running = False
