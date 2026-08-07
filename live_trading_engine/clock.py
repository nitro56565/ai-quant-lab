"""
System Clock Abstraction Module — AI Quant Lab v5.0.
Provides unified BaseClock interface with RealClock (live production) and ReplayClock (historical backtest/replay).
Guarantees 100% identical code execution paths across Backtesting, Forensic Replay, Paper Trading, and Live Trading.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta

class BaseClock(ABC):
    """
    Abstract Clock Interface for deterministic time querying.
    """
    @abstractmethod
    def now(self) -> datetime:
        """Returns current datetime in UTC timezone."""
        pass

class RealClock(BaseClock):
    """
    Live Production Clock returning actual system UTC time.
    """
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

class ReplayClock(BaseClock):
    """
    Simulated Replay Clock for historical backtest & forensic replay execution.
    """
    def __init__(self, initial_time: datetime = None):
        self._current_time = initial_time or datetime.now(timezone.utc)
        if getattr(self._current_time, "tzinfo", None) is None:
            self._current_time = self._current_time.replace(tzinfo=timezone.utc)

    def set_time(self, new_time: datetime):
        if getattr(new_time, "tzinfo", None) is None:
            new_time = new_time.replace(tzinfo=timezone.utc)
        self._current_time = new_time

    def advance_seconds(self, seconds: float):
        self._current_time += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self._current_time
