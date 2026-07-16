#!/usr/bin/env python3
"""
HistData Automated Downloader & Ingestion Pipeline
===================================================
Automates the complete workflow:
1. Connects to HistData.com and extracts CSRF tokens.
2. Downloads all 12 monthly ZIP archives (Generic ASCII Tick data) for a selected year.
3. Stores them in the root downloads/ folder structure.
4. Executes the bulk parser and resampler to compile ticks & generate all timeframe bars.
5. Deletes the raw ZIP files to clean up disk space once ingestion succeeds.

To run:
    python3 download_and_process.py
"""

import os
import sys
import time
import shutil
import logging
import subprocess
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AutoPipeline")

# =====================================================================
# ⚙️ CONFIGURATION SETTINGS (Edit these to target different years/pairs)
# =====================================================================
SYMBOL = "EURUSD"                # Currency pair (e.g. "EURUSD", "GBPUSD")
YEARS = [2022, 2023, 2024, 2025, 2026] # List of years to download and ingest
# =====================================================================


def install_dependencies():
    """Ensure BeautifulSoup4 and Requests are installed."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.info("Installing missing dependencies (requests, beautifulsoup4)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
        logger.info("Dependencies installed successfully.")


def download_month_data(symbol, year, month, dest_dir):
    """Download single month's tick data zip from HistData.com."""
    import requests
    from bs4 import BeautifulSoup
    
    url = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/{symbol.lower()}/{year}/{month}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    logger.info(f"Retrieving download token from: {url}")
    r = requests.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        raise Exception(f"Failed to load download page: HTTP {r.status_code}")
        
    # Extract token and other hidden form parameters
    soup = BeautifulSoup(r.text, 'html.parser')
    form = soup.find('form', {'id': 'file_download'})
    if not form:
        form = soup.find('form')
        
    if not form:
        raise Exception("Could not find download form on page.")
        
    payload = {}
    for inp in form.find_all('input'):
        if inp.get('name'):
            payload[inp.get('name')] = inp.get('value', '')
            
    if 'tk' not in payload or not payload['tk']:
        raise Exception("Security token (tk) not found in form input fields.")
        
    post_url = "https://www.histdata.com/get.php"
    post_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': url,
        'Origin': 'https://www.histdata.com',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    
    logger.info(f"Sending POST request to get.php for month {month}...")
    res = requests.post(post_url, data=payload, headers=post_headers, stream=True, timeout=30)
    if res.status_code != 200:
        raise Exception(f"POST request failed: HTTP {res.status_code}")
        
    # Find filename from headers or default to standard format
    disp = res.headers.get('Content-Disposition', '')
    filename = f"HISTDATA_COM_ASCII_{symbol.upper()}_T{year}{month:02d}.zip"
    if 'filename=' in disp:
        filename = disp.split('filename=')[-1].replace('"', '').strip()
        
    dest_path = dest_dir / filename
    
    # Save file contents
    logger.info(f"Saving downloaded archive to: {dest_path.name}")
    with open(dest_path, 'wb') as f:
        for chunk in res.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)
                
    return dest_path


def main():
    install_dependencies()
    
    logger.info("=" * 65)
    logger.info("🤖 HISTDATA BATCH DOWNLOADER & INGESTION PIPELINE")
    logger.info("=" * 65)
    logger.info(f"Target Symbol: {SYMBOL}")
    logger.info(f"Target Years:  {YEARS}")
    print("-" * 65)

    workspace_dir = Path(__file__).resolve().parent

    for year in YEARS:
        logger.info("\n" + "=" * 65)
        logger.info(f"📅 STARTING INGESTION FOR YEAR: {year}")
        logger.info("=" * 65)
        
        downloads_dir = workspace_dir / "downloads" / SYMBOL / str(year)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Storage Dir:   {downloads_dir}")
        
        downloaded_files = []
        
        # In 2026, download up to June (Month 6). For other years, download all 12 months.
        max_month = 6 if year == 2026 else 12
        
        # 1. Download months in sequence
        for m in range(1, max_month + 1):
            logger.info(f"\n🌍 Step 1/3: Downloading month {m:02d}/{max_month} for {year} from HistData...")
            retries = 3
            success = False
            for attempt in range(retries):
                try:
                    file_path = download_month_data(SYMBOL, year, m, downloads_dir)
                    downloaded_files.append(file_path)
                    success = True
                    logger.info(f"  ✅ Month {m:02d} downloaded successfully.")
                    break
                except Exception as e:
                    logger.warning(f"  ⚠️ Attempt {attempt+1}/{retries} failed for Month {m:02d}: {e}")
                    if attempt < retries - 1:
                        time.sleep(5) # Cooldown before retry
                    else:
                        logger.error(f"  ❌ Failed to download month {m:02d} after {retries} attempts.")
                        sys.exit(1)
            
            # Sane delay between months to prevent rate limits
            if m < max_month:
                time.sleep(3)

        logger.info("\n" + "=" * 65)
        logger.info(f"⚡ Step 2/3: Triggering Ingestion Parser & Resampler for {year}...")
        logger.info("=" * 65)
        
        # 2. Modify import settings and execute import_bulk_data.py
        import import_bulk_data
        
        # Override configuration variables dynamically
        import_bulk_data.INPUT_FILE_PATH = str(downloads_dir)
        import_bulk_data.SYMBOL = SYMBOL
        import_bulk_data.YEAR = year
        import_bulk_data.FORMAT_TYPE = "histdata_tick"
        
        try:
            import_bulk_data.main()
            logger.info(f"  ✅ Ingestion and bar resampling finished successfully for {year}.")
        except Exception as e:
            logger.error(f"  ❌ Ingestion failed for {year}: {e}")
            sys.exit(1)

        logger.info("\n" + "=" * 65)
        logger.info(f"🧹 Step 3/3: Cleaning up downloaded raw zip files for {year}...")
        logger.info("=" * 65)
        
        # 3. Delete downloaded zip archives to save space
        deleted_count = 0
        for f in downloaded_files:
            if f.exists():
                f.unlink()
                deleted_count += 1
                logger.info(f"  Deleted: {f.name}")
                
        # Clean up empty directories
        if downloads_dir.exists() and not any(downloads_dir.iterdir()):
            downloads_dir.rmdir()
            
        logger.info(f"  ✅ Cleanup complete. Deleted {deleted_count} ZIP files for {year}.")
        
    logger.info("\n" + "=" * 65)
    logger.info("🎉 ALL SELECTED YEARS INGESTED SUCCESSFULLY!")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()
