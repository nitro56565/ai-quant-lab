"""
Download market data for a specific year.
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from .tickvault_client import TickVaultClient

logger = logging.getLogger(__name__)

def _download_hour(client, symbol, year, month, day, hour, file_path):
    """Helper function to download a single hour's data with backoff retries."""
    import time
    import random
    
    if file_path.exists():
        if file_path.stat().st_size > 0:
            return 'skipped_data', 0
        else:
            return 'skipped_empty', 0
            
    max_retries = 4
    backoff = 1.0
    
    for attempt in range(max_retries):
        try:
            bi5_content = client.download_hourly_bi5(symbol, year, month, day, hour)
            
            # Dukascopy returns 200 OK with empty content for weekends/holidays
            if not bi5_content:
                with open(file_path, 'wb') as f:
                    f.write(b'')
                return 'empty', 0
                
            with open(file_path, 'wb') as f:
                f.write(bi5_content)
            return 'downloaded', len(bi5_content)
            
        except Exception as e:
            err_str = str(e)
            # A 404 error means no data (usually weekend or holiday)
            if '404' in err_str:
                with open(file_path, 'wb') as f:
                    f.write(b'')
                return 'empty', 0
                
            # For network issues/503/connection resets, wait and retry
            if attempt < max_retries - 1:
                sleep_time = backoff * (1.5 ** attempt) + random.uniform(0.1, 0.4)
                logger.debug(f"Download warning for {file_path.name} (attempt {attempt+1}/{max_retries}): {e}. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
            else:
                logger.error(f"Failed to download {file_path.name} after {max_retries} attempts: {e}")
                return 'failed', str(e)

def download_year(symbol, year, download_dir="downloads"):
    """
    Download hourly BI5 files for a symbol for the entire year from Dukascopy public feed.
    Downloads are executed concurrently using thread pool.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        year: Year to download (e.g., 2018)
        download_dir: Directory to save downloaded files
        
    Returns:
        Path to downloaded data directory
    """
    # Create download directory structure
    symbol_dir = Path(download_dir) / symbol / str(year)
    symbol_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize TickVault client (no authentication required)
    client = TickVaultClient()
    
    # Calculate total hours in the year
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    tasks = []
    current = start_date
    while current <= end_date:
        month = current.month
        day = current.day
        hour = current.hour
        
        file_path = symbol_dir / f"{year}-{month:02d}-{day:02d}_{hour:02d}.bi5"
        tasks.append((month, day, hour, file_path))
        current += timedelta(hours=1)
        
    total_hours = len(tasks)
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0
    
    logger.info(f"Starting concurrent download for {symbol} {year}. Total hours: {total_hours}")
    
    # Parallel execution using ThreadPoolExecutor
    max_workers = 8
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(_download_hour, client, symbol, year, month, day, hour, file_path): (month, day, hour, file_path)
            for month, day, hour, file_path in tasks
        }
        
        for index, future in enumerate(as_completed(future_to_task), 1):
            month, day, hour, file_path = future_to_task[future]
            try:
                status, info = future.result()
                if status == 'downloaded':
                    downloaded_count += 1
                elif status in ('skipped_data', 'skipped_empty'):
                    skipped_count += 1
                elif status == 'empty':
                    downloaded_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Error handling task for {file_path.name}: {e}")
                
            if index % 500 == 0 or index == total_hours:
                logger.info(f"Download Progress: {index}/{total_hours} (Downloaded/Parsed: {downloaded_count}, Skipped: {skipped_count}, Failed: {failed_count})")
                
    logger.info(f"Download complete. Processed successfully: {downloaded_count}, Skipped: {skipped_count}, Failed: {failed_count}")
    
    return str(symbol_dir)


