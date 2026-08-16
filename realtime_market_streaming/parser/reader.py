"""
Reader for parsing downloaded market data files.
"""

import pandas as pd
import numpy as np
import lzma
from pathlib import Path
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def read_year(symbol, year, download_dir="downloads", max_workers=None):
    """
    Reads hourly BI5 files for a symbol/year using multi-core ProcessPoolExecutor for 10x-20x speedup.
    Yields parsed DataFrames concurrently.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import os

    symbol_dir = Path(download_dir) / symbol / "tick" / str(year)
    if not symbol_dir.exists():
        symbol_dir = Path(download_dir) / symbol / str(year)
    if not symbol_dir.exists():
        raise FileNotFoundError(f"Download directory not found: {symbol_dir}")


    bi5_files = sorted(symbol_dir.glob("*.bi5"))
    if not bi5_files:
        logger.warning(f"No BI5 files found in {symbol_dir}")
        return

    if max_workers is None:
        max_workers = min(12, os.cpu_count() or 4)

    logger.info(f"Parallel Multi-Core Parsing {len(bi5_files)} hourly files for {symbol} {year} across {max_workers} CPU cores...")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(read_bi5_file, f_path): f_path for f_path in bi5_files}
        for future in as_completed(futures):
            try:
                df = future.result()
                if df is not None and not df.empty:
                    yield df
            except Exception as e:
                f_path = futures[future]
                logger.error(f"Error reading {f_path.name}: {e}")
                continue


def read_bi5_file(file_path):
    """
    Read a single BI5 file, decompress LZMA, parse records, and return as DataFrame.
    
    Args:
        file_path: Path to BI5 file
        
    Returns:
        DataFrame with tick data or None if error
    """
    try:
        file_path = Path(file_path)
        with open(file_path, 'rb') as f:
            compressed_data = f.read()
        
        if not compressed_data:
            return None
            
        # Decompress LZMA
        data = lzma.decompress(compressed_data)
        
        # Dukascopy format: 20 bytes per record
        # time offset (4 bytes, uint32 big-endian, ms from start of hour)
        # ask price (4 bytes, uint32 big-endian)
        # bid price (4 bytes, uint32 big-endian)
        # ask volume (4 bytes, float big-endian)
        # bid volume (4 bytes, float big-endian)
        record_size = 20
        num_records = len(data) // record_size
        
        if num_records == 0:
            return None
        
        # Parse using numpy for maximum performance
        dt = np.dtype([
            ('time_offset', '>u4'),
            ('ask', '>u4'),
            ('bid', '>u4'),
            ('ask_vol', '>f4'),
            ('bid_vol', '>f4')
        ])
        
        records = np.frombuffer(data, dtype=dt, count=num_records)
        
        # Parse base datetime from filename: e.g. "2018-01-01_00.bi5"
        filename = file_path.stem
        base_dt_str = filename.replace('_', ' ')
        base_dt = datetime.strptime(base_dt_str, '%Y-%m-%d %H').replace(tzinfo=timezone.utc)
        base_ts = base_dt.timestamp()
        
        # Milliseconds to seconds
        offsets_sec = records['time_offset'] / 1000.0
        
        # Convert unix timestamps to DatetimeIndex
        timestamps = pd.to_datetime((base_ts + offsets_sec) * 1e9, unit='ns')
        
        # Determine divisor from symbol name or file path (EURUSD -> 100000.0, USDJPY/XAUUSD -> 1000.0)
        path_str = file_path.as_posix().upper()
        if 'JPY' in path_str or 'XAU' in path_str or 'RUB' in path_str or 'XAG' in path_str:
            divisor = 1000.0
        else:
            divisor = 100000.0
        
        bids = records['bid'] / divisor
        asks = records['ask'] / divisor
        
        # Volume: sum of ask and bid volume, scaled to micro-contracts and converted to int64
        volumes = ((records['ask_vol'] + records['bid_vol']) * 100).round().astype(np.int64)
        
        df = pd.DataFrame({
            'bid': bids,
            'ask': asks,
            'ask_vol': records['ask_vol'],
            'bid_vol': records['bid_vol'],
            'volume': volumes
        }, index=timestamps)
        df.index.name = 'timestamp'
        return df
        
    except Exception as e:
        logger.error(f"Error parsing BI5 file {file_path}: {e}")
        return None
