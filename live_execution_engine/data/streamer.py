"""
Real-Time Data Streamer Module.
Simulates live tick/bar streaming or interfaces with live REST/WebSocket APIs.
"""

from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import logging

from historical_data_ingestion.loader import DataLoader, DataRequest
from live_execution_engine.clock import BaseClock, RealClock
from live_execution_engine.data.base_provider import BaseMarketDataProvider
from live_execution_engine.data.oanda_provider import OANDAMarketDataProvider

logger = logging.getLogger(__name__)

class RealTimeDataStreamer:
    def __init__(self, symbol: str = "EURUSD", timeframe: str = "1h", 
                 clock: Optional[BaseClock] = None, 
                 provider: Optional[BaseMarketDataProvider] = None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.clock = clock or RealClock()
        self.provider = provider or OANDAMarketDataProvider(clock=self.clock)
        self.loader = DataLoader()
        self.full_df = None
        self.current_index = 0
        self.last_valid_ask = 1.15230
        self.last_valid_bid = 1.15215
        self.last_valid_mid = 1.152225

    def _fetch_live_oanda_h1_candles(self, count: int = 48) -> pd.DataFrame:
        """Delegates historical candle fetching to the decoupled Market Data Provider."""
        return self.provider.fetch_historical_candles(self.symbol, timeframe=self.timeframe, count=count)


    def initialize_stream(self, start_date: str = "2014-01-01", end_date: str = "2026-08-06"):
        logger.info(f"🔄 Initializing Live Bar Data Streamer for {self.symbol} ({self.timeframe}) across {start_date} to {end_date}...")
        req = DataRequest(symbol=self.symbol, timeframe=self.timeframe, start=start_date, end=end_date)

        self.full_df = self.loader.load(req)
        
        # Sync latest real-time H1 candles directly from OANDA v20 API
        df_oanda = self._fetch_live_oanda_h1_candles(count=48)
        if df_oanda is not None and not df_oanda.empty:
            df_combined = pd.concat([self.full_df, df_oanda])
            df_combined = df_combined[~df_combined.index.duplicated(keep='last')].sort_index()
            self.full_df = df_combined
            logger.info(f"🟢 Synced {len(df_oanda)} live OANDA H1 candles. Total dataset buffer: {len(self.full_df):,} bars.")

        self.current_index = len(self.full_df) - 1 # Position at latest bar
        if self.full_df is not None and len(self.full_df) > 0:
            c = float(self.full_df.iloc[-1]['close'])
            self.last_valid_mid = c
            self.last_valid_ask = c + 0.00006
            self.last_valid_bid = c - 0.00006
        logger.info(f"✅ Streamer initialized with {len(self.full_df):,} bars. Ready for live bar iteration.")

    def sync_latest_closed_candles(self, count: int = 2):
        """
        Dynamically fetches the latest closed H1 candles from OANDA and appends them
        to the internal dataset buffer so feature extraction doesn't go stale over 24h.
        """
        try:
            df_oanda = self._fetch_live_oanda_h1_candles(count=count)
            if df_oanda is not None and not df_oanda.empty:
                df_combined = pd.concat([self.full_df, df_oanda])
                df_combined = df_combined[~df_combined.index.duplicated(keep='last')].sort_index()
                self.full_df = df_combined
                self.current_index = len(self.full_df) - 1
                logger.info(f"🟢 Synchronized {len(df_oanda)} latest closed H1 candles from OANDA. Total buffer: {len(self.full_df):,}")
        except Exception as e:
            logger.error(f"⚠️ Failed to sync live candles from OANDA: {e}")

    def has_next_bar(self) -> bool:
        return self.current_index < len(self.full_df)

    def fetch_live_market_quote_detailed(self) -> tuple:
        """
        Fetches true real-time live price quote (ask, bid, mid) directly from the Market Data Provider.
        Maintains last_valid_price state during temporary network outages.
        """
        try:
            quote = self.provider.get_latest_quote(self.symbol)
            if quote and "ask" in quote:
                self.last_valid_ask = quote["ask"]
                self.last_valid_bid = quote["bid"]
                self.last_valid_mid = quote["mid"]
                return quote["ask"], quote["bid"], quote["mid"]
        except Exception as e:
            logger.warning(f"⚠️ Market Data Provider quote fetch error ({e}). Returning last valid quote state...")

        return self.last_valid_ask, self.last_valid_bid, self.last_valid_mid



    def fetch_live_market_quote(self) -> float:
        ask, bid, mid = self.fetch_live_market_quote_detailed()
        return mid

    def get_next_tick_and_bars(self) -> tuple:
        """
        Fetches current live real-time price and returns (curr_time, ask, bid, rolling_df).
        """
        curr_time = datetime.now(timezone.utc)
        ask, bid, mid = self.fetch_live_market_quote_detailed()

        # Build rolling historical feature window (latest 400 bars + live tick)
        start_idx = max(0, len(self.full_df) - 400)
        rolling_df = self.full_df.iloc[start_idx:].copy()

        # Append live candle tick with clean DatetimeIndex
        naive_dt = curr_time.replace(tzinfo=None)
        new_row = pd.DataFrame([{
            'open': mid,
            'high': mid + 0.00005,
            'low': mid - 0.00005,
            'close': mid,
            'volume': 1000
        }], index=pd.DatetimeIndex([naive_dt]))


        rolling_df = pd.concat([rolling_df, new_row])
        rolling_df.index = pd.to_datetime(rolling_df.index)
        if getattr(rolling_df.index, 'tz', None) is not None:
            rolling_df.index = rolling_df.index.tz_localize(None)



        self.current_index += 1
        return curr_time, ask, bid, rolling_df

