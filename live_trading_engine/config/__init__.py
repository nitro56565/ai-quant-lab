"""
Live Trading Configuration Package.
Centralizes parameters for real-time paper trading execution.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict
from live_trading_engine.config.loader import get_config, ConfigLoader

@dataclass
class LiveTradingConfig:
    symbol: str = field(default_factory=lambda: os.getenv("SYMBOL", "EURUSD"))
    secondary_symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "GBPUSD"])
    timeframe: str = "1h"
    broker_type: str = "local"
    initial_capital: float = field(default_factory=lambda: float(os.getenv("INITIAL_CAPITAL", 10000.0)))
    pip_size: float = 0.0001
    default_pip_value: float = 10.0

    # Pre-Trade Risk Limits
    max_daily_drawdown_pct: float = 3.0
    max_open_positions: int = 3
    risk_per_trade_pct: float = field(default_factory=lambda: float(os.getenv("RISK_PER_TRADE_PCT", 1.0)))
    max_holding_hours: int = 24

    # Microstructure Friction Parameters
    latency_ms: int = 300
    slippage_pips: float = 0.30
    commission_per_lot: float = 7.00
    limit_retrace_atr_mult: float = 0.25
    last_look_rejection_rate: float = 0.035

    # Strategy Multipliers
    sl_multiplier: float = 2.0
    tp_multiplier_base: float = 1.8
    tp_multiplier_high_vol: float = 2.4

    # Path Settings
    log_dir: str = field(default_factory=lambda: os.getenv("LOG_DIR", "live_trading_engine/logs"))
    model_dir: str = field(default_factory=lambda: os.getenv("MODEL_DIR", "models/production"))

__all__ = ["LiveTradingConfig", "get_config", "ConfigLoader"]
