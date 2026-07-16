import os
import json
import logging
import pandas as pd
from pathlib import Path
from .exceptions import (
    SymbolNotFoundError,
    TimeframeNotFoundError,
    MissingDataError,
    CorruptDataError
)
from .request import DataRequest

logger = logging.getLogger(__name__)

class DataLoader:
    """
    DataLoader loads OHLCV data from the pipeline output directory.
    Supports DataRequest queries, caching, symbol metadata verification,
    data quality validation, trading calendar awareness, and fallback resampling.
    """
    def __init__(self, data_dir=None, metadata_dir=None):
        """
        Initialize the DataLoader.
        
        Args:
            data_dir: Path to the pipeline output directory.
            metadata_dir: Path to the pipeline metadata directory.
        """
        base_dir = Path(__file__).resolve().parent.parent
        self.data_dir = Path(data_dir) if data_dir else base_dir / 'market_data_pipeline' / 'output'
        self.metadata_dir = Path(metadata_dir) if metadata_dir else base_dir / 'market_data_pipeline' / 'metadata'
        
        # Memory Cache: key is (symbol, timeframe, year) -> DataFrame
        self._cache = {}
        
    def get_symbol_metadata(self, symbol):
        """
        Load symbol metadata from json file.
        
        Args:
            symbol: Trading symbol (e.g. "EURUSD")
            
        Returns:
            Dict containing symbol metadata parameters
        """
        symbol = symbol.upper().strip()
        metadata_file = self.metadata_dir / symbol / "symbol_info.json"
        
        if not metadata_file.exists():
            # Try falling back to data_dir
            metadata_file = self.data_dir / symbol / "symbol_info.json"
            
        if not metadata_file.exists():
            raise SymbolNotFoundError(f"Symbol metadata not found for '{symbol}' at {metadata_file}")
            
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise SymbolNotFoundError(f"Failed to read symbol metadata for '{symbol}': {e}")
            
    def _normalize_timeframe(self, timeframe):
        """Normalize timeframe string to pandas frequency alias."""
        tf = timeframe.lower().strip()
        if tf in ('1m', '1min', '1minut', '1minute'):
            return '1min'
        elif tf in ('5m', '5min', '5minutes'):
            return '5min'
        elif tf in ('15m', '15min', '15minutes'):
            return '15min'
        elif tf in ('1h', '60m', '60min', '1hour'):
            return '1h'
        elif tf in ('4h', '240m', '240min', '4hours'):
            return '4h'
        elif tf in ('1d', 'daily', '1day'):
            return '1d'
        else:
            raise TimeframeNotFoundError(f"Unsupported timeframe: '{timeframe}'.")

    def load(self, request: DataRequest):
        """
        Load market data using a DataRequest parameter object.
        
        Args:
            request: DataRequest object encapsulating query details
            
        Returns:
            DataFrame with DatetimeIndex index and open, high, low, close, volume columns
        """
        # 1. Load Symbol Metadata
        metadata = self.get_symbol_metadata(request.symbol)
        
        target_tf = self._normalize_timeframe(request.timeframe)
        
        # 2. Lazy load files based on requested start and end dates
        start_year = request.start.year if request.start else None
        end_year = request.end.year if request.end else None
        
        tf_dir = self.data_dir / request.symbol / "bars" / target_tf
        
        load_and_resample = False
        source_tf = target_tf
        
        # Timeframe resolution fallback
        if not tf_dir.exists() or not any(tf_dir.glob("*.parquet")):
            if target_tf != '1min':
                fallback_dir = self.data_dir / request.symbol / "bars" / "1min"
                if fallback_dir.exists() and any(fallback_dir.glob("*.parquet")):
                    tf_dir = fallback_dir
                    source_tf = '1min'
                    load_and_resample = True
                else:
                    raise TimeframeNotFoundError(
                        f"No bar files found for symbol '{request.symbol}' at timeframe '{request.timeframe}' or fallback '1min'."
                    )
            else:
                raise TimeframeNotFoundError(
                    f"No bar files found for symbol '{request.symbol}' at timeframe '{request.timeframe}'."
                )
                
        # Get parquet files
        all_files = sorted(tf_dir.glob("*.parquet"))
        
        # Filter files for lazy loading
        files_to_load = []
        for file in all_files:
            try:
                year = int(file.stem)
                if start_year and year < start_year:
                    continue
                if end_year and year > end_year:
                    continue
                files_to_load.append((year, file))
            except ValueError:
                files_to_load.append((None, file))
                
        if not files_to_load:
            raise MissingDataError(f"No data files match the requested date range for {request.symbol}")
            
        # 3. Caching: Load files, utilizing cache where possible
        dfs = []
        for year, file_path in files_to_load:
            cache_key = (request.symbol, source_tf, year)
            if cache_key in self._cache:
                df = self._cache[cache_key]
            else:
                try:
                    df = pd.read_parquet(file_path)
                    # Standardize index
                    if 'timestamp' in df.columns:
                        df = df.set_index('timestamp')
                    elif not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index)
                        
                    self._cache[cache_key] = df
                except Exception as e:
                    raise CorruptDataError(f"Failed to read data file {file_path.name}: {e}")
            dfs.append(df)
            
        combined_df = pd.concat(dfs).sort_index()
        
        # Timezone compatibility filtering
        is_tz_aware = combined_df.index.tz is not None
        start_ts = request.start
        end_ts = request.end
        
        if start_ts:
            if is_tz_aware and start_ts.tz is None:
                start_ts = start_ts.tz_localize('UTC')
            combined_df = combined_df.loc[combined_df.index >= start_ts]
            
        if end_ts:
            if is_tz_aware and end_ts.tz is None:
                end_ts = end_ts.tz_localize('UTC')
            combined_df = combined_df.loc[combined_df.index <= end_ts]
            
        if combined_df.empty:
            raise MissingDataError(f"No data available for {request.symbol} inside the date range {request.start} to {request.end}")
            
        # Format prices (mid, bid, ask, raw)
        df_formatted = self._format_prices(combined_df, request.price_type)
        
        # Resample if fallback was used
        if load_and_resample:
            df_formatted = self.resample_ohlcv(df_formatted, target_tf)
            
        # Clean any intervals with no price activity (e.g. gaps/empty bars)
        if 'close' in df_formatted.columns:
            df_formatted = df_formatted.dropna(subset=['close'])
            
        # 4. Data Validation
        self.validate_data(df_formatted, asset_type=metadata.get('asset_type', 'forex'))
        
        return df_formatted

    def _format_prices(self, df, price_type):
        """Format raw bid/ask OHLCV columns to standardized OHLCV."""
        if price_type == 'raw':
            return df
            
        price_type = price_type.lower().strip()
        
        has_bid = all(c in df.columns for c in ['bid_open', 'bid_high', 'bid_low', 'bid_close'])
        has_ask = all(c in df.columns for c in ['ask_open', 'ask_high', 'ask_low', 'ask_close'])
        
        has_std = all(c in df.columns for c in ['open', 'high', 'low', 'close'])
        if has_std and not (has_bid or has_ask):
            return df
            
        result = pd.DataFrame(index=df.index)
        
        if price_type == 'mid' and has_bid and has_ask:
            result['open'] = (df['bid_open'] + df['ask_open']) / 2.0
            result['high'] = (df['bid_high'] + df['ask_high']) / 2.0
            result['low'] = (df['bid_low'] + df['ask_low']) / 2.0
            result['close'] = (df['bid_close'] + df['ask_close']) / 2.0
        elif price_type == 'bid' and has_bid:
            result['open'] = df['bid_open']
            result['high'] = df['bid_high']
            result['low'] = df['bid_low']
            result['close'] = df['bid_close']
        elif price_type == 'ask' and has_ask:
            result['open'] = df['ask_open']
            result['high'] = df['ask_high']
            result['low'] = df['ask_low']
            result['close'] = df['ask_close']
        else:
            if has_bid:
                result['open'] = df['bid_open']
                result['high'] = df['bid_high']
                result['low'] = df['bid_low']
                result['close'] = df['bid_close']
            elif has_ask:
                result['open'] = df['ask_open']
                result['high'] = df['ask_high']
                result['low'] = df['ask_low']
                result['close'] = df['ask_close']
            else:
                for col in ['open', 'high', 'low', 'close']:
                    if col in df.columns:
                        result[col] = df[col]
                        
        if 'volume' in df.columns:
            result['volume'] = df['volume']
            
        return result

    def resample_ohlcv(self, df, target_frequency):
        """Resample OHLCV to higher timeframe."""
        agg_dict = {}
        if 'open' in df.columns:
            agg_dict['open'] = 'first'
        if 'high' in df.columns:
            agg_dict['high'] = 'max'
        if 'low' in df.columns:
            agg_dict['low'] = 'min'
        if 'close' in df.columns:
            agg_dict['close'] = 'last'
        if 'volume' in df.columns:
            agg_dict['volume'] = 'sum'
            
        if not agg_dict:
            return df
            
        if 'close' in agg_dict:
            resampled = df.resample(target_frequency).agg(agg_dict).dropna(subset=['close'])
        else:
            resampled = df.resample(target_frequency).agg(agg_dict).dropna(how='all')
            
        if 'volume' in resampled.columns:
            resampled['volume'] = resampled['volume'].fillna(0).astype('int64')
        return resampled

    def validate_data(self, df, asset_type='forex'):
        """Validate loaded market data for structural and financial anomalies."""
        # 1. Non-monotonic index
        if not df.index.is_monotonic_increasing:
            raise CorruptDataError("Index is not monotonically increasing.")
            
        # 2. Duplicate timestamps
        if df.index.duplicated().any():
            duplicate_count = df.index.duplicated().sum()
            raise CorruptDataError(f"Found {duplicate_count} duplicate timestamps.")
            
        # 3. NaN values
        nan_cols = df.isna().sum()
        if nan_cols.sum() > 0:
            nan_summary = ", ".join([f"{col}: {val}" for col, val in nan_cols.items() if val > 0])
            raise CorruptDataError(f"Found NaN values in dataset: {nan_summary}")
            
        # 4. OHLC Consistency
        if 'open' in df.columns and 'high' in df.columns:
            violations = df['high'] < df['open']
            if violations.any():
                raise CorruptDataError(f"OHLC violation: high < open found in {violations.sum()} records.")
                
            if 'close' in df.columns:
                violations = df['high'] < df['close']
                if violations.any():
                    raise CorruptDataError(f"OHLC violation: high < close found in {violations.sum()} records.")
                    
        if 'open' in df.columns and 'low' in df.columns:
            violations = df['low'] > df['open']
            if violations.any():
                raise CorruptDataError(f"OHLC violation: low > open found in {violations.sum()} records.")
                
            if 'close' in df.columns:
                violations = df['low'] > df['close']
                if violations.any():
                    raise CorruptDataError(f"OHLC violation: low > close found in {violations.sum()} records.")
                    
        # 5. Trading Calendar Gaps (Weekend vs Normal Hours Gaps)
        if len(df) > 1:
            diffs = pd.Series(df.index).diff().dropna()
            
            mode_diff = diffs.mode()
            if not mode_diff.empty:
                expected_delta = mode_diff[0]
                
                gaps = diffs[diffs > expected_delta]
                for idx, gap in gaps.items():
                    gap_start = df.index[idx - 1]
                    gap_end = df.index[idx]
                    
                    if asset_type == 'forex':
                        if self._is_weekend_gap(gap_start, gap_end):
                            continue
                            
                    logger.warning(f"Unexpected data gap found between {gap_start} and {gap_end} (duration: {gap})")

    def _is_weekend_gap(self, start, end):
        """
        Check if a gap between two timestamps represents a normal forex weekend closure.
        Forex markets close Friday 22:00 UTC and reopen Sunday 22:00 UTC.
        """
        if start.tz is not None:
            start_utc = start.tz_convert('UTC')
            end_utc = end.tz_convert('UTC')
        else:
            start_utc = start
            end_utc = end
            
        start_day = start_utc.weekday()
        end_day = end_utc.weekday()
        
        if start_day == 4 and end_day == 0:  # Friday to Monday
            if start_utc.hour >= 21 and end_utc.hour <= 23:
                return True
        elif start_day == 4 and end_day == 6:  # Friday to Sunday
            if start_utc.hour >= 21 and end_utc.hour >= 21:
                return True
        elif start_day == 5 or (start_day == 6 and start_utc.hour < 21): # Gap starts on Saturday or Sunday morning
            return True
            
        return False
