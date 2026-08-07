"""
Dual Bid / Ask / Mid Hourly Candle Aggregator v3.0.
Aggregates ticks into Dual Bid, Ask, and Mid OHLC candles.
Seals candles strictly using provider timestamps with a 250ms grace window.
Includes multi-hour gap detection & REST backfill callback logic.
"""

import asyncio
import pandas as pd
from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional, Callable, Awaitable

logger = logging.getLogger("DualHourlyCandleAggregator")

class HourlyCandleAggregator:
    """
    Dual Bid / Ask / Mid Candle Aggregator.
    Produces:
      - Mid OHLC: open, high, low, close
      - Bid OHLC: bid_open, bid_high, bid_low, bid_close
      - Ask OHLC: ask_open, ask_high, ask_low, ask_close
      - Metrics: spread_min, spread_max, tick_volume
    """
    def __init__(self, symbol: str = "EURUSD", seal_grace_ms: int = 250):
        self.symbol = symbol
        self.seal_grace_ms = seal_grace_ms
        self.current_hour: Optional[datetime] = None
        self.current_candle: Optional[Dict[str, Any]] = None

    async def process_tick_async(
        self, 
        tick: Dict[str, Any], 
        rest_backfill_cb: Optional[Callable[[datetime, datetime], Awaitable[None]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Asynchronously processes an incoming tick.
        Returns a sealed Dict candle object when top-of-hour boundary is crossed.
        """
        provider_dt = pd.to_datetime(tick["timestamp"]).tz_convert(timezone.utc)
        candle_hour = provider_dt.replace(minute=0, second=0, microsecond=0)

        closed_candle = None

        if self.current_hour is not None and candle_hour > self.current_hour:
            # 250ms Sealing Grace Window to ingest late in-flight ticks for closing hour
            if self.seal_grace_ms > 0:
                await asyncio.sleep(self.seal_grace_ms / 1000.0)

            # Check multi-hour gap (e.g. 10:00 to 13:00)
            hours_diff = int((candle_hour - self.current_hour).total_seconds() // 3600)
            if hours_diff > 1 and rest_backfill_cb:
                logger.warning(f"⚠️ Multi-hour gap detected ({hours_diff} hours between {self.current_hour} and {candle_hour}). Triggering REST backfill...")
                try:
                    await rest_backfill_cb(self.current_hour, candle_hour)
                except Exception as backfill_err:
                    logger.error(f"Error executing REST gap backfill: {backfill_err}")

            closed_candle = self.current_candle.copy()
            logger.info(
                f"⏰ H1 Candle Sealed for {self.symbol} at {self.current_hour.strftime('%Y-%m-%d %H:%M:%S UTC')}: "
                f"Mid [{closed_candle['open']:.5f}/{closed_candle['close']:.5f}], "
                f"Bid [{closed_candle['bid_open']:.5f}/{closed_candle['bid_close']:.5f}], "
                f"Ask [{closed_candle['ask_open']:.5f}/{closed_candle['ask_close']:.5f}], "
                f"Ticks: {closed_candle['tick_volume']}"
            )
            self.current_hour = candle_hour
            self.current_candle = self._init_candle(tick, candle_hour)

        elif self.current_hour is None:
            self.current_hour = candle_hour
            self.current_candle = self._init_candle(tick, candle_hour)
        else:
            self._update_candle(tick)

        return closed_candle

    def process_tick_sync(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Synchronous fallback for tick processing.
        """
        provider_dt = pd.to_datetime(tick["timestamp"]).tz_convert(timezone.utc)
        candle_hour = provider_dt.replace(minute=0, second=0, microsecond=0)

        closed_candle = None

        if self.current_hour is not None and candle_hour > self.current_hour:
            closed_candle = self.current_candle.copy()
            self.current_hour = candle_hour
            self.current_candle = self._init_candle(tick, candle_hour)
        elif self.current_hour is None:
            self.current_hour = candle_hour
            self.current_candle = self._init_candle(tick, candle_hour)
        else:
            self._update_candle(tick)

        return closed_candle

    def _init_candle(self, tick: Dict[str, Any], candle_hour: datetime) -> Dict[str, Any]:
        bid, ask, mid = tick["bid"], tick["ask"], tick["mid"]
        spread = tick["spread"]
        return {
            "timestamp": candle_hour,
            "symbol": self.symbol,
            "open": mid, "high": mid, "low": mid, "close": mid,
            "bid_open": bid, "bid_high": bid, "bid_low": bid, "bid_close": bid,
            "ask_open": ask, "ask_high": ask, "ask_low": ask, "ask_close": ask,
            "spread_min": spread, "spread_max": spread,
            "tick_volume": 1
        }

    def _update_candle(self, tick: Dict[str, Any]):
        bid, ask, mid = tick["bid"], tick["ask"], tick["mid"]
        spread = tick["spread"]
        c = self.current_candle

        c["high"] = max(c["high"], mid)
        c["low"] = min(c["low"], mid)
        c["close"] = mid

        c["bid_high"] = max(c["bid_high"], bid)
        c["bid_low"] = min(c["bid_low"], bid)
        c["bid_close"] = bid

        c["ask_high"] = max(c["ask_high"], ask)
        c["ask_low"] = min(c["ask_low"], ask)
        c["ask_close"] = ask

        c["spread_min"] = min(c["spread_min"], spread)
        c["spread_max"] = max(c["spread_max"], spread)
        c["tick_volume"] += 1
