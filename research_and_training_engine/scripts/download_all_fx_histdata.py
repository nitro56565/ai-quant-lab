"""
High-Speed Multi-Asset HistData Downloader & Bulk Ingestion Pipeline.
Downloads and ingests 2014-2025 H1 data for GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF
directly into realtime_market_streaming/output and metadata directories for Stage 11 Cross-Validation.
"""

import os, sys, time, shutil, logging, subprocess, json, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("HistDataMultiAsset")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "realtime_market_streaming" / "output"
METADATA_DIR = BASE_DIR / "realtime_market_streaming" / "metadata"
DOWNLOADS_DIR = BASE_DIR / "scripts" / "downloads"

TARGET_SYMBOLS = ["GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]
YEARS = list(range(2014, 2026))

def install_dependencies():
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.info("Installing missing dependencies (requests, beautifulsoup4)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
        logger.info("Dependencies installed successfully.")

def download_month_zip(symbol, year, month, dest_dir):
    import requests
    from bs4 import BeautifulSoup

    url = f"https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/{symbol.lower()}/{year}/{month}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    r = requests.get(url, headers=headers, timeout=25)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code} for {symbol} {year}-{month:02d}")

    soup = BeautifulSoup(r.text, 'html.parser')
    form = soup.find('form', {'id': 'file_download'}) or soup.find('form')
    if not form:
        raise Exception("Could not find download form on page.")

    payload = {}
    for inp in form.find_all('input'):
        if inp.get('name'):
            payload[inp.get('name')] = inp.get('value', '')

    if 'tk' not in payload or not payload['tk']:
        raise Exception("Security token (tk) not found.")

    post_url = "https://www.histdata.com/get.php"
    post_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': url,
        'Origin': 'https://www.histdata.com',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    res = requests.post(post_url, data=payload, headers=post_headers, stream=True, timeout=40)
    if res.status_code != 200:
        raise Exception(f"POST request failed: HTTP {res.status_code}")

    filename = f"HISTDATA_COM_ASCII_{symbol.upper()}_T{year}{month:02d}.zip"
    dest_path = dest_dir / filename

    with open(dest_path, 'wb') as f:
        for chunk in res.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)

    return dest_path

def process_year_symbol(symbol, year):
    sym_dir = DOWNLOADS_DIR / symbol / str(year)
    sym_dir.mkdir(parents=True, exist_ok=True)

    max_month = 6 if year == 2026 else 12
    zip_files = []

    logger.info(f"⬇️ Downloading {symbol} {year} (Months 1-{max_month})...")

    def fetch_m(m):
        for attempt in range(3):
            try:
                zp = download_month_zip(symbol, year, m, sym_dir)
                return zp
            except Exception as e:
                if attempt == 2:
                    logger.warning(f"  Failed {symbol} {year}-{m:02d}: {e}")
                    return None
                time.sleep(2)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch_m, m) for m in range(1, max_month + 1)]
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                zip_files.append(res)

    if not zip_files:
        logger.error(f"❌ No ZIP files downloaded for {symbol} {year}")
        return False

    # Extract & Aggregate into 1H OHLCV Bar Parquet
    all_dfs = []
    for zf in zip_files:
        try:
            with zipfile.ZipFile(zf, 'r') as z:
                csv_files = [f for f in z.namelist() if f.endswith('.csv') or f.endswith('.txt')]
                for cf in csv_files:
                    with z.open(cf) as sample_f:
                        first_line = sample_f.readline().decode('utf-8')
                        sep = ';' if ';' in first_line else ','

                    with z.open(cf) as f:
                        df = pd.read_csv(f, sep=sep, header=None, names=['ts_raw', 'bid', 'ask', 'volume'], dtype={'bid': float, 'ask': float})
                        df['datetime'] = pd.to_datetime(df['ts_raw'].astype(str).str.strip(), format='%Y%m%d %H%M%S%f', errors='coerce')
                        df = df.dropna(subset=['datetime', 'bid', 'ask'])
                        df['mid'] = (df['bid'] + df['ask']) / 2.0
                        df = df.set_index('datetime')

                        # Resample to 1H
                        h1_df = df['mid'].resample('1h').ohlc().dropna()
                        if 'volume' in df.columns:
                            h1_df['volume'] = df['volume'].resample('1h').sum().fillna(0)
                        else:
                            h1_df['volume'] = 1000
                        all_dfs.append(h1_df)
        except Exception as e:
            logger.warning(f"Error parsing zip {zf.name}: {e}")

    if not all_dfs:
        logger.error(f"❌ Failed to parse data for {symbol} {year}")
        return False

    yearly_h1 = pd.concat(all_dfs).sort_index()
    yearly_h1 = yearly_h1[~yearly_h1.index.duplicated(keep='first')]

    # Ensure high >= open/close and low <= open/close
    yearly_h1['high'] = yearly_h1[['open', 'high', 'low', 'close']].max(axis=1)
    yearly_h1['low'] = yearly_h1[['open', 'high', 'low', 'close']].min(axis=1)

    out_bars_dir = DATA_DIR / symbol / "bars" / "1h"
    out_bars_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_bars_dir / f"{year}.parquet"

    yearly_h1.to_parquet(parquet_path)
    logger.info(f"✅ Saved 1H Parquet: {parquet_path} ({len(yearly_h1)} H1 bars)")

    # Write Metadata
    sym_meta_dir = METADATA_DIR / symbol
    sym_meta_dir.mkdir(parents=True, exist_ok=True)

    meta_dict = {
        "symbol": symbol,
        "asset_type": "forex",
        "quote_currency": symbol[3:],
        "base_currency": symbol[:3],
        "pip_size": 0.01 if "JPY" in symbol else 0.0001
    }
    with open(sym_meta_dir / "symbol_info.json", "w") as f:
        json.dump(meta_dict, f, indent=2)

    with open(DATA_DIR / symbol / "symbol_info.json", "w") as f:
        json.dump(meta_dict, f, indent=2)

    # Cleanup Zip Files
    for zf in zip_files:
        if zf.exists():
            zf.unlink()

    return True

def main():
    install_dependencies()
    t0 = time.time()
    logger.info("=================================================================================")
    logger.info("  🚀 HIGH-SPEED MULTI-ASSET HISTDATA DOWNLOADER & INGESTION PIPELINE")
    logger.info("=================================================================================")
    logger.info(f"  • Target Symbols: {TARGET_SYMBOLS}")
    logger.info(f"  • Years Range:    2014 to 2025")
    logger.info("=================================================================================\n")

    for symbol in TARGET_SYMBOLS:
        logger.info(f"\n🌍 INGESTING ASSET: {symbol}")
        logger.info("-" * 60)
        for yr in YEARS:
            process_year_symbol(symbol, yr)

    elapsed = time.time() - t0
    logger.info(f"\n🎉 ALL MULTI-ASSET INGESTION COMPLETE IN {elapsed:.1f}s!")

if __name__ == "__main__":
    main()
