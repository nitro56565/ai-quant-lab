"""
Parquet writer for converting market data to Parquet format.
"""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ParquetWriter:
    """
    Writer for converting market data to Parquet format with append support.
    """
    
    def __init__(self, output_path):
        """
        Initialize the Parquet writer.
        
        Args:
            output_path: Path where Parquet files will be written
        """
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
    
    def append(self, data, symbol, year):
        """
        Append market data to existing Parquet file.
        Creates file if it doesn't exist.
        
        Args:
            data: Market data to append (DataFrame)
            symbol: Trading symbol (e.g., "EURUSD")
            year: Year (e.g., 2018)
            
        Returns:
            Path to the Parquet file
        """
        # Create directory structure: output/symbol/ticks/
        ticks_dir = self.output_path / symbol / "ticks"
        ticks_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = ticks_dir / f"{year}.parquet"
        
        if file_path.exists():
            # Read existing data and append
            existing_data = pd.read_parquet(file_path)
            combined_data = pd.concat([existing_data, data], ignore_index=True)
            combined_data.to_parquet(file_path)
            logger.info(f"Appended {len(data)} rows to {file_path}")
        else:
            # Create new file
            data.to_parquet(file_path)
            logger.info(f"Created new file {file_path} with {len(data)} rows")
        
        return str(file_path)
    
    def write_ticks(self, data, symbol, year):
        """
        Write complete year's market data to Parquet format (overwrites existing).
        
        Args:
            data: Market data to write (DataFrame)
            symbol: Trading symbol (e.g., "EURUSD")
            year: Year (e.g., 2018)
            
        Returns:
            Path to the written Parquet file
        """
        ticks_dir = self.output_path / symbol / "ticks"
        ticks_dir.mkdir(parents=True, exist_ok=True)
        file_path = ticks_dir / f"{year}.parquet"
        data.to_parquet(file_path)
        logger.info(f"Successfully wrote {len(data)} rows to {file_path}")
        return str(file_path)
    
    def write(self, data, filename):
        """
        Write market data to Parquet format (overwrites existing).
        
        Args:
            data: Market data to write (DataFrame)
            filename: Name of the output file
            
        Returns:
            Path to the written Parquet file
        """
        file_path = self.output_path / f"{filename}.parquet"
        data.to_parquet(file_path)
        return str(file_path)
    
    def write_partitioned(self, data, partition_columns):
        """
        Write market data to partitioned Parquet format.
        
        Args:
            data: Market data to write (DataFrame)
            partition_columns: Columns to partition by
            
        Returns:
            Path to the written Parquet directory
        """
        data.to_parquet(self.output_path, partition_cols=partition_columns)
        return str(self.output_path)

