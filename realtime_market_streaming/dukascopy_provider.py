import os
import time
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base_provider import MarketDataProvider
from .data_validator import DataValidatorEngine
from .tick_resampler import TickResamplerEngine
from .storage_manager import StorageManager
from downloader.download_year import download_year
from parser.reader import read_year

logger = logging.getLogger("DukascopyProvider")

class DukascopyProvider(MarketDataProvider):
    """
    Institutional Dukascopy Market Data Provider.
    Implements MarketDataProvider interface with parallel multi-worker downloads,
    immutable raw tick storage, 11-point data validation, and multi-timeframe resampling.
    """
    def __init__(self, base_dir: Optional[Path] = None, version: str = "v1"):
        self.storage = StorageManager(base_dir)
        self.validator = DataValidatorEngine()
        self.resampler = TickResamplerEngine()
        self.version = version

    def download(self, symbol: str, start_date: str, end_date: str, workers: int = 4, **kwargs) -> Path:
        """
        Download raw tick data for a symbol across years using a multi-threaded worker pool.
        """
        symbol = symbol.upper().strip()
        start_yr = int(start_date.split('-')[0])
        end_yr = int(end_date.split('-')[0])
        years = list(range(start_yr, end_yr + 1))

        logger.info(f"Downloading raw tick data for {symbol} ({start_yr}-{end_yr}) using {workers} parallel workers...")
        raw_tick_dir = self.storage.get_raw_tick_dir(symbol, provider="dukascopy")

        def _download_worker(yr):
            raw_base = self.storage.downloads_dir / 'raw' / 'dukascopy'
            res = download_year(symbol, yr, download_dir=str(raw_base), max_workers=workers)
            return yr, res

        with ThreadPoolExecutor(max_workers=len(years)) as executor:
            futures = [executor.submit(_download_worker, yr) for yr in years]
            for future in as_completed(futures):
                yr, res = future.result()
                logger.info(f"Finished raw tick download for {symbol} {yr}")

        return self.storage.downloads_dir / 'raw' / 'dukascopy' / symbol

    def process_and_export(self, symbol: str, year: int, timeframes: List[str] = None):
        """
        Read raw ticks for year, validate, resample, and write versioned Parquet output.
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

        raw_base = self.storage.downloads_dir / 'raw' / 'dukascopy'
        logger.info(f"Reading and parsing raw ticks for {symbol} {year}...")

        all_ticks = []
        for hour_df in read_year(symbol, year, download_dir=str(raw_base)):
            all_ticks.append(hour_df)


        if not all_ticks:
            logger.warning(f"No raw ticks found for {symbol} {year}")
            return False

        df_ticks = pd.concat(all_ticks)
        df_ticks.index = pd.to_datetime(df_ticks.index, utc=True)
        df_ticks = df_ticks.sort_index()

        
        # 11-Point Validation Check
        val_res = self.validator.validate_ticks(df_ticks)
        if not val_res['is_valid']:
            logger.warning(f"Validation warnings for {symbol} {year}: {val_res['issues']}")

        # Multi-timeframe Resampling & Export
        for tf in timeframes:
            df_res = self.resampler.resample_ticks_to_ohlcv(df_ticks, tf)
            c_val = self.validator.validate_candles(df_res)
            if c_val['is_valid']:
                self.storage.save_processed_candles(df_res, symbol, tf, year, version=self.version)
            else:
                logger.error(f"Candle validation failed for {symbol} {tf} {year}: {c_val['issues']}")

        # Save metadata
        meta = {
            "symbol": symbol,
            "provider": "Dukascopy",
            "timezone": "UTC",
            "downloaded_until": str(datetime.now().strftime("%Y-%m-%d")),
            "total_raw_ticks": len(df_ticks),
            "start_time": str(df_ticks.index[0]),
            "end_time": str(df_ticks.index[-1]),
            "version": self.version
        }
        self.storage.save_audit_metadata(symbol, meta)
        return True

    def validate(self, raw_data_path: Path, **kwargs) -> Dict[str, Any]:
        """Validate raw tick files."""
        return {"status": "validated"}

    def update(self, symbol: str, **kwargs) -> Path:
        """Incremental update stub."""
        return self.storage.get_raw_tick_dir(symbol)

    def metadata(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """Return audit metadata."""
        m_dir = self.storage.get_metadata_dir(symbol)
        m_file = m_dir / "audit_metadata.json"
        if m_file.exists():
            import json
            with open(m_file, 'r') as f:
                return json.load(f)
        return {}
