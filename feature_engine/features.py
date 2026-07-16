import pandas as pd
import numpy as np

def calculate_ema(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
    """Calculate Exponential Moving Average (EMA)."""
    return df[column].ewm(span=period, adjust=False).mean()


def calculate_sma(df: pd.DataFrame, period: int, column: str = 'close') -> pd.Series:
    """Calculate Simple Moving Average (SMA)."""
    return df[column].rolling(window=period).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.Series:
    """Calculate Relative Strength Index (RSI)."""
    delta = df[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: float = 2.0, column: str = 'close'):
    """Calculate Bollinger Bands (Upper, Lower, SMA, Width)."""
    sma = df[column].rolling(window=period).mean()
    std = df[column].rolling(window=period).std()
    
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    width = (upper - lower) / sma.replace(0, 1e-9)
    
    return upper, lower, sma, width


def calculate_adx(df: pd.DataFrame, period: int = 14):
    """Calculate Average Directional Index (ADX)."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    up_move = high.diff()
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)
    
    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean().replace(0, 1e-9)
    
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    adx = dx.rolling(window=period).mean()
    
    return adx, plus_di, minus_di


# =====================================================================
# 🌟 PRICE STRUCTURE FEATURES (⭐5)
# =====================================================================
def compute_higher_highs_lows(df: pd.DataFrame, window: int = 20):
    """
    Identifies higher highs and higher lows to define market structure.
    Returns boolean columns indicating if the current swing points are rising.
    """
    rolling_max = df['high'].rolling(window=window, min_periods=1).max()
    rolling_min = df['low'].rolling(window=window, min_periods=1).min()
    
    # Shifted to get prior swing levels
    prev_max = rolling_max.shift(window)
    prev_min = rolling_min.shift(window)
    
    higher_high = rolling_max > prev_max
    higher_low = rolling_min > prev_min
    
    return higher_high, higher_low


def compute_pullback_depth(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Measures current price position relative to recent high-low swing range.
    Values close to 0.0 mean near high, 1.0 means near low (deep pullback).
    """
    rolling_max = df['high'].rolling(window=window, min_periods=1).max()
    rolling_min = df['low'].rolling(window=window, min_periods=1).min()
    
    range_span = rolling_max - rolling_min
    pullback_depth = (rolling_max - df['close']) / range_span.replace(0, 1e-9)
    return pullback_depth.clip(0.0, 1.0)


def compute_breakout_strength(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Measures distance price has broken out past Donchian Upper Channel.
    Normalized by ATR to measure breakout intensity.
    """
    donchian_upper = df['high'].shift(1).rolling(window=window).max()
    atr = calculate_atr(df, 14).replace(0, 1e-9)
    
    strength = (df['close'] - donchian_upper) / atr
    return strength


# =====================================================================
# 🌟 SESSION & LIQUIDITY FEATURES (⭐5)
# =====================================================================
def compute_session_flags(df: pd.DataFrame):
    """
    Computes session flags based on UTC timestamps.
    London Open: 08:00 - 10:00 UTC
    NY Overlap: 12:00 - 16:00 UTC
    """
    hours = df.index.hour
    london_open = (hours >= 8) & (hours <= 10)
    ny_overlap = (hours >= 12) & (hours <= 16)
    return london_open.astype(int), ny_overlap.astype(int)


def compute_tick_density(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Measures current volume (ticks) compared to its rolling average.
    Values > 1.0 indicate expanding liquidity.
    """
    if 'volume' not in df.columns:
        return pd.Series(1.0, index=df.index)
    
    avg_vol = df['volume'].rolling(window=window).mean().replace(0, 1e-9)
    return df['volume'] / avg_vol


# =====================================================================
# 🌟 VOLATILITY FEATURES (⭐4)
# =====================================================================
def compute_atr_percentile(df: pd.DataFrame, period: int = 14, lookback: int = 252) -> pd.Series:
    """Rank current ATR against the last year (252 bars) of history (0 to 100)."""
    atr = calculate_atr(df, period)
    # Rolling rank from 0.0 to 1.0
    rank = atr.rolling(window=lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5,
        raw=True
    )
    return rank * 100.0


def compute_volatility_squeeze(df: pd.DataFrame, short_p: int = 20, long_p: int = 100) -> pd.Series:
    """
    Ratio of short-term BB width to long-term average BB width.
    Values < 0.8 indicate a volatility squeeze (potential breakout setup).
    """
    _, _, _, bb_width_short = calculate_bollinger_bands(df, short_p)
    bb_width_long = bb_width_short.rolling(window=long_p).mean().replace(0, 1e-9)
    return bb_width_short / bb_width_long


# =====================================================================
# 🌟 TREND FEATURES (⭐4)
# =====================================================================
def compute_ema_slope(df: pd.DataFrame, period: int = 50, lookback: int = 5) -> pd.Series:
    """
    Slope of the EMA over the last few bars, normalized by ATR to make it
    comparable across different assets/volatility regimes.
    """
    ema = calculate_ema(df, period)
    atr = calculate_atr(df, 14).replace(0, 1e-9)
    
    change = ema - ema.shift(lookback)
    slope = change / (lookback * atr)
    return slope


def compute_trend_persistence(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Kaufman Efficiency Ratio: Net change / Total path movement.
    Value of 1.0 means perfect linear trend, 0.0 means complete chop.
    """
    close = df['close']
    net_change = (close - close.shift(period)).abs()
    path_movement = close.diff().abs().rolling(window=period).sum().replace(0, 1e-9)
    return net_change / path_movement


def find_swings(highs: np.ndarray, lows: np.ndarray, window: int = 5):
    """
    Lookahead-bias-free Swing High and Swing Low detection.
    Returns array of last confirmed swing high and last confirmed swing low.
    """
    swing_highs = np.zeros(len(highs))
    swing_lows = np.zeros(len(lows))
    
    last_sh = highs[0] if len(highs) > 0 else 0.0
    last_sl = lows[0] if len(lows) > 0 else 0.0
    
    for i in range(2 * window, len(highs)):
        # Check if i - window is a swing high
        is_sh = True
        val_h = highs[i - window]
        for k in range(1, window + 1):
            if highs[i - window - k] >= val_h or highs[i - window + k] > val_h:
                is_sh = False
                break
        if is_sh:
            last_sh = val_h
        swing_highs[i] = last_sh
        
        # Check if i - window is a swing low
        is_sl = True
        val_l = lows[i - window]
        for k in range(1, window + 1):
            if lows[i - window - k] <= val_l or lows[i - window + k] < val_l:
                is_sl = False
                break
        if is_sl:
            last_sl = val_l
        swing_lows[i] = last_sl
        
    # Fill initial warmup period
    if len(highs) > 2 * window:
        first_sh = swing_highs[2 * window]
        first_sl = swing_lows[2 * window]
        swing_highs[:2 * window] = first_sh
        swing_lows[:2 * window] = first_sl
    
    return swing_highs, swing_lows


def compute_pullback_features(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, 
                              swing_highs: np.ndarray, swing_lows: np.ndarray):
    """
    Lookahead-bias-free pullback depth and breakout distance calculation.
    """
    pullback_depths = np.zeros(len(closes))
    breakout_distances = np.zeros(len(closes))
    
    for i in range(1, len(closes)):
        sh = swing_highs[i]
        sl = swing_lows[i]
        
        # Current close relative to last confirmed swing high (Breakout Distance)
        breakout_distances[i] = closes[i] - sh
        
        # Impulse height (high reached since swing low)
        idx_start = i
        while idx_start > 0 and swing_lows[idx_start] == sl:
            idx_start -= 1
        
        if idx_start < i:
            max_high = np.max(highs[idx_start:i+1])
            impulse_height = max_high - sl
            if impulse_height > 0:
                # Distance from peak high to current bar low (maximum pullback depth reached)
                retracement = max_high - lows[i]
                pullback_depths[i] = retracement / impulse_height
                
    return pullback_depths, breakout_distances
