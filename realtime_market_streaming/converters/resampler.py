"""
Resampler for resampling market data to different frequencies.
"""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class MarketDataResampler:
    """
    Resampler for converting tick data to different time frequencies.
    """
    
    TIMEFRAMES = ['1min', '5min', '15min', '1h', '4h', '1d']
    
    def __init__(self, tick_file_path):
        """
        Initialize the resampler with tick data file path.
        
        Args:
            tick_file_path: Path to tick data parquet file
        """
        self.tick_file_path = Path(tick_file_path)
    
    def resample_all_timeframes(self, output_dir):
        """
        Resample tick data to all predefined timeframes and save.
        
        Args:
            output_dir: Base output directory for resampled data
            
        Returns:
            dict mapping timeframe to output file paths
        """
        # Load tick data
        logger.info(f"Loading tick data from {self.tick_file_path}")
        tick_data = pd.read_parquet(self.tick_file_path)
        
        # Ensure timestamp is index for resampling
        if 'timestamp' in tick_data.columns:
            tick_data = tick_data.set_index('timestamp')
        
        results = {}
        
        for timeframe in self.TIMEFRAMES:
            logger.info(f"Resampling to {timeframe}")
            resampled_data = self.resample_to_ohlc(tick_data, timeframe)
            
            # Save to appropriate directory
            output_path = self._save_resampled_data(resampled_data, output_dir, timeframe)
            results[timeframe] = output_path
            logger.info(f"Saved {timeframe} data to {output_path}")
        
        return results
    
    def resample_to_ohlc(self, data, frequency):
        """
        Resample tick data to OHLC format for given frequency.
        
        Args:
            data: Tick data DataFrame with timestamp index
            frequency: Target frequency (e.g., '1min', '5min', '1H', '1D')
            
        Returns:
            Resampled OHLC data
        """
        # Resample bid and ask to OHLC
        bid_ohlc = data['bid'].resample(frequency).ohlc()
        ask_ohlc = data['ask'].resample(frequency).ohlc()
        
        # Sum volume for each period
        volume_sum = data['volume'].resample(frequency).sum()
        
        # Combine into single DataFrame with proper column names
        result = pd.DataFrame({
            'bid_open': bid_ohlc['open'],
            'bid_high': bid_ohlc['high'],
            'bid_low': bid_ohlc['low'],
            'bid_close': bid_ohlc['close'],
            'ask_open': ask_ohlc['open'],
            'ask_high': ask_ohlc['high'],
            'ask_low': ask_ohlc['low'],
            'ask_close': ask_ohlc['close'],
            'volume': volume_sum
        })
        
        # Remove rows with all NaN (empty periods)
        result = result.dropna(how='all')
        
        return result
    
    def _save_resampled_data(self, data, output_dir, timeframe):
        """
        Save resampled data to appropriate directory structure.
        
        Args:
            data: Resampled data DataFrame
            output_dir: Base output directory
            timeframe: Timeframe identifier
            
        Returns:
            Path to saved file
        """
        # Extract symbol and year from tick file path
        # Expected path: .../symbol/ticks/year.parquet
        parts = self.tick_file_path.parts
        symbol = parts[-3]  # symbol directory (e.g. EURUSD from output/EURUSD/ticks/2018.parquet)
        year = self.tick_file_path.stem  # year.parquet -> year
        
        # Create output directory: output_dir/symbol/bars/timeframe/
        bars_dir = Path(output_dir) / symbol / "bars" / timeframe
        bars_dir.mkdir(parents=True, exist_ok=True)
        
        # Save parquet file
        output_path = bars_dir / f"{year}.parquet"
        data.to_parquet(output_path)
        
        return str(output_path)
    
    def resample(self, data, frequency, aggregation='ohlc'):
        """
        Resample data to a different frequency.
        
        Args:
            data: Market data (DataFrame with datetime index)
            frequency: Target frequency (e.g., '1min', '5min', '1H', '1D')
            aggregation: Aggregation method ('ohlc', 'mean', 'sum', etc.)
            
        Returns:
            Resampled market data
        """
        if aggregation == 'ohlc':
            return self.resample_to_ohlc(data, frequency)
        elif aggregation == 'mean':
            return data.resample(frequency).mean()
        elif aggregation == 'sum':
            return data.resample(frequency).sum()
        else:
            raise ValueError(f"Unsupported aggregation method: {aggregation}")
