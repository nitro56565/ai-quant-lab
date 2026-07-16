import numpy as np

class PositionSizer:
    """
    PositionSizer implements industry-standard position sizing algorithms
    used by professional quants and portfolio managers.
    """
    def __init__(self, account_equity=10000.0, pip_value_standard_lot=10.0):
        """
        Initialize the sizer with account parameters.
        
        Args:
            account_equity: Current total account equity in USD.
            pip_value_standard_lot: The USD value of 1 pip for 1 standard lot (100,000 units).
                                     Default is 10.0 USD (applies to EURUSD, GBPUSD, etc.).
        """
        self.account_equity = account_equity
        self.pip_value_standard_lot = pip_value_standard_lot

    def fixed_lot(self, lots=0.1) -> float:
        """Fixed Lot sizing: Returns a static number of lots."""
        return round(float(lots), 2)

    def fixed_fractional(self, risk_percent: float, stop_loss_pips: float) -> float:
        """
        Fixed Fractional position sizing: Risks a fixed percentage of account equity per trade.
        
        Formula:
            Lot Size = (Equity * Risk%) / (StopLossPips * PipValuePerLot)
        """
        if stop_loss_pips <= 0:
            raise ValueError("Stop loss in pips must be positive.")
            
        dollar_risk = self.account_equity * (risk_percent / 100.0)
        lots = dollar_risk / (stop_loss_pips * self.pip_value_standard_lot)
        return round(max(lots, 0.01), 2)

    def atr_volatility_adjusted(self, risk_percent: float, atr: float, atr_multiplier: float, pip_size: float = 0.0001) -> float:
        """
        ATR-Based Volatility Adjusted Sizing:
        The gold standard for trend followers. Scales the stop loss (and position size)
        inversely with the market's volatility (ATR).
        
        Formula:
            Stop Loss Pips = (ATR * ATR_Multiplier) / PipSize
            Lot Size = (Equity * Risk%) / (Stop Loss Pips * PipValuePerLot)
        """
        if atr <= 0:
            raise ValueError("ATR must be greater than zero.")
            
        stop_loss_price = atr * atr_multiplier
        stop_loss_pips = stop_loss_price / pip_size
        
        return self.fixed_fractional(risk_percent, stop_loss_pips)

    def kelly_criterion(self, win_rate: float, win_loss_ratio: float, kelly_fraction: float = 0.1) -> float:
        """
        Kelly Criterion Sizing:
        Calculates optimal trade fraction to maximize geometric growth rate.
        Recommended to use a fractional multiplier (e.g. 0.1 or 0.25) to avoid over-leverage.
        
        Formula:
            Kelly % = Win_Rate - (1 - Win_Rate) / Win_Loss_Ratio
            Optimal Risk % = Kelly % * kelly_fraction
        """
        if win_loss_ratio <= 0:
            return 0.0
            
        w = win_rate / 100.0 if win_rate > 1.0 else win_rate
        kelly = w - (1 - w) / win_loss_ratio
        
        # Clip to positive (don't trade if Kelly is negative)
        kelly = max(kelly, 0.0)
        
        # Apply fractional Kelly
        risk_percent = kelly * kelly_fraction * 100.0
        return round(risk_percent, 2)
