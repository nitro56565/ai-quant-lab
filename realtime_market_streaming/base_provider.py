import abc
import pandas as pd
from typing import Dict, Any, List, Optional
from pathlib import Path

class MarketDataProvider(abc.ABC):
    """
    Abstract Base Class for Market Data Providers.
    Defines a unified, polymorphic interface for downloading, validating,
    resampling, updating, and preserving metadata for any asset or data source.
    """
    @abc.abstractmethod
    def download(self, symbol: str, start_date: str, end_date: str, **kwargs) -> Path:
        """
        Download raw tick/candle data for a symbol and date range.
        Returns Path to the immutable raw data storage.
        """
        pass

    @abc.abstractmethod
    def validate(self, raw_data_path: Path, **kwargs) -> Dict[str, Any]:
        """
        Execute data quality validation checks.
        Returns a dictionary summarizing validation results and quality status.
        """
        pass

    @abc.abstractmethod
    def update(self, symbol: str, **kwargs) -> Path:
        """
        Incrementally update dataset with missing recent days.
        Returns Path to the updated raw storage.
        """
        pass

    @abc.abstractmethod
    def metadata(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        Generate and return detailed audit metadata.
        """
        pass
