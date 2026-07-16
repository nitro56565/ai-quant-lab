"""
Main orchestration script for the market data pipeline.
Runs all 8 steps in sequence to download, process, and store market data.
"""

import json
import logging
import sys
from pathlib import Path

from downloader.download_year import download_year
from downloader.cleanup import delete_raw_files, verify_parquet_file
from parser.reader import read_year
from validator.validator import MarketDataValidator
from cleaner.cleaner import MarketDataCleaner
from converters.parquet_writer import ParquetWriter
from converters.resampler import MarketDataResampler
from metadata.metadata_generator import generate_metadata, generate_bars_metadata

# Setup logging
def setup_logging(log_dir="logs"):
    """Setup logging configuration."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path / 'pipeline.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def load_config(config_path="config/tickvault_config.json"):
    """Load TickVault configuration."""
    with open(config_path, 'r') as f:
        return json.load(f)

def run_pipeline(symbol, year, config):
    """
    Run the complete market data pipeline for a symbol and year.
    
    Args:
        symbol: Trading symbol (e.g., "EURUSD")
        year: Year to process (e.g., 2018)
        config: Configuration dictionary with directory paths
    """
    logger = logging.getLogger(__name__)
    
    # Configuration from config file
    download_dir = config.get('download_dir', 'downloads')
    output_dir = config.get('output_dir', 'output')
    metadata_dir = config.get('metadata_dir', 'metadata')
    
    logger.info(f"=" * 60)
    logger.info(f"Starting pipeline for {symbol} {year}")
    logger.info(f"=" * 60)
    
    # Step 1: Download hourly BI5 files from Dukascopy (no authentication required)
    logger.info("Step 1: Downloading hourly BI5 files from Dukascopy...")
    try:
        download_path = download_year(symbol, year, download_dir)
        logger.info(f"Download completed: {download_path}")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False
    
    # Initialize components
    validator = MarketDataValidator()
    cleaner = MarketDataCleaner()
    writer = ParquetWriter(output_dir)
    
    # Step 2-5: Read, validate, clean, and write data
    logger.info("Step 2-5: Reading, validating, cleaning, and processing data...")
    total_rows = 0
    chunk_count = 0
    processed_dfs = []
    
    try:
        import pandas as pd
        for hour_df in read_year(symbol, year, download_dir):
            chunk_count += 1
            
            # Step 3: Validate
            validation_result = validator.validate(hour_df)
            if not validation_result['is_valid']:
                logger.warning(f"Validation issues in chunk {chunk_count}: {validation_result['issues']}")
                # Continue processing despite validation issues
            
            # Step 4: Clean
            cleaned_df = cleaner.clean(hour_df)
            processed_dfs.append(cleaned_df)
            
            total_rows += len(cleaned_df)
            
            if chunk_count % 100 == 0:
                logger.info(f"Processed {chunk_count} chunks, {total_rows} rows so far")
        
        logger.info(f"Completed processing {chunk_count} chunks, {total_rows} total rows")
        
        # Step 5: Write to parquet (bulk write)
        if processed_dfs:
            logger.info("Step 5: Concatenating and writing all data to Parquet...")
            combined_df = pd.concat(processed_dfs, ignore_index=True)
            writer.write_ticks(combined_df, symbol, year)
        else:
            logger.error("No data processed to write")
            return False
        
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return False

    
    # Verify parquet file
    tick_file_path = Path(output_dir) / symbol / "ticks" / f"{year}.parquet"
    if not verify_parquet_file(tick_file_path):
        logger.error("Parquet file verification failed")
        return False
    
    # Step 7: Generate metadata for tick data
    logger.info("Step 7: Generating metadata for tick data...")
    try:
        generate_metadata(tick_file_path, metadata_dir)
    except Exception as e:
        logger.error(f"Metadata generation failed: {e}")
        return False
    
    # Step 6: Resample to all timeframes
    logger.info("Step 6: Resampling to multiple timeframes...")
    try:
        resampler = MarketDataResampler(tick_file_path)
        resampled_files = resampler.resample_all_timeframes(output_dir)
        
        # Generate metadata for each resampled file
        for timeframe, file_path in resampled_files.items():
            generate_bars_metadata(file_path, metadata_dir, timeframe)
            logger.info(f"Generated metadata for {timeframe}")
            
    except Exception as e:
        logger.error(f"Resampling failed: {e}")
        return False
    
    # Step 8: Delete raw files
    logger.info("Step 8: Deleting raw BI5 files...")
    try:
        deleted_count = delete_raw_files(symbol, year, download_dir)
        logger.info(f"Deleted {deleted_count} raw files")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return False
    
    logger.info(f"=" * 60)
    logger.info(f"Pipeline completed successfully for {symbol} {year}")
    logger.info(f"=" * 60)
    
    return True

def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Example: Process EURUSD for 2018
    # You can modify these values or make them command-line arguments
    symbol = "EURUSD"
    year = 2018
    
    # Run pipeline
    success = run_pipeline(symbol, year, config)
    
    if success:
        logger.info("Pipeline execution completed successfully")
        sys.exit(0)
    else:
        logger.error("Pipeline execution failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
