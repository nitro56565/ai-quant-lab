import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'market_data_pipeline')))

import argparse
import logging
from datetime import datetime
from market_data_pipeline.dukascopy_provider import DukascopyProvider

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DukascopyPipelineCLI")

def main():
    parser = argparse.ArgumentParser(description="Institutional Dukascopy Forex Data Collection & Processing Pipeline")
    parser.add_argument("--symbol", type=str, default="XAUUSD", help="Trading symbol (e.g. XAUUSD, EURUSD, GBPUSD)")
    parser.add_argument("--year", type=int, default=2018, help="Single year to download (e.g. 2018)")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--timeframes", type=str, default="1m,5m,15m,30m,1h,4h,1d", help="Comma-separated timeframes")
    parser.add_argument("--workers", type=int, default=10, help="Number of parallel worker threads")


    parser.add_argument("--version", type=str, default="v1", help="Dataset version tag")

    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    year = args.year
    tf_list = [tf.strip().lower() for tf in args.timeframes.split(',')]

    start_date = args.start if args.start else f"{year}-01-01"
    end_date = args.end if args.end else f"{year}-12-31"

    print("=================================================================================")
    print(f"  🤖 DUKASCOPY FOREX DATA PIPELINE: {symbol} ({start_date} to {end_date})")
    print(f"  Version: {args.version} | Workers: {args.workers} | Timeframes: {tf_list}")
    print("=================================================================================\n")

    provider = DukascopyProvider(version=args.version)

    # 1. Step 1: Parallel Download Raw Ticks
    raw_path = provider.download(symbol=symbol, start_date=start_date, end_date=end_date, workers=args.workers)
    print(f"✅ Step 1 Complete: Raw tick files downloaded to {raw_path}")

    # 2. Step 2: Process, Validate, Resample, Export & Save Metadata
    success = provider.process_and_export(symbol=symbol, year=year, timeframes=tf_list)
    
    if success:
        print("\n=================================================================================")
        print(f"  🏆 DUKASCOPY PIPELINE SUCCESSFUL FOR {symbol} {year}")
        print("=================================================================================\n")
    else:
        print(f"\n❌ Pipeline encountered issues for {symbol} {year}\n")

if __name__ == '__main__':
    main()
