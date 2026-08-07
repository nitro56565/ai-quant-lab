"""
Historical Event Replay Engine Module.
Replays historical price feeds through the Event Bus to debug edge cases and reproduce live trading behavior.
"""

from datetime import datetime
import pandas as pd
import logging
from data_loader.loader import DataLoader, DataRequest
from live_trading_engine.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)

class HistoricalReplayEngine:
    def __init__(self, event_bus: EventBus, symbol: str = "EURUSD", timeframe: str = "1h"):
        self.event_bus = event_bus
        self.symbol = symbol
        self.timeframe = timeframe
        self.loader = DataLoader()

    def run_replay(self, start_date: str = "2024-01-01", end_date: str = "2024-12-31"):
        logger.info(f"🔄 Starting Deterministic Event Replay for {self.symbol} ({start_date} to {end_date})...")
        req = DataRequest(symbol=self.symbol, timeframe=self.timeframe, start=start_date, end=end_date)
        df = self.loader.load(req)

        warmup_bars = 400
        for i in range(warmup_bars, len(df)):
            curr_bar = df.iloc[i]
            curr_time = df.index[i]

            spread_pips = 0.00012
            bid = curr_bar['close']
            ask = curr_bar['close'] + spread_pips

            start_idx = max(0, i - 400)
            rolling_df = df.iloc[start_idx:i + 1].copy()

            # 1. Emit TICK_UPDATE for limit order / position updates
            tick_data = {
                "timestamp": curr_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "dt": curr_time,
                "ask": ask,
                "bid": bid,
                "symbol": self.symbol
            }
            self.event_bus.publish(Event(EventType.TICK_UPDATE, tick_data))

            # 2. Emit BAR_CLOSED for model inference
            bar_data = {
                "timestamp": curr_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "symbol": self.symbol,
                "ask": ask,
                "bid": bid,
                "rolling_bars_df": rolling_df
            }
            self.event_bus.publish(Event(EventType.BAR_CLOSED, bar_data))

        logger.info("🏆 Historical Event Replay Complete.")
