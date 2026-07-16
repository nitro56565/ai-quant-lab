import pandas as pd
import numpy as np

class Indicator:
    """Base class for all indicators."""
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError
        
    @property
    def name(self) -> str:
        raise NotImplementedError

class EMA(Indicator):
    """Exponential Moving Average (EMA)."""
    def __init__(self, period=20, column='close'):
        self.period = period
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found in DataFrame.")
        return df[self.column].ewm(span=self.period, adjust=False).mean()
        
    @property
    def name(self) -> str:
        return f"EMA{self.period}"

class SMA(Indicator):
    """Simple Moving Average (SMA)."""
    def __init__(self, period=20, column='close'):
        self.period = period
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found in DataFrame.")
        return df[self.column].rolling(window=self.period).mean()
        
    @property
    def name(self) -> str:
        return f"SMA{self.period}"

class RSI(Indicator):
    """Relative Strength Index (RSI)."""
    def __init__(self, period=14, column='close'):
        self.period = period
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found in DataFrame.")
        
        delta = df[self.column].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Wilder's smoothing
        avg_gain = gain.ewm(com=self.period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.period - 1, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    @property
    def name(self) -> str:
        return f"RSI{self.period}"

class ATR(Indicator):
    """Average True Range (ATR)."""
    def __init__(self, period=14):
        self.period = period
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        for col in ['high', 'low', 'close']:
            if col not in df.columns:
                raise KeyError(f"ATR calculation requires column '{col}'")
                
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        # Wilder's moving average
        atr = tr.ewm(alpha=1/self.period, adjust=False).mean()
        return atr
        
    @property
    def name(self) -> str:
        return f"ATR{self.period}"

class ADX(Indicator):
    """Average Directional Index (ADX)."""
    def __init__(self, period=14):
        self.period = period
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        for col in ['high', 'low', 'close']:
            if col not in df.columns:
                raise KeyError(f"ADX calculation requires column '{col}'")
                
        high = df['high']
        low = df['low']
        close = df['close']
        
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Wilder's smoothing
        tr_smoothed = tr.ewm(alpha=1/self.period, adjust=False).mean()
        plus_dm_smoothed = pd.Series(plus_dm, index=df.index).ewm(alpha=1/self.period, adjust=False).mean()
        minus_dm_smoothed = pd.Series(minus_dm, index=df.index).ewm(alpha=1/self.period, adjust=False).mean()
        
        # Prevent division by zero
        plus_di = 100 * (plus_dm_smoothed / tr_smoothed.replace(0, np.nan))
        minus_di = 100 * (minus_dm_smoothed / tr_smoothed.replace(0, np.nan))
        
        plus_di = plus_di.fillna(0)
        minus_di = minus_di.fillna(0)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).abs().replace(0, np.nan)
        dx = dx.fillna(0)
        
        adx = dx.ewm(alpha=1/self.period, adjust=False).mean()
        return adx
        
    @property
    def name(self) -> str:
        return f"ADX{self.period}"

class BBandsMid(Indicator):
    """Bollinger Bands Middle Band (SMA)."""
    def __init__(self, period=20, column='close'):
        self.period = period
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found.")
        return df[self.column].rolling(window=self.period).mean()
        
    @property
    def name(self) -> str:
        return f"BB_mid_{self.period}"

class BBandsUpper(Indicator):
    """Bollinger Bands Upper Band."""
    def __init__(self, period=20, num_std=2.0, column='close'):
        self.period = period
        self.num_std = num_std
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found.")
        mid = df[self.column].rolling(window=self.period).mean()
        std = df[self.column].rolling(window=self.period).std()
        return mid + self.num_std * std
        
    @property
    def name(self) -> str:
        return f"BB_upper_{self.period}"

class BBandsLower(Indicator):
    """Bollinger Bands Lower Band."""
    def __init__(self, period=20, num_std=2.0, column='close'):
        self.period = period
        self.num_std = num_std
        self.column = column
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found.")
        mid = df[self.column].rolling(window=self.period).mean()
        std = df[self.column].rolling(window=self.period).std()
        return mid - self.num_std * std
        
    @property
    def name(self) -> str:
        return f"BB_lower_{self.period}"

class DonchianUpper(Indicator):
    """Donchian Channel Upper Band (highest high in period)."""
    def __init__(self, period=20):
        self.period = period
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if 'high' not in df.columns:
            raise KeyError("Donchian calculation requires column 'high'")
        return df['high'].rolling(window=self.period).max()
        
    @property
    def name(self) -> str:
        return f"DC_upper_{self.period}"

class DonchianLower(Indicator):
    """Donchian Channel Lower Band (lowest low in period)."""
    def __init__(self, period=20):
        self.period = period
        
    def calculate(self, df: pd.DataFrame) -> pd.Series:
        if 'low' not in df.columns:
            raise KeyError("Donchian calculation requires column 'low'")
        return df['low'].rolling(window=self.period).min()
        
    @property
    def name(self) -> str:
        return f"DC_lower_{self.period}"

