#!/usr/bin/env python3
"""
TickVault Ingestion & Processing Pipeline
=========================================
Alternative automated data downloader based on Keyhan Kamyar's TickVault package
(https://keyhankamyar.github.io/posts/tickvault-introduction/).

Downloads, decodes, cleans, and resamples historical FX market data from TickVault.

Usage:
    python3 scripts/download_tickvault.py
"""

import os
import sys
import asyncio
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Import TickVault package by Keyhan Kamyar
from tick_vault import download_range, read_tick_data, config

# Configure TickVault download settings
try:
    config.MAX_CONCURRENT_DOWNLOADS = 4
    config.TIMEOUT_SECONDS = 30
except Exception:
    pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TickVaultPipeline")

# =====================================================================
# ⚙️ CONFIGURATION SETTINGS
# =====================================================================
SYMBOL = "EURUSD"                # Currency pair (e.g. "EURUSD", "GBPUSD")
YEARS = [2021]                   # Target years to download and ingest
# =====================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "market_data_pipeline" / "output"

async def download_symbol_year(symbol: str, year: int) -> bool:
    """
    Download raw ticks for a symbol and year using TickVault async downloader.
    """
    start_dt = datetime(year, 1, 1, 0, 0)
    end_dt = datetime(year, 12, 31, 23, 59)

    logger.info(f"⏳ Downloading tick data from TickVault for {symbol} ({start_dt.date()} to {end_dt.date()})...")
    try:
        await download_range(symbol=symbol.upper(), start=start_dt, end=end_dt)
        logger.info(f"✅ Download completed for {symbol} {year}")
        return True
    except Exception as e:
        logger.error(f"Failed to download tick range for {symbol} {year}: {e}")
        return False

def process_and_save_bars(symbol: str, year: int) -> bool:
    """
    Read downloaded tick data from TickVault local storage, resample to 1H bars, and save to Parquet.
    """
    start_dt = datetime(year, 1, 1, 0, 0)
    end_dt = datetime(year, 12, 31, 23, 59)

    logger.info(f"📖 Reading tick data from TickVault storage for {symbol} {year}...")
    try:
        df_ticks = read_tick_data(symbol=symbol.upper(), start=start_dt, end=end_dt)
        if df_ticks is None or df_ticks.empty:
            logger.error(f"No tick data available for {symbol} {year} in TickVault storage.")
            return False

        logger.info(f"Raw Ticks Loaded: {len(df_ticks)} rows")
        
        # Ensure datetime index
        if not isinstance(df_ticks.index, pd.DatetimeIndex):
            if 'timestamp' in df_ticks.columns:
                df_ticks['datetime'] = pd.to_datetime(df_ticks['timestamp'])
                df_ticks = df_ticks.set_index('datetime')
            elif 'time' in df_ticks.columns:
                df_ticks['datetime'] = pd.to_datetime(df_ticks['time'])
                df_ticks = df_ticks.set_index('datetime')

        # Compute bid and ask columns if missing
        if 'bid' in df_ticks.columns and 'ask' in df_ticks.columns:
            bid_col, ask_col = 'bid', 'ask'
        elif 'price' in df_ticks.columns:
            df_ticks['bid'] = df_ticks['price']
            df_ticks['ask'] = df_ticks['price'] + 0.00015
            bid_col, ask_col = 'bid', 'ask'
        else:
            bid_col = [c for c in df_ticks.columns if 'bid' in c.lower()][0]
            ask_col = [c for c in df_ticks.columns if 'ask' in c.lower()][0]

        vol_col = 'volume' if 'volume' in df_ticks.columns else 'vol'

        # Resample ticks to 1-Hour OHLCV bars
        logger.info("Resampling ticks to 1H OHLCV candles...")
        resample_dict = {
            bid_col: ['first', 'max', 'min', 'last'],
            ask_col: ['first', 'max', 'min', 'last']
        }
        if vol_col in df_ticks.columns:
            resample_dict[vol_col] = 'sum'

        df_1h = df_ticks.resample('1h').agg(resample_dict)
        
        # Flatten multi-level columns
        df_1h.columns = [
            'bid_open', 'bid_high', 'bid_low', 'bid_close',
            'ask_open', 'ask_high', 'ask_low', 'ask_close',
            'volume'
        ] if vol_col in df_ticks.columns else [
            'bid_open', 'bid_high', 'bid_low', 'bid_close',
            'ask_open', 'ask_high', 'ask_low', 'ask_close'
        ]
        
        if 'volume' not in df_1h.columns:
            df_1h['volume'] = 0.0

        df_1h = df_1h.dropna(subset=['bid_close', 'ask_close'])

        # Save to Parquet output directory
        out_1h_dir = OUTPUT_DIR / symbol.upper() / "bars" / "1h"
        out_1h_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = out_1h_dir / f"{year}.parquet"

        df_1h.to_parquet(parquet_path)
        logger.info(f"✅ Successfully saved {len(df_1h)} 1H candles to: {parquet_path}")
        logger.info(f"   Candle Date Range: {df_1h.index.min()} to {df_1h.index.max()}")
        return True

    except Exception as e:
        logger.error(f"Error processing TickVault data for {symbol} {year}: {e}")
        return False

def main():
    print("=================================================================")
    print("  🤖 AI QUANT LAB — TICKVAULT MARKET DATA INGESTION ENGINE")
    print("  (Keyhan Kamyar Architecture: https://keyhankamyar.github.io/)")
    print("=================================================================")
    print(f"Target Symbol: {SYMBOL}")
    print(f"Target Years:  {YEARS}")
    print(f"Output Dir:    {OUTPUT_DIR}")
    print("-" * 65)

    for year in YEARS:
        logger.info(f"Starting TickVault ingestion for {SYMBOL} {year}...")
        # Step 1: Download tick range
        download_success = asyncio.run(download_symbol_year(SYMBOL, year))
        
        # Step 2: Process and save Parquet bars
        if download_success or True:
            process_and_save_bars(SYMBOL, year)

if __name__ == "__main__":
    main()
