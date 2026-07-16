import pandas as pd
from data_loader import DataLoader, DataRequest
import indicator_engine as ie
from .base import Strategy

class AdaptiveTrendFollowing(Strategy):
    """
    Adaptive Trend Following Strategy:
    - Trend Filter (H4): Buy only if EMA50 > EMA200 and ADX > 25.
    - Entry Trigger (H1): Price pulls back to EMA50, bullish candle closes, and H1 ADX > 25.
    - Stop Loss: 1.5 * ATR (H1).
    - Exit: ATR Trailing Stop.
    """
    def __init__(self, sl_atr_multiplier=1.0, trail_atr_multiplier=1.5, **kwargs):
        """
        Initialize the strategy parameters.
        
        Args:
            sl_atr_multiplier: Multiplier for stop loss (1.0 * ATR)
            trail_atr_multiplier: Multiplier for trailing stop (1.5 * ATR)
        """
        super().__init__(name="AdaptiveTrendFollowing", **kwargs)
        self.sl_atr_multiplier = sl_atr_multiplier
        self.trail_atr_multiplier = trail_atr_multiplier
        self.atr_col = 'ATR14_H1'
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Load H4 and H1 data, calculate indicators, shift H4 indicators to prevent
        lookahead bias, and align them into a single DatetimeIndexed DataFrame.
        """
        start_dt = pd.to_datetime(start_date)
        # 60 days warmup is sufficient to compute H4 EMA 200 (60 days * 6 bars/day = 360 bars)
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        # Load data
        req_h4 = DataRequest(symbol=symbol, timeframe="4h", start=warmup_start, end=end_date)
        req_h1 = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        
        df_h4 = data_loader.load(req_h4)
        df_h1 = data_loader.load(req_h1)
        
        # Calculate H4 indicators
        h4_indicators = [
            ie.EMA(50),
            ie.EMA(200),
            ie.ADX(14)
        ]
        df_h4 = ie.calculate(df_h4, h4_indicators)
        
        # Rename H4 indicators to prevent collision
        df_h4 = df_h4.rename(columns={
            'EMA50': 'EMA50_H4',
            'EMA200': 'EMA200_H4',
            'ADX14': 'ADX14_H4'
        })
        
        # Calculate H1 indicators
        h1_indicators = [
            ie.EMA(50),
            ie.ATR(14),
            ie.ADX(14)
        ]
        df_h1 = ie.calculate(df_h1, h1_indicators)
        df_h1 = df_h1.rename(columns={
            'EMA50': 'EMA50_H1',
            'ATR14': 'ATR14_H1',
            'ADX14': 'ADX14_H1'
        })
        
        # Shift H4 indicators to prevent lookahead bias (historical close is only known on next bar)
        h4_cols = ['EMA50_H4', 'EMA200_H4', 'ADX14_H4']
        h4_indicators_df = df_h4[h4_cols].shift(1)
        
        # Forward-fill H4 indicators to match H1 frequency
        h4_aligned = h4_indicators_df.reindex(df_h1.index, method='ffill')
        
        # Combine H1 prices/indicators and aligned H4 indicators
        combined_df = pd.concat([df_h1, h4_aligned], axis=1)
        
        # Filter out warmup data to return only requested date range
        is_tz_aware = combined_df.index.tz is not None
        start_ts = start_dt
        if is_tz_aware and start_ts.tz is None:
            start_ts = start_ts.tz_localize('UTC')
            
        combined_df = combined_df.loc[combined_df.index >= start_ts]
        
        # Generate signal columns
        combined_df = self.generate_signals(combined_df)
        
        return combined_df
        
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate strategy regime and entry signal flags.
        """
        df = df.copy()
        
        # H4 Filter: EMA50 > EMA200 and H4 ADX > 20 (slightly relaxed for more setups)
        df['long_regime'] = (df['EMA50_H4'] > df['EMA200_H4']) & (df['ADX14_H4'] > 20)
        
        # H1 Pullback: low drops to or below H1 EMA50
        df['pullback'] = df['low'] <= df['EMA50_H1']
        
        # H1 Bullish Close: Close > Open and closes above EMA50
        df['bullish_close'] = (df['close'] > df['open']) & (df['close'] > df['EMA50_H1'])
        
        # H1 Trend Strength: H1 ADX > 20 (relaxed from 25 to allow entries on re-accelerating trends)
        df['h1_trend_strength'] = df['ADX14_H1'] > 20
        
        # Combined Entry Signal (triggers when all conditions align in long regime)
        df['entry_signal'] = (
            df['long_regime'] & 
            df['pullback'] & 
            df['bullish_close'] & 
            df['h1_trend_strength']
        )
        
        return df
