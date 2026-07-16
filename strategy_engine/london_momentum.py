import pandas as pd
from data_loader import DataLoader, DataRequest
import indicator_engine as ie
from .base import Strategy

class LondonSessionMomentum(Strategy):
    """
    Strategy 5: London Session Momentum
    - Trading Window: London Open (08:00 to 11:00 UTC)
    - Trend Filters (Multi-timeframe):
      * H4: EMA 50 > EMA 200
      * H1: EMA 50 > EMA 200
    - Volatility Expansion Filter: M15 ATR > 1.1 * SMA of M15 ATR (prevents quiet breakout entries)
    - Trigger (M15): Close breaks above M15 20-period Donchian Upper Channel
    - Stop Loss: 2.0 * ATR (M15)
    - Exit: ATR Trailing Stop (3.0 * ATR)
    """
    def __init__(self, sl_atr_multiplier=1.5, trail_atr_multiplier=4.0, **kwargs):
        super().__init__(name="LondonSessionMomentum", **kwargs)
        self.sl_atr_multiplier = sl_atr_multiplier
        self.trail_atr_multiplier = trail_atr_multiplier
        self.atr_col = 'ATR14_M15'
        
    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_dt = pd.to_datetime(start_date)
        warmup_start = (start_dt - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        
        # Load multiple timeframes
        req_h4 = DataRequest(symbol=symbol, timeframe="4h", start=warmup_start, end=end_date)
        req_h1 = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        req_m15 = DataRequest(symbol=symbol, timeframe="15m", start=warmup_start, end=end_date)
        
        df_h4 = data_loader.load(req_h4)
        df_h1 = data_loader.load(req_h1)
        df_m15 = data_loader.load(req_m15)
        
        # Calculate H4 trend indicators
        df_h4 = ie.calculate(df_h4, [ie.EMA(50), ie.EMA(200)])
        df_h4 = df_h4.rename(columns={'EMA50': 'EMA50_H4', 'EMA200': 'EMA200_H4'})
        
        # Shift to prevent lookahead bias
        h4_indicators_shifted = df_h4[['EMA50_H4', 'EMA200_H4']].shift(1)
        
        # Calculate H1 trend indicators
        df_h1 = ie.calculate(df_h1, [ie.EMA(50), ie.EMA(200)])
        df_h1 = df_h1.rename(columns={'EMA50': 'EMA50_H1', 'EMA200': 'EMA200_H1'})
        
        # Shift to prevent lookahead bias
        h1_indicators_shifted = df_h1[['EMA50_H1', 'EMA200_H1']].shift(1)
        
        # Calculate M15 indicators
        df_m15 = ie.calculate(df_m15, [ie.ATR(14), ie.DonchianUpper(20)])
        df_m15 = df_m15.rename(columns={'ATR14': 'ATR14_M15', 'DC_upper_20': 'DC_upper_20_M15'})
        
        # Calculate ATR Moving Average on M15
        df_m15['ATR14_M15_SMA'] = df_m15['ATR14_M15'].rolling(window=20).mean()
        
        # Align H4 and H1 with M15 timeline (forward-fill)
        h4_aligned = h4_indicators_shifted.reindex(df_m15.index, method='ffill')
        h1_aligned = h1_indicators_shifted.reindex(df_m15.index, method='ffill')
        
        # Combine
        combined_df = pd.concat([df_m15, h1_aligned, h4_aligned], axis=1)
        
        # Filter out warmup data
        is_tz_aware = combined_df.index.tz is not None
        start_ts = start_dt
        if is_tz_aware and start_ts.tz is None:
            start_ts = start_ts.tz_localize('UTC')
            
        combined_df = combined_df.loc[combined_df.index >= start_ts]
        
        # Generate signals
        combined_df = self.generate_signals(combined_df)
        return combined_df
        
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. H4 Trend: EMA 50 > EMA 200
        df['h4_trend_ok'] = df['EMA50_H4'] > df['EMA200_H4']
        
        # 2. H1 Trend: EMA 50 > EMA 200
        df['h1_trend_ok'] = df['EMA50_H1'] > df['EMA200_H1']
        
        # 3. Session Window (08:00 - 10:00 UTC) - optimized narrow window
        df['session_active'] = (df.index.hour >= 8) & (df.index.hour <= 10)
        
        # 4. M15 Donchian breakout (close breaks above shifted upper band)
        df['m15_breakout'] = df['close'] > df['DC_upper_20_M15'].shift(1)
        
        # 5. Volatility expansion confirmation (current ATR is 10% higher than its recent SMA)
        df['vol_expansion'] = df['ATR14_M15'] > (1.1 * df['ATR14_M15_SMA'])
        
        # Combined Entry Signal
        df['entry_signal'] = (
            df['h4_trend_ok'] & 
            df['h1_trend_ok'] & 
            df['session_active'] & 
            df['m15_breakout'] &
            df['vol_expansion']
        )
        
        return df
