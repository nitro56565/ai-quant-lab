import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("SignalEngine")

class SignalEngine:
    """
    Evaluates rule-based signals combining normalized features and classified regimes.
    All strategies are LONG-only to match the original codebase behavior.
    """
    def __init__(self):
        pass

    def evaluate_adaptive_trend(self, df: pd.DataFrame):
        """
        Strategy 1: Adaptive Trend Following
        - Trend Filter (H4): Buy only if EMA50 > EMA200 and H4 ADX > 20.
        - Entry Trigger (H1): Price pulls back to H1 EMA50, bullish candle closes, and H1 ADX > 20.
        """
        signals = np.full(len(df), None, dtype=object)
        
        ema50_h4 = df['feat_trend_ema50_h4'].values
        ema200_h4 = df['feat_trend_ema200_h4'].values
        adx_h4 = df['feat_trend_adx_h4'].values
        
        low = df['low'].values
        close = df['close'].values
        open_p = df['open'].values
        ema50_h1 = df['feat_trend_ema50'].values
        adx_h1 = df['feat_trend_adx'].values
        
        for i in range(1, len(df)):
            # 1. H4 Filter
            h4_filter = (ema50_h4[i] > ema200_h4[i]) & (adx_h4[i] > 20)
            
            # 2. H1 Pullback
            pullback = low[i] <= ema50_h1[i]
            
            # 3. H1 Bullish Close
            bullish_close = (close[i] > open_p[i]) & (close[i] > ema50_h1[i])
            
            # 4. H1 Trend Strength
            h1_strength = adx_h1[i] > 20
            
            if h4_filter and pullback and bullish_close and h1_strength:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 1.0,
            'tp_multiplier': None,
            'trail_multiplier': 1.5
        }
        return signals, config

    def evaluate_pullback_continuation(self, df: pd.DataFrame):
        """
        Strategy 2: Pullback Continuation
        - Trend: EMA50 > EMA200
        - Pullback: Low drops below or touches EMA20
        - Cooler: RSI between 40 and 50
        - Trigger: Bullish Engulfing pattern
        """
        signals = np.full(len(df), None, dtype=object)
        
        ema50 = df['feat_trend_ema50'].values
        ema200 = df['feat_trend_ema200'].values
        ema20 = df['feat_trend_ema20'].values
        low = df['low'].values
        rsi = df['feat_osc_rsi'].values
        close = df['close'].values
        open_p = df['open'].values
        
        for i in range(2, len(df)):
            trend_ok = ema50[i] > ema200[i]
            pullback = low[i] <= ema20[i]
            rsi_ok = (rsi[i] >= 40) & (rsi[i] <= 50)
            
            # Bullish Engulfing
            bullish_curr = close[i] > open_p[i]
            bearish_prev = close[i-1] < open_p[i-1]
            engulfing = (close[i] >= open_p[i-1]) & (open_p[i] <= close[i-1])
            engulfing_ok = bullish_curr & bearish_prev & engulfing
            
            if trend_ok and pullback and rsi_ok and engulfing_ok:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 1.0,
            'tp_multiplier': None,
            'trail_multiplier': 2.0
        }
        return signals, config

    def evaluate_mean_reversion(self, df: pd.DataFrame):
        """
        Strategy 3: Mean Reversion
        - Active only in quiet markets (ADX < 25)
        - Entry: Close < lower BB, RSI < 30
        """
        signals = np.full(len(df), None, dtype=object)
        
        adx = df['feat_trend_adx'].values
        close = df['close'].values
        bb_lower = df['feat_vol_bb_lower'].values
        rsi = df['feat_osc_rsi'].values
        
        for i in range(1, len(df)):
            quiet_market = adx[i] < 25
            below_bb = close[i] < bb_lower[i]
            oversold = rsi[i] < 30
            
            if quiet_market and below_bb and oversold:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 1.5,
            'tp_multiplier': None, # Managed by BB Mid Custom Exit
            'trail_multiplier': 999.0 # Effectively disabled
        }
        return signals, config

    def evaluate_volatility_breakout(self, df: pd.DataFrame):
        """
        Strategy 4: Volatility Breakout
        - Trend Filter: Close > EMA200
        - Volatility Squeeze: BB width < BB width SMA50 in last 5 bars
        - Volatility Expansion: ATR > SMA5 of ATR
        - Entry Trigger: Close > shifted Donchian Upper Channel
        """
        signals = np.full(len(df), None, dtype=object)
        
        close = df['close'].values
        ema200 = df['feat_trend_ema200'].values
        squeeze = df['feat_vol_squeeze'].values
        atr = df['feat_vol_atr'].values
        atr_sma5 = df['feat_vol_atr_sma5'].values
        channel_upper = df['feat_price_channel_upper'].values
        
        for i in range(5, len(df)):
            uptrend = close[i] > ema200[i]
            squeeze_recent = any(squeeze[i-k] for k in range(0, 5))
            vol_expansion = atr[i] > atr_sma5[i]
            donchian_breakout = close[i] > channel_upper[i-1]
            
            if uptrend and squeeze_recent and vol_expansion and donchian_breakout:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 2.0,
            'tp_multiplier': None,
            'trail_multiplier': 4.0
        }
        return signals, config

    def evaluate_london_momentum(self, df: pd.DataFrame):
        """
        Strategy 5: London Session Momentum
        - Trading Window: London Open (08:00 to 10:00 UTC)
        - Trend Filters (Multi-timeframe):
          * H4: EMA50 > EMA200
          * H1: EMA50 > EMA200
        - Volatility Expansion: ATR > 1.1 * ATR SMA
        - Trigger: Close breaks above shifted Donchian Upper Channel
        """
        signals = np.full(len(df), None, dtype=object)
        
        ema50_h4 = df['feat_trend_ema50_h4'].values
        ema200_h4 = df['feat_trend_ema200_h4'].values
        
        ema50_h1 = df['feat_trend_ema50_h1'].values
        ema200_h1 = df['feat_trend_ema200_h1'].values
        
        session_active = df['feat_session_london_open'].values
        close = df['close'].values
        channel_upper = df['feat_price_channel_upper'].values
        
        atr = df['feat_vol_atr'].values
        atr_sma = df['feat_vol_atr_sma'].values
        
        for i in range(1, len(df)):
            h4_trend_ok = ema50_h4[i] > ema200_h4[i]
            h1_trend_ok = ema50_h1[i] > ema200_h1[i]
            time_ok = session_active[i] == 1
            breakout = close[i] > channel_upper[i-1]
            vol_expansion = atr[i] > (1.1 * atr_sma[i])
            
            if h4_trend_ok and h1_trend_ok and time_ok and breakout and vol_expansion:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 1.5,
            'tp_multiplier': None,
            'trail_multiplier': 4.0
        }
        return signals, config

    def evaluate_adaptive_momentum_pullback(self, df: pd.DataFrame):
        """
        Strategy: Adaptive Momentum Pullback (AMP)
        Scoring-based trend pullback execution.
        """
        signals = np.full(len(df), None, dtype=object)
        
        atr_pct = df['feat_vol_atr_pct'].values
        london_open = df['feat_session_london_open'].values
        trend_score = df['feat_trend_score'].values
        pullback_depth = df['feat_price_pullback_depth'].values
        breakout_dist = df['feat_price_breakout_distance'].values
        atr = df['feat_vol_atr'].values
        
        # Volume rolling average proxy
        volume = df['volume'].values if 'volume' in df.columns else np.ones(len(df))
        volume_sma = pd.Series(volume).rolling(window=20).mean().values
        
        for i in range(1, len(df)):
            # Step 1: Market Tradability filter
            if atr_pct[i] < 30.0:
                continue
            if london_open[i] != 1:
                continue
                
            # Step 2: Regime Check
            if trend_score[i] < 45.0:
                continue
                
            # Step 4: Volatility Filter
            if not (40.0 <= atr_pct[i] <= 85.0):
                continue
                
            # Step 9: Scoring System
            score = 0
            
            # Trend Score > 70: +20 points
            if trend_score[i] > 70.0:
                score += 20
                
            # Pullback Quality (30% to 50% pullback): +20 points
            if 0.30 <= pullback_depth[i] <= 0.50:
                score += 20
                
            # Breakout Strength (Breakout >= 0.25 * ATR): +15 points
            if breakout_dist[i] >= 0.25 * atr[i]:
                score += 15
                
            # Volatility range OK: +15 points
            if 40.0 <= atr_pct[i] <= 85.0:
                score += 15
                
            # London Session: +10 points
            if london_open[i] == 1:
                score += 10
                
            # Volume > SMA: +10 points
            if volume[i] > volume_sma[i]:
                score += 10
                
            # Spread OK proxy: +10 points
            score += 10
            
            # Entry Trigger: Score > 80
            if score > 80:
                signals[i] = 'BUY'
                
        config = {
            'sl_multiplier': 1.3,
            'tp_multiplier': None,
            'trail_multiplier': 1.3
        }
        return signals, config
