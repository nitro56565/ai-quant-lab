"""
Pre-Trade Risk Guardian Module.
Enforces institutional risk constraints, drawdown limits, session filters, weekend market closure guards, and dynamic position scaling.
"""

from datetime import datetime, timezone
import logging
from live_trading_engine.config import LiveTradingConfig

logger = logging.getLogger(__name__)

class PreTradeRiskGuardian:
    def __init__(self, config: LiveTradingConfig):
        self.config = config
        self.daily_starting_equity = config.initial_capital
        self.last_reset_day = None

    def check_daily_reset(self, current_equity: float, current_time: datetime):
        curr_day = current_time.strftime("%Y-%m-%d")
        if self.last_reset_day != curr_day:
            self.daily_starting_equity = current_equity
            self.last_reset_day = curr_day
            logger.info(f"🛡️ Daily Risk Guardian reset starting equity to ${current_equity:.2f} for {curr_day}")

    def evaluate_entry_risk(self, symbol: str, current_equity: float, open_positions_count: int, 
                            current_time: datetime, vol_rank_pct: float, pending_orders_count: int = 0) -> dict:
        """
        Evaluates whether a new trade signal passes pre-trade risk criteria.
        Returns dict with 'allowed': bool, 'risk_multiplier': float, 'reason': str
        """
        self.check_daily_reset(current_equity, current_time)

        # 0. Weekend Market Closure Guard Check (Forex closed Friday 21:00 UTC to Sunday 21:00 UTC)
        w = current_time.weekday() # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = current_time.hour
        is_weekend = (w == 5) or (w == 4 and hour >= 21) or (w == 6 and hour < 21)
        if is_weekend:
            msg = f"⛔ REJECTED: Weekend market closure (Forex closed Friday 21:00 UTC - Sunday 21:00 UTC)"
            logger.warning(msg)
            return {"allowed": False, "risk_multiplier": 0.0, "reason": msg}

        # 1. Daily Drawdown Circuit Breaker Check
        dd_pct = (self.daily_starting_equity - current_equity) / self.daily_starting_equity * 100.0
        if dd_pct >= self.config.max_daily_drawdown_pct:
            msg = f"⛔ REJECTED: Daily drawdown limit hit ({dd_pct:.2f}% >= {self.config.max_daily_drawdown_pct:.1f}%)"
            logger.warning(msg)
            return {"allowed": False, "risk_multiplier": 0.0, "reason": msg}

        # 2. Duplicate Pending Order or Active Position Check
        total_active = open_positions_count + pending_orders_count
        if total_active >= self.config.max_open_positions:
            msg = f"⛔ REJECTED: Active pending order or open position already exists for {symbol} ({total_active} active)"
            logger.warning(msg)
            return {"allowed": False, "risk_multiplier": 0.0, "reason": msg}

        # 3. Session Filtering Check (Avoid 13:00-16:00 UTC US Open Spikes)
        if hour in [13, 14, 15, 16]:
            msg = f"⛔ REJECTED: Restricted trading window (Hour {hour} UTC)"
            logger.warning(msg)
            return {"allowed": False, "risk_multiplier": 0.0, "reason": msg}

        # 4. Volatility Regime Risk Scaling
        if vol_rank_pct >= 80.0:
            risk_mult = 1.00
        elif vol_rank_pct >= 60.0:
            risk_mult = 0.75
        elif vol_rank_pct >= 40.0:
            risk_mult = 0.50
        else:
            risk_mult = 0.25

        logger.info(f"✅ Pre-Trade Risk Guardian PASSED for {symbol}. Risk Multiplier: {risk_mult:.2f}")
        return {"allowed": True, "risk_multiplier": risk_mult, "reason": "PASSED"}
