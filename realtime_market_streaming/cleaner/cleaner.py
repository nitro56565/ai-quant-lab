"""
Cleaner for processing and cleaning market data.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MarketDataCleaner:
    """
    Cleaner for processing and cleaning market data.
    """
    
    def clean(self, data, price_precision=5):
        """
        Clean and normalize market data.
        
        Args:
            data: Raw market data DataFrame (columns: timestamp, bid, ask, volume)
            price_precision: Number of decimal places for price precision
            
        Returns:
            Cleaned and normalized market data
        """
        df = data.copy()
        
        # Normalize timestamps to UTC
        df = self.normalize_timestamps_to_utc(df)
        
        # Normalize float precision for prices
        df = self.normalize_float_precision(df, precision=price_precision)
        
        # Handle missing volumes
        df = self.handle_missing_volumes(df)
        
        # Add spread column
        df = self.add_spread_column(df)
        
        return df
    
    def normalize_timestamps_to_utc(self, data):
        """
        Convert timestamps to UTC timezone.
        
        Args:
            data: Market data with timestamp column
            
        Returns:
            Data with timestamps in UTC
        """
        df = data.copy()
        
        if 'timestamp' in df.columns:
            # If timestamp is timezone-naive, assume it's UTC
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
            else:
                # Convert to UTC if it has a timezone
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
        
        return df
    
    def normalize_float_precision(self, data, precision=5):
        """
        Normalize float precision for price columns.
        
        Args:
            data: Market data with price columns
            precision: Number of decimal places to round to
            
        Returns:
            Data with normalized float precision
        """
        df = data.copy()
        
        price_columns = ['bid', 'ask']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].round(precision)
        
        return df
    
    def handle_missing_volumes(self, data, fill_value=0):
        """
        Handle missing volume values by filling with default.
        
        Args:
            data: Market data with volume column
            fill_value: Value to use for missing volumes
            
        Returns:
            Data with missing volumes filled
        """
        df = data.copy()
        
        if 'volume' in df.columns:
            df['volume'] = df['volume'].fillna(fill_value)
        
        return df
    
    def add_spread_column(self, data):
        """
        Add spread column (ask - bid).
        
        Args:
            data: Market data with bid and ask columns
            
        Returns:
            Data with spread column added
        """
        df = data.copy()
        
        if 'bid' in df.columns and 'ask' in df.columns:
            df['spread'] = df['ask'] - df['bid']
        
        return df
    
    def handle_missing_values(self, data, method='forward_fill'):
        """
        Handle missing values in the data.
        
        Args:
            data: Market data with potential missing values
            method: Method to handle missing values (forward_fill, backward_fill, drop)
            
        Returns:
            Data with missing values handled
        """
        df = data.copy()
        
        if method == 'forward_fill':
            df = df.fillna(method='ffill')
        elif method == 'backward_fill':
            df = df.fillna(method='bfill')
        elif method == 'drop':
            df = df.dropna()
        else:
            logger.warning(f"Unknown method {method}, returning original data")
        
        return df
    
    def remove_outliers(self, data, method='iqr'):
        """
        Remove outliers from the data.
        
        Args:
            data: Market data with potential outliers
            method: Method to detect outliers (iqr, zscore)
            
        Returns:
            Data with outliers removed
        """
        df = data.copy()
        
        if method == 'iqr':
            for col in ['bid', 'ask']:
                if col in df.columns:
                    Q1 = df[col].quantile(0.25)
                    Q3 = df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR
                    df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]
        
        elif method == 'zscore':
            for col in ['bid', 'ask']:
                if col in df.columns:
                    z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
                    df = df[z_scores < 3]
        
        return df
