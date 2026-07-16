import pandas as pd
from data_loader import DataLoader, DataRequest
import indicator_engine as ie
from .base import Strategy

class PullbackContinuation(Strategy):
    """
    Strategy 2: Pullback Continuation
    - Trend: EMA50 > EMA200
    - Pullback: Low drops below or touches EMA20
    - Cooler indicator: RSI between 40 and 50
    - Trigger pattern: Bullish Engulfing candle
    - Stop Loss: 1.5 * ATR
    - Exit: ATR Trailing Stop
    """
    def __init__(self, sl_atr_multiplier=1.0, trail_atr_multiplier=2.0, **kwargs):
        super().__init__(name="PullbackContinuation", **kwargs)
        self.sl_atr_multiplier = sl_atr_multiplier
        self.trail_atr_multiplier = trail_atr_multiplier
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_dt = pd.to_datetime(start_date)
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        req = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        df = data_loader.load(req)
        
        # Calculate indicators
        indicators = [
            ie.EMA(20),
            ie.EMA(50),
            ie.EMA(200),
            ie.RSI(14),
            ie.ATR(14)
        ]
        df = ie.calculate(df, indicators)
        
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
        
        # 1. Trend Filter: EMA50 > EMA200
        df['trend_ok'] = df['EMA50'] > df['EMA200']
        
        # 2. Pullback: Low is below or equal to EMA20
        df['pullback_to_ema20'] = df['low'] <= df['EMA20']
        
        # 3. RSI between 40 and 50
        df['rsi_ok'] = (df['RSI14'] >= 40) & (df['RSI14'] <= 50)
        
        # 4. Bullish Engulfing Candle Pattern
        # - Current candle is bullish: close > open
        bullish_curr = df['close'] > df['open']
        # - Previous candle was bearish: close.shift(1) < open.shift(1)
        bearish_prev = df['close'].shift(1) < df['open'].shift(1)
        # - Current body engulfs previous body
        #   Current close >= previous open AND current open <= previous close
        engulfing_body = (df['close'] >= df['open'].shift(1)) & (df['open'] <= df['close'].shift(1))
        
        df['bullish_engulfing'] = bullish_curr & bearish_prev & engulfing_body
        
        # Entry signal triggers when all align
        df['entry_signal'] = (
            df['trend_ok'] & 
            df['pullback_to_ema20'] & 
            df['rsi_ok'] & 
            df['bullish_engulfing']
        )
        
        return df
