#!/usr/bin/env python3
"""
Bulk Historical Data Importer
=============================
Import large historical datasets (CSV, ZIP, or Parquet) from external providers 
(like HistData, Kaggle, or custom CSV exports) directly into the TickVault database.

This script parses the bulk data, serializes it to Parquet, executes data cleaning,
resamples it to all target timeframes, and generates the required index metadata.

To run:
    python3 import_bulk_data.py
"""

import os
import sys
import json
import zipfile
import logging
from pathlib import Path
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BulkImporter")

# =====================================================================
# ⚙️ IMPORT CONFIGURATION SETTINGS (Modify these before running)
# =====================================================================
INPUT_FILE_PATH = "downloads/EURUSD/2020"                 # Path to bulk file/directory (CSV, ZIP, or Parquet)
SYMBOL = "EURUSD"                                         # Symbol to register (e.g. "EURUSD")
YEAR = 2020                                               # Year of the data
FORMAT_TYPE = "histdata_tick"

# Column mappings for "generic_tick" or "generic_bar" (only used if FORMAT_TYPE is generic)
COLUMN_MAP = {
    'timestamp': 'Timestamp',
    'bid': 'Bid',
    'ask': 'Ask',
    'volume': 'Volume'
}
# =====================================================================


def read_histdata_tick(file_path):
    """Parse HistData.com tick format (zipped or raw CSV)."""
    logger.info(f"Parsing HistData tick file: {file_path}")
    
    # Auto-detect separator
    sep = ','
    if file_path.suffix.lower() == '.zip':
        with zipfile.ZipFile(file_path, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
            if not csv_files:
                raise ValueError("No CSV file found inside ZIP archive")
            # Read first line to detect separator
            with z.open(csv_files[0], 'r') as sample_f:
                first_line = sample_f.readline().decode('utf-8')
                sep = ';' if ';' in first_line else ','
            logger.info(f"Detected separator '{sep}'. Extracting & loading {csv_files[0]} from ZIP...")
            f = z.open(csv_files[0])
    else:
        with open(file_path, 'r', encoding='utf-8') as sample_f:
            first_line = sample_f.readline()
            sep = ';' if ';' in first_line else ','
        logger.info(f"Detected separator '{sep}'. Opening file...")
        f = open(file_path, 'rb')

    try:
        # HistData tick format: YYYYMMDD HHMMSSmmm[sep]Bid[sep]Ask[sep]Volume
        df = pd.read_csv(
            f,
            sep=sep,
            header=None,
            names=['timestamp_raw', 'bid', 'ask', 'volume'],
            dtype={'bid': float, 'ask': float, 'volume': float}
        )
        
        logger.info("Parsing raw timestamp strings to DatetimeIndex...")
        df['timestamp'] = pd.to_datetime(df['timestamp_raw'], format='%Y%m%d %H%M%S%f')
        df = df.drop(columns=['timestamp_raw'])
        
        return df, 'ticks'
    finally:
        f.close()


def read_histdata_1min(file_path):
    """Parse HistData.com 1-minute bar format (zipped or raw CSV)."""
    logger.info(f"Parsing HistData 1-minute bar file: {file_path}")
    
    sep = ';'
    if file_path.suffix.lower() == '.zip':
        with zipfile.ZipFile(file_path, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv') or f.endswith('.txt')]
            if not csv_files:
                raise ValueError("No text/CSV file found inside ZIP archive")
            with z.open(csv_files[0], 'r') as sample_f:
                first_line = sample_f.readline().decode('utf-8')
                sep = ';' if ';' in first_line else ','
            logger.info(f"Detected separator '{sep}'. Extracting & loading {csv_files[0]} from ZIP...")
            f = z.open(csv_files[0])
    else:
        with open(file_path, 'r', encoding='utf-8') as sample_f:
            first_line = sample_f.readline()
            sep = ';' if ';' in first_line else ','
        logger.info(f"Detected separator '{sep}'. Opening file...")
        f = open(file_path, 'rb')

    try:
        # HistData 1-min format: YYYY.MM.DD HH:MM[sep]Open[sep]High[sep]Low[sep]Close[sep]Volume
        df = pd.read_csv(
            f,
            sep=sep,
            header=None,
            names=['timestamp_raw', 'open', 'high', 'low', 'close', 'volume'],
            dtype={'open': float, 'high': float, 'low': float, 'close': float, 'volume': float}
        )
        
        logger.info("Parsing raw timestamp strings to DatetimeIndex...")
        df['timestamp'] = pd.to_datetime(df['timestamp_raw'], format='%Y.%m.%d %H:%M')
        df = df.drop(columns=['timestamp_raw'])
        
        return df, 'bars'
    finally:
        f.close()


def read_generic(file_path, is_tick=True):
    """Parse generic CSV file with headers."""
    logger.info(f"Parsing generic CSV file: {file_path}")
    df = pd.read_csv(file_path)
    
    # Invert mapping to rename
    inv_map = {v: k for k, v in COLUMN_MAP.items() if v in df.columns}
    df = df.rename(columns=inv_map)
    
    if 'timestamp' not in df.columns:
        raise ValueError("Missing 'timestamp' column in generic file structure.")
        
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Add ask/volume columns if missing for tick
    if is_tick:
        if 'ask' not in df.columns and 'bid' in df.columns:
            df['ask'] = df['bid']
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        return df[['timestamp', 'bid', 'ask', 'volume']], 'ticks'
    else:
        if 'volume' not in df.columns:
            df['volume'] = 0.0
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']], 'bars'


def main():
    logger.info("=" * 65)
    logger.info("📂 BULK DATA IMPORT ORCHESTRATOR")
    logger.info("=" * 65)
    
    file_path = Path(INPUT_FILE_PATH)
    if not file_path.exists():
        logger.error(f"Input path not found at: {file_path}")
        sys.exit(1)

    # Detect if directory input
    files_to_process = []
    if file_path.is_dir():
        all_zips = sorted(file_path.glob("*.zip"))
        all_csvs = sorted(file_path.glob("*.csv"))
        all_txts = sorted(file_path.glob("*.txt"))
        files_to_process = all_zips + all_csvs + all_txts
        if not files_to_process:
            logger.error(f"No zip/csv/txt files found in directory: {file_path}")
            sys.exit(1)
        logger.info(f"Detected directory input. Found {len(files_to_process)} files to import in sequence.")
    else:
        files_to_process = [file_path]

    # 1. Parse all files in loop
    dfs = []
    data_type = None
    
    try:
        for f_to_parse in files_to_process:
            logger.info(f"Importing file: {f_to_parse.name}")
            if FORMAT_TYPE == "histdata_tick":
                sub_df, dt_type = read_histdata_tick(f_to_parse)
            elif FORMAT_TYPE == "histdata_1min":
                sub_df, dt_type = read_histdata_1min(f_to_parse)
            elif FORMAT_TYPE == "generic_tick":
                sub_df, dt_type = read_generic(f_to_parse, is_tick=True)
            elif FORMAT_TYPE == "generic_bar":
                sub_df, dt_type = read_generic(f_to_parse, is_tick=False)
            elif FORMAT_TYPE == "parquet":
                logger.info(f"Loading Parquet: {f_to_parse}")
                sub_df = pd.read_parquet(f_to_parse)
                dt_type = 'ticks' if 'bid' in sub_df.columns else 'bars'
                if 'timestamp' in sub_df.columns:
                    sub_df['timestamp'] = pd.to_datetime(sub_df['timestamp'])
                elif not isinstance(sub_df.index, pd.DatetimeIndex):
                    sub_df.index = pd.to_datetime(sub_df.index)
                    sub_df = sub_df.reset_index().rename(columns={'index': 'timestamp', 'timestamp': 'timestamp'})
            else:
                raise ValueError(f"Unknown format type: {FORMAT_TYPE}")
                
            dfs.append(sub_df)
            data_type = dt_type
            
        logger.info("Concatenating all parsed datasets...")
        df = pd.concat(dfs, ignore_index=True)
            
    except Exception as e:
        logger.error(f"Failed to read/parse input data: {e}")
        sys.exit(1)

    logger.info(f"Successfully consolidated dataset. Total Rows: {len(df):,}")

    # Set project absolute paths
    workspace_dir = Path(__file__).resolve().parent
    pipeline_dir = workspace_dir / 'market_data_pipeline'
    sys.path.insert(0, str(pipeline_dir))

    from converters.resampler import MarketDataResampler
    from metadata.metadata_generator import generate_metadata, generate_bars_metadata
    from cleaner.cleaner import MarketDataCleaner

    # Ensure index is standardized
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
    df = df.sort_index()

    # Drop duplicates
    dups = df.index.duplicated().sum()
    if dups > 0:
        logger.info(f"Dropping {dups:,} duplicate timestamps...")
        df = df[~df.index.duplicated(keep='first')]

    # Fill NaNs or drop them
    nans = df.isna().any(axis=1).sum()
    if nans > 0:
        logger.info(f"Dropping {nans:,} records with NaN values...")
        df = df.dropna()

    # 2. Output directory mapping
    output_dir = pipeline_dir / 'output'
    metadata_dir = pipeline_dir / 'metadata'
    
    # Save Symbol Metadata (symbol_info.json) if it doesn't exist
    sym_info_dir = output_dir / SYMBOL
    sym_info_dir.mkdir(parents=True, exist_ok=True)
    sym_meta_file = sym_info_dir / "symbol_info.json"
    
    if not sym_meta_file.exists():
        metadata_content = {
            "symbol": SYMBOL,
            "asset_type": "forex",
            "base_currency": SYMBOL[:3],
            "quote_currency": SYMBOL[3:],
            "pip_value": 0.0001,
            "lot_size": 100000
        }
        with open(sym_meta_file, 'w') as f:
            json.dump(metadata_content, f, indent=4)
        logger.info(f"Created symbol metadata info at {sym_meta_file}")

    # Save to corresponding Parquet directory
    if data_type == 'ticks':
        tick_dir = output_dir / SYMBOL / 'ticks'
        tick_dir.mkdir(parents=True, exist_ok=True)
        tick_file = tick_dir / f"{YEAR}.parquet"
        
        logger.info(f"Writing raw tick data to Parquet: {tick_file}")
        df.to_parquet(tick_file)
        
        # Generate Metadata for Ticks
        logger.info("Generating tick index metadata...")
        generate_metadata(tick_file, metadata_dir)
        
        # Resample to all bar frequencies (1m, 5m, 15m, 1h, 4h, 1d)
        logger.info("Triggering Local Multi-Timeframe Resampler...")
        resampler = MarketDataResampler(tick_file)
        resampled_files = resampler.resample_all_timeframes(output_dir)
        
        # Generate Metadata for all resampled bar files
        for tf, f_path in resampled_files.items():
            generate_bars_metadata(f_path, metadata_dir, tf)
            
    else:  # if imported pre-resampled bar data (e.g. 1min bar bulk exports)
        logger.info("Formatting imported bar data...")
        # If it is 1-minute bars, we store it in standard 1min folder
        bar_dir = output_dir / SYMBOL / 'bars' / '1min'
        bar_dir.mkdir(parents=True, exist_ok=True)
        bar_file = bar_dir / f"{YEAR}.parquet"
        
        # Format Open/High/Low/Close
        df_bars = pd.DataFrame(index=df.index)
        df_bars['bid_open'] = df['open']
        df_bars['bid_high'] = df['high']
        df_bars['bid_low'] = df['low']
        df_bars['bid_close'] = df['close']
        df_bars['ask_open'] = df['open']
        df_bars['ask_high'] = df['high']
        df_bars['ask_low'] = df['low']
        df_bars['ask_close'] = df['close']
        df_bars['volume'] = df['volume']
        
        logger.info(f"Writing 1min bar data to Parquet: {bar_file}")
        df_bars.to_parquet(bar_file)
        
        # Generate Metadata for 1-minute bars
        generate_bars_metadata(bar_file, metadata_dir, '1min')
        
        # We can also resample higher timeframes from the 1min bars!
        logger.info("Triggering Local Multi-Timeframe Resampler from 1-min bars...")
        # Mock class for bar-to-bar resampling
        # (Simply call resampling directly using pandas since we already have bars)
        for tf in ['5min', '15min', '1h', '4h', '1d']:
            logger.info(f"Resampling from 1min to {tf}...")
            agg_rules = {
                'bid_open': 'first', 'bid_high': 'max', 'bid_low': 'min', 'bid_close': 'last',
                'ask_open': 'first', 'ask_high': 'max', 'ask_low': 'min', 'ask_close': 'last',
                'volume': 'sum'
            }
            resdf = df_bars.resample(tf).agg(agg_rules).dropna()
            resdf_file = output_dir / SYMBOL / 'bars' / tf / f"{YEAR}.parquet"
            (output_dir / SYMBOL / 'bars' / tf).mkdir(parents=True, exist_ok=True)
            resdf.to_parquet(resdf_file)
            generate_bars_metadata(resdf_file, metadata_dir, tf)

    logger.info("=" * 65)
    logger.info("🎉 BULK IMPORT COMPLETED SUCCESSFULLY")
    logger.info("=" * 65)
    logger.info(f"Imported Symbol: {SYMBOL}")
    logger.info(f"Imported Year:   {YEAR}")
    logger.info(f"All timeframes (1min, 5min, 15min, 1h, 4h, 1d) are fully active.")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()
