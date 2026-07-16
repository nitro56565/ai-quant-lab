import pandas as pd
from typing import List
from .indicators import Indicator

class IndicatorEngine:
    """
    Engine to calculate a list of indicator objects and append them
    as columns to a DataFrame.
    """
    def calculate(self, df: pd.DataFrame, indicators: List[Indicator]) -> pd.DataFrame:
        """
        Calculate indicators and append as columns.
        Does NOT modify the original DataFrame (returns a copy).
        
        Args:
            df: DataFrame containing price data.
            indicators: List of Indicator objects to calculate.
            
        Returns:
            DataFrame with indicator columns appended.
        """
        # Create a shallow copy to prevent modifying the user's DataFrame in place
        df_out = df.copy()
        
        for indicator in indicators:
            if not isinstance(indicator, Indicator):
                raise TypeError(f"Expected Indicator instance, got {type(indicator)}")
            
            # Calculate and assign column
            df_out[indicator.name] = indicator.calculate(df)
            
        return df_out

# Global helper function for direct functional API usage
def calculate(df: pd.DataFrame, indicators: List[Indicator]) -> pd.DataFrame:
    engine = IndicatorEngine()
    return engine.calculate(df, indicators)
