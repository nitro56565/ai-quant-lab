"""
Risk Guardian Component.
Enforces institutional risk bounds:
1. 0.75% Normal Risk per Trade Sizing
2. Dynamic Equity Scaling (Up & Down)
3. Volatility (ATR) Adaptive Sizing
4. Daily Drawdown Limit Enforcement (PASS / BOUNDARY / BLOCK)
5. Maximum Leverage Limit Enforcement (PASS / BOUNDARY / BLOCK)
6. Aggregate Open Portfolio Risk & Exposure Capping
"""

import math
from typing import Tuple, Dict, Any, Optional

class RiskGuardian:
    def __init__(
        self,
        config: Any = None,
        risk_per_trade_pct: float = 0.0075,
        max_daily_drawdown_pct: float = 0.03, # 3.0% Max Daily DD
        max_leverage: float = 20.0,            # 20:1 Max Leverage
        max_aggregate_exposure_pct: float = 0.05, # 5.0% Max Total Portfolio Risk
        pip_size: float = 0.0001
    ):
        raw_risk = getattr(config, 'risk_per_trade_pct', risk_per_trade_pct) if config else risk_per_trade_pct
        self.risk_per_trade_pct = raw_risk / 100.0 if raw_risk > 0.05 else raw_risk
        self.max_daily_drawdown_pct = max_daily_drawdown_pct / 100.0 if max_daily_drawdown_pct > 0.5 else max_daily_drawdown_pct
        self.max_leverage = max_leverage
        self.max_aggregate_exposure_pct = max_aggregate_exposure_pct / 100.0 if max_aggregate_exposure_pct > 0.5 else max_aggregate_exposure_pct
        self.pip_size = pip_size

    def evaluate_entry_risk(
        self,
        symbol: str,
        current_equity: float,
        open_positions_count: int,
        pending_orders_count: int,
        current_time: Any,
        vol_rank_pct: float = 50.0,
        signal_direction: str = "BUY",
        active_direction: Optional[str] = None,
        atr: float = 0.0012
    ) -> Dict[str, Any]:
        """
        Evaluates trade risk dynamically using true equity and calculated lots.
        """
        if active_direction and active_direction != signal_direction:
            return {'allowed': True, 'action': 'SIGNAL_REVERSAL', 'risk_multiplier': 1.0, 'reason': 'SIGNAL_REVERSAL_ALLOWED'}

        day_str = current_time.strftime("%Y-%m-%d") if hasattr(current_time, 'strftime') else str(current_time)[:10]
        if not hasattr(self, '_current_day_str') or self._current_day_str != day_str or not hasattr(self, '_daily_starting_equity'):
            self._current_day_str = day_str
            self._daily_starting_equity = current_equity

        pos_sizing = self.calculate_position_size(equity=current_equity, atr=atr, atr_sl_mult=1.5)

        is_valid, reason, _ = self.validate_trade_risk(
            equity=current_equity,
            daily_starting_equity=self._daily_starting_equity,
            open_positions_count=open_positions_count,
            open_aggregate_risk_usd=0.0,
            proposed_lots=pos_sizing['lots'],
            proposed_sl_pips=pos_sizing['sl_pips']
        )

        return {
            'allowed': is_valid,
            'reason': reason,
            'risk_multiplier': 1.0 if is_valid else 0.0
        }

    def calculate_position_size(
        self,
        equity: float,
        atr: float,
        atr_sl_mult: float = 1.5,
        risk_multiplier: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates lot size and risk details based on current equity and ATR.
        Formula: Lots = (Equity * Risk_Pct * Risk_Mult) / (SL_Pips * Pip_Value)
        """
        if equity <= 0:
            return {'lots': 0.0, 'risk_usd': 0.0, 'sl_pips': 0.0, 'sl_dist': 0.0}

        sl_dist = atr * atr_sl_mult
        sl_pips = sl_dist / self.pip_size
        if sl_pips <= 0:
            return {'lots': 0.0, 'risk_usd': 0.0, 'sl_pips': 0.0, 'sl_dist': 0.0}

        eff_risk_pct = self.risk_per_trade_pct * risk_multiplier
        risk_usd = equity * eff_risk_pct

        # 1 lot = 100,000 units = $10/pip on EURUSD
        pip_value_per_lot = 10.0
        raw_lots = risk_usd / (sl_pips * pip_value_per_lot)

        # Leverage Check Cap: Units = Lots * 100,000 <= Equity * Max_Leverage
        max_lots_leverage = (equity * self.max_leverage) / 100000.0
        lots = min(raw_lots, max_lots_leverage)

        # Round to 2 decimal places (min 0.01)
        lots_rounded = round(max(0.01, lots), 2)

        return {
            'lots': lots_rounded,
            'raw_lots': raw_lots,
            'risk_usd': risk_usd,
            'sl_pips': sl_pips,
            'sl_dist': sl_dist
        }

    def validate_trade_risk(
        self,
        equity: float,
        daily_starting_equity: float,
        open_positions_count: int,
        open_aggregate_risk_usd: float,
        proposed_lots: float,
        proposed_sl_pips: float
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates trade against Daily DD, Max Leverage, and Aggregate Risk.
        Returns:
            (is_valid: bool, reason_code: str, risk_audit: Optional[dict])
        """
        # 1. Daily Drawdown Limit Check
        daily_pnl = equity - daily_starting_equity
        daily_dd_pct = (abs(daily_pnl) / daily_starting_equity) if daily_pnl < 0 else 0.0

        if daily_dd_pct >= self.max_daily_drawdown_pct:
            return False, "DAILY_DRAWDOWN_LIMIT", {'daily_dd_pct': daily_dd_pct, 'limit': self.max_daily_drawdown_pct}

        # 2. Maximum Leverage Check
        proposed_units = proposed_lots * 100000.0
        proposed_leverage = proposed_units / max(1.0, equity)

        if proposed_leverage > self.max_leverage:
            return False, "MAX_LEVERAGE_EXCEEDED", {'leverage': proposed_leverage, 'limit': self.max_leverage}

        # 3. Aggregate Portfolio Exposure Check
        proposed_risk_usd = proposed_lots * proposed_sl_pips * 10.0  # Full position risk evaluation
        total_aggregate_risk_usd = open_aggregate_risk_usd + proposed_risk_usd
        max_aggregate_risk_usd = equity * self.max_aggregate_exposure_pct

        if total_aggregate_risk_usd > max_aggregate_risk_usd:
            return False, "EXPOSURE_LIMIT_EXCEEDED", {'total_risk_usd': total_aggregate_risk_usd, 'limit_usd': max_aggregate_risk_usd}

        risk_audit = {
            'proposed_lots': proposed_lots,
            'proposed_leverage': proposed_leverage,
            'daily_dd_pct': daily_dd_pct,
            'total_aggregate_risk_usd': total_aggregate_risk_usd
        }

        return True, "RISK_PASS", risk_audit

# Package export alias
PreTradeRiskGuardian = RiskGuardian
