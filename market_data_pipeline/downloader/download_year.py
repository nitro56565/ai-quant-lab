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

def is_trading_hour(symbol: str, dt: datetime) -> bool:
    """
    Check if the given datetime is an expected trading hour for the symbol.
    Forex markets close Friday ~22:00 UTC to Sunday ~22:00 UTC.
    Gold (XAUUSD) additionally closes daily from 22:00 to 23:00 UTC for maintenance.
    """
    weekday = dt.weekday() # 0 = Monday, 6 = Sunday
    hour = dt.hour

    # Friday after 22:00 UTC -> Closed
    if weekday == 4 and hour >= 22:
        return False
    # Saturday -> Closed all day
    if weekday == 5:
        return False
    # Sunday before 22:00 UTC -> Closed
    if weekday == 6 and hour < 22:
        return False

    # XAUUSD Daily Maintenance Window: 22:00 to 23:00 UTC
    if "XAU" in symbol.upper() and hour == 22:
        return False

    return True

def download_year(symbol, year, download_dir="downloads", max_workers=3):
    """
    Download hourly BI5 files for a symbol for expected trading hours in the year.
    Features 2-pass failure retry queue (failed_hours.json) and trading calendar filtering.
    """
    import json
    import time
    from pathlib import Path

    symbol_dir = Path(download_dir) / symbol / str(year)
    symbol_dir.mkdir(parents=True, exist_ok=True)
    failed_queue_path = symbol_dir / "failed_hours.json"

    client = TickVaultClient()

    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)

    tasks = []
    current = start_date
    while current <= end_date:
        if is_trading_hour(symbol, current):
            month = current.month
            day = current.day
            hour = current.hour
            file_path = symbol_dir / f"{year}-{month:02d}-{day:02d}_{hour:02d}.bi5"
            tasks.append((month, day, hour, file_path))
        current += timedelta(hours=1)

    total_hours = len(tasks)
    logger.info(f"Starting Trading-Calendar-Filtered download for {symbol} {year}. Active trading hours: {total_hours} (Skipped ~{8760 - total_hours} non-trading closure hours)")

    downloaded_count = 0
    skipped_count = 0
    failed_tasks = []

    # PASS 1: Main Download Pass
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(_download_hour, client, symbol, year, month, day, hour, file_path): (month, day, hour, file_path)
            for month, day, hour, file_path in tasks
        }

        for index, future in enumerate(as_completed(future_to_task), 1):
            task_info = future_to_task[future]
            month, day, hour, file_path = task_info
            try:
                status, info = future.result()
                if status == 'downloaded' or status == 'empty':
                    downloaded_count += 1
                elif status in ('skipped_data', 'skipped_empty'):
                    skipped_count += 1
                else:
                    failed_tasks.append({"year": year, "month": month, "day": day, "hour": hour, "file": str(file_path)})
            except Exception as e:
                failed_tasks.append({"year": year, "month": month, "day": day, "hour": hour, "file": str(file_path)})
                logger.error(f"Pass 1 failure for {file_path.name}: {e}")

            if index % 500 == 0 or index == total_hours:
                logger.info(f"Pass 1 Progress: {index}/{total_hours} (Active: {downloaded_count}, Skipped: {skipped_count}, Failed: {len(failed_tasks)})")

    # PASS 2: Retry Failed Hours Queue
    if failed_tasks:
        logger.warning(f"Pass 1 complete with {len(failed_tasks)} failed hours. Pausing 5s for throttling recovery before Pass 2 Retry Queue...")
        time.sleep(5.0)

        # Save failed queue to JSON for auditability
        with open(failed_queue_path, 'w') as f:
            json.dump(failed_tasks, f, indent=2)

        pass2_resolved = 0
        still_failed = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_failed = {
                executor.submit(_download_hour, client, symbol, year, f_info['month'], f_info['day'], f_info['hour'], Path(f_info['file'])): f_info
                for f_info in failed_tasks
            }
            for future in as_completed(future_to_failed):
                f_info = future_to_failed[future]
                try:
                    status, _ = future.result()
                    if status in ('downloaded', 'empty', 'skipped_data', 'skipped_empty'):
                        pass2_resolved += 1
                        downloaded_count += 1
                    else:
                        still_failed.append(f_info)
                except Exception as e:
                    still_failed.append(f_info)

        logger.info(f"Pass 2 Complete: Resolved {pass2_resolved}/{len(failed_tasks)} failed hours. Unresolved remaining: {len(still_failed)}")
        with open(failed_queue_path, 'w') as f:
            json.dump(still_failed, f, indent=2)

    logger.info(f"Download year complete for {symbol} {year}. Total Active Handled: {downloaded_count}, Skipped: {skipped_count}")
    return str(symbol_dir)



