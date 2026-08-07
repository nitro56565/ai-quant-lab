"""
Zero-Branching Historical Replay Provider v3.0.
Implements MarketDataProvider interface. Streams historical ticks or Parquet candles into the exact same pipeline with ZERO conditional branching in core execution code.
"""

import time
import logging
from typing import Callable, Dict, Any, List, Optional
import pandas as pd
from live_trading_engine.data.base_provider import MarketDataProvider
from data_loader.loader import DataLoader, DataRequest

logger = logging.getLogger("ReplayProvider")

class ReplayProvider(MarketDataProvider):
    """
    Historical Replay Market Data Provider.
    Feeds historical market data step-by-step into downstream EventBus callbacks.
    """
    def __init__(self, start_date: str = "2024-01-01", end_date: str = "2024-12-31", fast_mode: bool = True):
        self.start_date = start_date
        self.end_date = end_date
        self.fast_mode = fast_mode
        self.loader = DataLoader()
        self.is_running = False
        self.processed_ticks_count = 0
        self.last_tick_time = None

    def start(self, symbol: str, tick_callback: Callable[[Dict[str, Any]], None]):
        logger.info(f"🔄 Starting ReplayProvider for {symbol} ({self.start_date} to {self.end_date})...")
        req = DataRequest(symbol=symbol, timeframe="1h", start=self.start_date, end=self.end_date)
        df = self.loader.load(req)

        self.is_running = True
        spread_pips = 0.00012

        for idx, row in df.iterrows():
            if not self.is_running:
                break

            close_price = float(row['close'])
            bid = round(close_price, 5)
            ask = round(close_price + spread_pips, 5)
            ts_str = idx.strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(idx, pd.Timestamp) else str(idx)

            tick_data = {
                "symbol": symbol,
                "timestamp": ts_str,
                "bid": bid,
                "ask": ask,
                "mid": close_price,
                "spread": spread_pips,
                "liquidity_bid": 1.0,
                "liquidity_ask": 1.0
            }

            self.processed_ticks_count += 1
            self.last_tick_time = ts_str
            tick_callback(tick_data)

            if not self.fast_mode:
                time.sleep(0.01)

        logger.info(f"✅ ReplayProvider complete. Processed {self.processed_ticks_count:,} historical steps.")

    def stop(self):
        self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "ReplayProvider",
            "is_running": self.is_running,
            "processed_ticks_count": self.processed_ticks_count,
            "last_tick_time": self.last_tick_time
        }
