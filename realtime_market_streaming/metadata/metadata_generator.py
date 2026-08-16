"""
Metadata generator for market data files.
"""

import json
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def generate_metadata(parquet_file_path, output_dir):
    """
    Generate metadata JSON file for a parquet data file.
    
    Args:
        parquet_file_path: Path to the parquet file
        output_dir: Directory to save metadata file
        
    Returns:
        Path to the generated metadata file
    """
    # Load the parquet file to get metadata
    data = pd.read_parquet(parquet_file_path)
    
    # Extract symbol and year from file path
    parts = Path(parquet_file_path).parts
    symbol = parts[-4] if 'bars' in parts else parts[-3]
    year = int(Path(parquet_file_path).stem)
    
    # Get date range
    if 'timestamp' in data.columns:
        start_date = data['timestamp'].min().strftime('%Y-%m-%d')
        end_date = data['timestamp'].max().strftime('%Y-%m-%d')
    else:
        # If timestamp is index
        start_date = data.index.min().strftime('%Y-%m-%d')
        end_date = data.index.max().strftime('%Y-%m-%d')
    
    # Create metadata dictionary
    metadata = {
        "symbol": symbol,
        "year": year,
        "rows": len(data),
        "start": start_date,
        "end": end_date
    }
    
    # Create metadata directory
    metadata_dir = Path(output_dir) / symbol
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata file
    metadata_path = metadata_dir / f"{year}_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Generated metadata: {metadata_path}")
    logger.info(f"  Symbol: {symbol}, Year: {year}, Rows: {metadata['rows']}")
    
    return str(metadata_path)

def generate_bars_metadata(parquet_file_path, output_dir, timeframe):
    """
    Generate metadata for resampled bar data.
    
    Args:
        parquet_file_path: Path to the parquet file
        output_dir: Directory to save metadata file
        timeframe: Timeframe of the bars (e.g., '1min', '5min', '1H')
        
    Returns:
        Path to the generated metadata file
    """
    # Load the parquet file to get metadata
    data = pd.read_parquet(parquet_file_path)
    
    # Extract symbol and year from file path
    parts = Path(parquet_file_path).parts
    symbol = parts[-4]
    year = int(Path(parquet_file_path).stem)
    
    # Get date range
    if hasattr(data.index, 'min'):
        start_date = data.index.min().strftime('%Y-%m-%d')
        end_date = data.index.max().strftime('%Y-%m-%d')
    else:
        start_date = "unknown"
        end_date = "unknown"
    
    # Create metadata dictionary
    metadata = {
        "symbol": symbol,
        "year": year,
        "timeframe": timeframe,
        "rows": len(data),
        "start": start_date,
        "end": end_date
    }
    
    # Create metadata directory
    metadata_dir = Path(output_dir) / symbol / "bars" / timeframe
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata file
    metadata_path = metadata_dir / f"{year}_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Generated bars metadata: {metadata_path}")
    logger.info(f"  Symbol: {symbol}, Year: {year}, Timeframe: {timeframe}, Rows: {metadata['rows']}")
    
    return str(metadata_path)
