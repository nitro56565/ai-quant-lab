class DataLoaderError(Exception):
    """Base exception for DataLoader errors."""
    pass

class SymbolNotFoundError(DataLoaderError):
    """Raised when the requested symbol is not found in the data registry."""
    pass

class TimeframeNotFoundError(DataLoaderError):
    """Raised when the requested timeframe is not available."""
    pass

class MissingDataError(DataLoaderError):
    """Raised when data is missing for the requested date range."""
    pass

class CorruptDataError(DataLoaderError):
    """Raised when loaded data fails validation checks (duplicate timestamps, OHLC violations, etc.)."""
    pass
