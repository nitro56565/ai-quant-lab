import pandas as pd
from data_loader import DataLoader, DataRequest
import indicator_engine as ie
from .base import Strategy

class VolatilityBreakout(Strategy):
    """
    Strategy 4: Volatility Breakout
    - Trend Filter: Close > EMA200 (Trade breakouts only in direction of primary trend)
    - Volatility Compression: Bollinger Squeeze (BB width < 50 SMA of BB width) in the last 5 bars
    - Volatility Expansion: ATR increasing (ATR > 5 SMA of ATR)
    - Entry Trigger: Close breaks above the 20-period Donchian Upper Channel
    - Stop Loss: 2.0 * ATR (adjusted to give breakouts room to breathe)
    - Exit: ATR Trailing Stop (3.0 * ATR)
    """
    def __init__(self, sl_atr_multiplier=2.0, trail_atr_multiplier=4.0, **kwargs):
        super().__init__(name="VolatilityBreakout", **kwargs)
        self.sl_atr_multiplier = sl_atr_multiplier
        self.trail_atr_multiplier = trail_atr_multiplier
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_dt = pd.to_datetime(start_date)
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        req = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        df = data_loader.load(req)
        
        # Calculate indicators
        indicators = [
            ie.ATR(14),
            ie.EMA(200),
            ie.BBandsMid(20),
            ie.BBandsUpper(20),
            ie.BBandsLower(20),
            ie.DonchianUpper(20),
            ie.DonchianLower(20)
        ]
        df = ie.calculate(df, indicators)
        
        # Bollinger width & SMA
        df['BB_width'] = (df['BB_upper_20'] - df['BB_lower_20']) / df['BB_mid_20']
        df['BB_width_SMA'] = df['BB_width'].rolling(window=50).mean()
        
        # ATR SMA (to check if ATR is increasing/expanding)
        df['ATR14_SMA'] = df['ATR14'].rolling(window=5).mean()
        
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
        
        # 1. Bollinger Squeeze (Compression)
        df['squeeze'] = df['BB_width'] < df['BB_width_SMA']
        # Squeeze was active recently (within the last 5 bars) to allow for expansion at breakout bar
        df['squeeze_recent'] = df['squeeze'].rolling(window=5).max() > 0
        
        # 2. Volatility Expansion (ATR increasing above its 5-period average)
        df['atr_increasing'] = df['ATR14'] > df['ATR14_SMA']
        
        # 3. Donchian Channel Breakout (close breaks above the shift(1) upper channel)
        df['donchian_breakout'] = df['close'] > df['DC_upper_20'].shift(1)
        
        # 4. Long-term Trend Filter
        df['uptrend'] = df['close'] > df['EMA200']
        
        # Combined Entry Signal
        df['entry_signal'] = (
            df['squeeze_recent'] & 
            df['atr_increasing'] & 
            df['donchian_breakout'] & 
            df['uptrend']
        )
        
        return df
