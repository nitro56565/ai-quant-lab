#!/usr/bin/env python3
"""
Market Data Extraction Pipeline Orchestrator
===========================================
Modify the CONFIGURATION SETTINGS block below to select symbols, years, 
and timeframes to download and resample, then run this file in your terminal:
    python3 extract_data.py
"""

import sys
import json
from pathlib import Path

# =====================================================================
# ⚙️ DATA PIPELINE CONFIGURATION SETTINGS (Edit these to extract data)
# =====================================================================
SYMBOL = "EURUSD"                # Forex pair to download (e.g., "EURUSD", "GBPUSD")
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]                   # List of years to process (e.g. [2018, 2019])

# Timeframes to resample/generate.
# Options: '1min', '5min', '15min', '1h', '4h', '1d'
TIMEFRAMES = ['1min', '5min', '15min', '1h', '4h', '1d']
# =====================================================================


def main():
    print("=" * 65)
    print("📥 HISTORICAL MARKET DATA EXTRACTION PIPELINE")
    print("=" * 65)
    print(f"Target Symbol:  {SYMBOL}")
    print(f"Target Years:   {', '.join(map(str, YEARS))}")
    print(f"Timeframes:     {', '.join(TIMEFRAMES)}")
    print("-" * 65)

    base_dir = Path(__file__).resolve().parent
    pipeline_dir = base_dir / 'market_data_pipeline'

    # Add pipeline directory to sys.path to resolve internal pipeline imports
    sys.path.insert(0, str(pipeline_dir))

    try:
        import main as pipeline_main
        from converters.resampler import MarketDataResampler
    except ImportError as e:
        print(f"❌ Import Error: Failed to import data pipeline components. Detail: {e}")
        sys.exit(1)

    # 1. Dynamically configure resampling timeframes
    MarketDataResampler.TIMEFRAMES = TIMEFRAMES

    # 2. Load configuration
    config_path = pipeline_dir / "config" / "tickvault_config.json"
    if not config_path.exists():
        print(f"❌ Error: Config file not found at {config_path}")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        # Update config paths to be absolute relative to workspace root
        config['download_dir'] = str(pipeline_dir / config.get('download_dir', 'downloads'))
        config['output_dir'] = str(pipeline_dir / config.get('output_dir', 'output'))
        config['metadata_dir'] = str(pipeline_dir / config.get('metadata_dir', 'metadata'))
    except Exception as e:
        print(f"❌ Error loading pipeline configuration: {e}")
        sys.exit(1)

    # Setup pipeline logging
    pipeline_main.setup_logging(log_dir=str(pipeline_dir / "logs"))

    # 3. Run extraction loop
    print("⏳ Starting download and extraction pipeline runs...")
    print("   (Data will be downloaded from Dukascopy, validated, cleaned, and resampled)\n")

    any_success = False
    for year in YEARS:
        print(f"▶️ Processing year {year}...")
        try:
            success = pipeline_main.run_pipeline(SYMBOL, year, config)
            if success:
                print(f"  ✅ Completed processing {SYMBOL} for {year}.\n")
                any_success = True
            else:
                print(f"  ❌ Pipeline execution failed for {SYMBOL} {year}.\n")
        except Exception as e:
            print(f"  ❌ Error executing pipeline for {SYMBOL} {year}: {e}\n")

    if any_success:
        print("=" * 65)
        print("🎉 DATA EXTRACTION PIPELINE COMPLETED")
        print("=" * 65)
        print(f"Output Bar Data:  {config['output_dir']}/{SYMBOL}/bars/")
        print(f"Output Metadata:  {config['metadata_dir']}/{SYMBOL}/")
        print("=" * 65)
    else:
        print("❌ Data extraction failed for all years.")
        sys.exit(1)


if __name__ == "__main__":
    main()
