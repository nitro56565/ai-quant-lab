"""
Validator for market data quality checks.
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)

class MarketDataValidator:
    """
    Validator for ensuring market data quality.
    """
    
    def validate(self, data):
        """
        Validate market data for quality and completeness.
        
        Args:
            data: DataFrame with market data (columns: timestamp, bid, ask, volume)
            
        Returns:
            dict with validation results and any issues found
        """
        issues = []
        
        # Check for duplicate timestamps
        dup_count = self.check_duplicate_timestamps(data)
        if dup_count > 0:
            issues.append(f"Found {dup_count} duplicate timestamps")
        
        # Check bid <= ask
        bid_ask_violations = self.check_bid_ask_relationship(data)
        if bid_ask_violations > 0:
            issues.append(f"Found {bid_ask_violations} records where bid > ask")
        
        # Check for NaNs
        nan_count = self.check_missing_values(data)
        if nan_count > 0:
            issues.append(f"Found {nan_count} NaN values")
        
        # Check timestamps are increasing
        if not self.check_timestamps_increasing(data):
            issues.append("Timestamps are not monotonically increasing")
        
        # Check valid prices
        invalid_prices = self.check_valid_prices(data)
        if invalid_prices > 0:
            issues.append(f"Found {invalid_prices} invalid price values (<= 0 or NaN)")
        
        # Check valid volumes
        invalid_volumes = self.check_valid_volumes(data)
        if invalid_volumes > 0:
            issues.append(f"Found {invalid_volumes} invalid volume values (< 0)")
        
        is_valid = len(issues) == 0
        
        if not is_valid:
            logger.warning(f"Validation failed with {len(issues)} issues")
            for issue in issues:
                logger.warning(f"  - {issue}")
        else:
            logger.info("Validation passed")
        
        return {
            'is_valid': is_valid,
            'issues': issues,
            'total_rows': len(data)
        }
    
    def check_duplicate_timestamps(self, data):
        """
        Check for duplicate timestamps in the data.
        
        Args:
            data: Market data to check
            
        Returns:
            Number of duplicate timestamps
        """
        if 'timestamp' not in data.columns:
            return 0
        
        return data['timestamp'].duplicated().sum()
    
    def check_bid_ask_relationship(self, data):
        """
        Check that bid <= ask for all records.
        
        Args:
            data: Market data to check
            
        Returns:
            Number of violations where bid > ask
        """
        if 'bid' not in data.columns or 'ask' not in data.columns:
            return 0
        
        return (data['bid'] > data['ask']).sum()
    
    def check_missing_values(self, data):
        """
        Check for missing values in the data.
        
        Args:
            data: Market data to check
            
        Returns:
            Total number of NaN values
        """
        return data.isna().sum().sum()
    
    def check_timestamps_increasing(self, data):
        """
        Check that timestamps are monotonically increasing.
        
        Args:
            data: Market data to check
            
        Returns:
            Boolean indicating if timestamps are increasing
        """
        if 'timestamp' not in data.columns or len(data) < 2:
            return True
        
        return data['timestamp'].is_monotonic_increasing
    
    def check_valid_prices(self, data):
        """
        Check that prices are valid (positive values).
        
        Args:
            data: Market data to check
            
        Returns:
            Number of invalid price values
        """
        invalid_count = 0
        
        if 'bid' in data.columns:
            invalid_count += (data['bid'] <= 0).sum()
        
        if 'ask' in data.columns:
            invalid_count += (data['ask'] <= 0).sum()
        
        return invalid_count
    
    def check_valid_volumes(self, data):
        """
        Check that volumes are valid (non-negative values).
        
        Args:
            data: Market data to check
            
        Returns:
            Number of invalid volume values
        """
        if 'volume' not in data.columns:
            return 0
        
        return (data['volume'] < 0).sum()
    
    def check_data_types(self, data):
        """
        Verify data types are correct.
        
        Args:
            data: Market data to check
            
        Returns:
            Boolean indicating if data types are valid
        """
        expected_types = {
            'timestamp': 'datetime64[ns]',
            'bid': 'float64',
            'ask': 'float64',
            'volume': 'int64'
        }
        
        for col, expected_type in expected_types.items():
            if col in data.columns:
                if str(data[col].dtype) != expected_type:
                    logger.warning(f"Column {col} has type {data[col].dtype}, expected {expected_type}")
                    return False
        
        return True
