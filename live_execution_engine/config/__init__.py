"""
Live Trading Configuration Package.
Centralizes parameters for real-time paper trading execution.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict
from live_execution_engine.config.loader import get_config, ConfigLoader

@dataclass
class LiveTradingConfig:
    symbol: str = field(default_factory=lambda: os.getenv("SYMBOL", "EURUSD"))
    secondary_symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "GBPUSD"])
    timeframe: str = "1h"
    broker_type: str = "local"
    initial_capital: float = field(default_factory=lambda: float(os.getenv("INITIAL_CAPITAL", 10000.0)))
    pip_size: float = 0.0001
    default_pip_value: float = 10.0

    # Three Distinct System Clocks (Explicit Specifications)
    signal_evaluation_timeframe: str = "1h"    # Clock 1: Signal Evaluation Horizon (1 Bar = 1 Hour)
    pending_order_expiry_hours: int = 3        # Clock 2: Pending Limit Order Expiry Lifetime (3 Hours)
    max_holding_hours: int = 36                # Clock 3: Maximum Filled Trade Holding Limit (36 Hours Certified Limit)

    # Pre-Trade Risk Limits (Strict Baseline v3.0 Parity)
    max_daily_drawdown_pct: float = 3.0
    max_open_positions: int = 3   # Up to 3 active overlapping positions (Certified Baseline v3.0)
    max_leverage: float = 20.0
    risk_per_trade_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PER_TRADE_PCT", 0.75)))

    latency_ms: int = 300
    slippage_pips: float = 0.30
    commission_per_lot: float = 7.00
    limit_retrace_atr_mult: float = 0.0
    last_look_rejection_rate: float = 0.035

    # Strategy Multipliers
    sl_multiplier: float = 1.5
    tp_multiplier_base: float = 3.0
    tp_multiplier_high_vol: float = 3.0

    # Path Settings
    log_dir: str = field(default_factory=lambda: os.getenv("LOG_DIR", "live_execution_engine/logs"))
    model_dir: str = field(default_factory=lambda: os.getenv("MODEL_DIR", "trained_model_artifacts/production_deployment"))

__all__ = ["LiveTradingConfig", "get_config", "ConfigLoader"]
