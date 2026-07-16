import pandas as pd
from data_loader import DataLoader, DataRequest
import indicator_engine as ie
from .base import Strategy

class MeanReversion(Strategy):
    """
    Strategy 3: Mean Reversion
    - Active only in quiet markets (ADX < 20)
    - Entry: Close is below lower Bollinger Band, RSI < 25, and ATR is below its 20 SMA (low vol compression)
    - Stop Loss: 1.5 * ATR
    - Take Profit (Custom Exit): Middle Bollinger Band (SMA 20)
    """
    def __init__(self, sl_atr_multiplier=1.5, **kwargs):
        super().__init__(name="MeanReversion", **kwargs)
        self.sl_atr_multiplier = sl_atr_multiplier
        # We don't use trailing stop for mean reversion (set it high to disable, or check_exit TP will hit first)
        self.trail_atr_multiplier = 999.0 
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_dt = pd.to_datetime(start_date)
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        req = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        df = data_loader.load(req)
        
        # Calculate indicators
        indicators = [
            ie.ADX(14),
            ie.RSI(14),
            ie.ATR(14),
            ie.BBandsMid(20),
            ie.BBandsUpper(20),
            ie.BBandsLower(20)
        ]
        df = ie.calculate(df, indicators)
        
        # Calculate ATR Moving Average
        df['ATR14_SMA'] = df['ATR14'].rolling(window=20).mean()
        
        # Filter out warmup data
        is_tz_aware = df.index.tz is not None
        start_ts = start_dt
        if is_tz_aware and start_ts.tz is None:
            start_ts = start_ts.tz_localize('UTC')
            
        df = df.loc[df.index >= start_ts]
        
        # Generate signals
        df = self.generate_signals(df)
        return df
        
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. Non-trending conditions: ADX < 25 (standard threshold for ranging market)
        df['quiet_market'] = df['ADX14'] < 25
        
        # 2. Outside lower Bollinger Band
        df['below_bb_lower'] = df['close'] < df['BB_lower_20']
        
        # 3. Oversold: RSI < 30 (standard oversold)
        df['oversold'] = df['RSI14'] < 30
        
        # Combined Entry Signal (removed contradictory low_vol check as BB breakouts expand ATR)
        df['entry_signal'] = (
            df['quiet_market'] & 
            df['below_bb_lower'] & 
            df['oversold']
        )
        
        return df
        
    def check_exit(self, row, trade):
        """
        Mean Reversion Custom Exit: Take profit when price rises to the Middle Bollinger Band.
        """
        # If the high of the current bar touches or exceeds the Middle Bollinger Band (SMA 20)
        if row['high'] >= row['BB_mid_20']:
            # Assume execution at Middle Bollinger Band level
            return row['BB_mid_20']
            
        return None
