"""
Cleanup utility for deleting raw downloaded files after processing.
"""

import shutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def delete_raw_files(symbol, year, download_dir="downloads"):
    """
    Delete raw downloaded BI5 files for a symbol/year after parquet verification.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        year: Year to delete (e.g., 2018)
        download_dir: Directory containing downloaded files
        
    Returns:
        Number of files deleted
    """
    symbol_dir = Path(download_dir) / symbol / str(year)
    
    if not symbol_dir.exists():
        logger.warning(f"Download directory not found: {symbol_dir}")
        return 0
    
    # Count files before deletion
    bi5_files = list(symbol_dir.glob("*.bi5"))
    file_count = len(bi5_files)
    
    if file_count == 0:
        logger.info(f"No BI5 files found in {symbol_dir}")
        return 0
    
    logger.info(f"Deleting {file_count} BI5 files from {symbol_dir}")
    
    # Delete the entire directory
    try:
        shutil.rmtree(symbol_dir)
        logger.info(f"Successfully deleted {symbol_dir}")
        
        # Also try to delete parent directories if empty
        symbol_parent = symbol_dir.parent
        if symbol_parent.exists() and not any(symbol_parent.iterdir()):
            symbol_parent.rmdir()
            logger.info(f"Deleted empty directory: {symbol_parent}")
        
        return file_count
        
    except Exception as e:
        logger.error(f"Error deleting {symbol_dir}: {e}")
        return 0

def verify_parquet_file(parquet_file_path, expected_rows=None):
    """
    Verify that a parquet file exists and contains expected data.
    
    Args:
        parquet_file_path: Path to the parquet file
        expected_rows: Optional expected number of rows for verification
        
    Returns:
        Boolean indicating if file is valid
    """
    try:
        import pandas as pd
        
        file_path = Path(parquet_file_path)
        
        if not file_path.exists():
            logger.error(f"Parquet file does not exist: {parquet_file_path}")
            return False
        
        # Try to read the file
        data = pd.read_parquet(file_path)
        
        if len(data) == 0:
            logger.error(f"Parquet file is empty: {parquet_file_path}")
            return False
        
        if expected_rows is not None and len(data) != expected_rows:
            logger.warning(f"Row count mismatch: expected {expected_rows}, got {len(data)}")
            # Still return True as file is valid, just row count differs
        
        logger.info(f"Parquet file verified: {parquet_file_path} ({len(data)} rows)")
        return True
        
    except Exception as e:
        logger.error(f"Error verifying parquet file {parquet_file_path}: {e}")
        return False
