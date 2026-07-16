import pandas as pd
from data_loader import DataLoader, DataRequest

class Strategy:
    """
    Base class for all trading strategies.
    """
    def __init__(self, name="BaseStrategy", **kwargs):
        self.name = name
        self.params = kwargs
        self.atr_col = "ATR14"
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Load required data, calculate indicators, and return a single unified DataFrame.
        Must be implemented by subclasses.
        """
        raise NotImplementedError
        
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate entry and regime signals on the prepared DataFrame.
        Must be implemented by subclasses.
        """
        raise NotImplementedError
        
    def check_exit(self, row, trade):
        """
        Check for custom strategy exit conditions on a given bar.
        
        Args:
            row: Current bar's Series data
            trade: Currently open trade dictionary
            
        Returns:
            exit_price (float) if exit condition met, otherwise None
        """
        return None
