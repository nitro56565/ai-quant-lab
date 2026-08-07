"""
Real-Time Data Streamer Module.
Simulates live tick/bar streaming or interfaces with live REST/WebSocket APIs.
"""

from datetime import datetime, timezone
import pandas as pd
import logging
from data_loader.loader import DataLoader, DataRequest

logger = logging.getLogger(__name__)

class RealTimeDataStreamer:
    def __init__(self, symbol: str = "EURUSD", timeframe: str = "1h"):
        self.symbol = symbol
        self.timeframe = timeframe
        self.loader = DataLoader()
        self.full_df = None
        self.current_index = 0
        self.last_valid_ask = 1.15230
        self.last_valid_bid = 1.15215
        self.last_valid_mid = 1.152225

    def _fetch_live_oanda_h1_candles(self, count: int = 48) -> pd.DataFrame:
        """Fetches latest real H1 candles directly from OANDA REST v20 API."""
        import os
        import urllib.request
        import json

        oanda_key = os.getenv("OANDA_API_KEY")
        oanda_acc = os.getenv("OANDA_ACCOUNT_ID")
        if not (oanda_key and oanda_acc):
            return None

        try:
            instrument = self.symbol.replace("/", "_")
            if "_" not in instrument and len(instrument) == 6:
                instrument = f"{instrument[:3]}_{instrument[3:]}"
            oanda_env = os.getenv("OANDA_ENV", "practice").lower()
            base_domain = "api-fxpractice.oanda.com" if oanda_env == "practice" else "api-fxtrade.oanda.com"
            url = f"https://{base_domain}/v3/instruments/{instrument}/candles?granularity=H1&count={count}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {oanda_key}"})
            
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read())
                rows = []
                for c in data.get("candles", []):
                    ts = pd.to_datetime(c["time"]).tz_localize(None)
                    rows.append({
                        "timestamp": ts,
                        "open": float(c["mid"]["o"]),
                        "high": float(c["mid"]["h"]),
                        "low": float(c["mid"]["l"]),
                        "close": float(c["mid"]["c"]),
                        "volume": int(c.get("volume", 1000))
                    })
                if rows:
                    df_oanda = pd.DataFrame(rows).set_index("timestamp")
                    return df_oanda

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch live OANDA H1 candles: {e}")
        return None

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


    def has_next_bar(self) -> bool:
        return self.current_index < len(self.full_df)

    def fetch_live_market_quote_detailed(self) -> tuple:
        """
        Fetches true real-time live price quote (ask, bid, mid) directly from OANDA v20 pricing or fallbacks.
        Maintains last_valid_price state during temporary network outages.
        """
        import os
        import urllib.request
        import json

        # Tier 1: OANDA v20 Real-Time Pricing REST API (when credentials are present)
        oanda_key = os.getenv("OANDA_API_KEY")
        oanda_acc = os.getenv("OANDA_ACCOUNT_ID")
        if oanda_key and oanda_acc:
            try:
                instrument = self.symbol.replace("/", "_")
                if "_" not in instrument and len(instrument) == 6:
                    instrument = f"{instrument[:3]}_{instrument[3:]}"
                oanda_env = os.getenv("OANDA_ENV", "practice").lower()
                base_domain = "api-fxpractice.oanda.com" if oanda_env == "practice" else "api-fxtrade.oanda.com"
                url = f"https://{base_domain}/v3/accounts/{oanda_acc}/pricing?instruments={instrument}"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {oanda_key}"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read())
                    ask = float(data['prices'][0]['asks'][0]['price'])
                    bid = float(data['prices'][0]['bids'][0]['price'])
                    mid = (ask + bid) / 2.0
                    self.last_valid_ask = ask
                    self.last_valid_bid = bid
                    self.last_valid_mid = mid
                    return ask, bid, mid
            except Exception as e_oanda:
                logger.warning(f"⚠️ OANDA v20 API feed error ({e_oanda}). Falling back to secondary feeds...")

        ticker = f"{self.symbol}=X" if "USDT" not in self.symbol else f"{self.symbol.replace('USDT', '-USD')}"
        if self.symbol == "BTCUSDT":
            ticker = "BTC-USD"
        elif self.symbol == "XAUUSD":
            ticker = "GC=F"

        # Tier 2: Yahoo Finance Real-time Chart API
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read())
                mid = float(data['chart']['result'][0]['meta']['regularMarketPrice'])
                spread = 0.00012
                ask = round(mid + (spread/2), 5)
                bid = round(mid - (spread/2), 5)
                self.last_valid_ask = ask
                self.last_valid_bid = bid
                self.last_valid_mid = mid
                return ask, bid, mid
        except Exception as e1:
            logger.warning(f"⚠️ Yahoo Finance feed unreachable ({e1}). Using last valid live quote...")

        # Network Outage Fallback: Preserve exact last valid live market price without synthetic jumps
        logger.info(f"🌐 [NETWORK RECOVERY HOLD] Maintaining last known valid quote: Ask ${self.last_valid_ask:.5f} | Bid ${self.last_valid_bid:.5f}")
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

