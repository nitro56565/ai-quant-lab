"""
Scheduler Daemon Module v3.0.
Centralized timing and cron manager for bar closes, heartbeats, daily reports, and weekend shutdowns.
"""

import time
from datetime import datetime, timezone
import logging
from typing import Callable, List

logger = logging.getLogger(__name__)

class SchedulerDaemon:
    def __init__(self, heartbeat_sec: int = 60, weekend_shutdown: bool = True):
        self.heartbeat_sec = heartbeat_sec
        self.weekend_shutdown = weekend_shutdown
        self.last_heartbeat = 0.0
        self.last_daily_report_day = None
        self.registered_tasks: List[Callable] = []
        logger.info(f"🟢 Scheduler Daemon Initialized (Heartbeat: {heartbeat_sec}s, Weekend Shutdown: {weekend_shutdown})")

    def is_weekend(self, dt: datetime = None) -> bool:
        """
        Checks if global FX market is closed for weekend (Friday 22:00 UTC to Sunday 22:00 UTC).
        """
        if not self.weekend_shutdown:
            return False
        dt = dt or datetime.now(timezone.utc)
        weekday = dt.weekday() # 4=Friday, 5=Saturday, 6=Sunday
        hour = dt.hour

        if weekday == 4 and hour >= 22:
            return True
        if weekday == 5:
            return True
        if weekday == 6 and hour < 22:
            return True
        return False

    def check_schedule(self, current_dt: datetime, on_heartbeat_cb: Callable = None, on_daily_report_cb: Callable = None):
        """
        Evaluates timing schedules on every bar/tick step.
        """
        now = time.time()

        # Heartbeat check
        if now - self.last_heartbeat >= self.heartbeat_sec:
            self.last_heartbeat = now
            if on_heartbeat_cb:
                on_heartbeat_cb()

        # Daily Report check (At 00:00 UTC)
        today_str = current_dt.strftime("%Y-%m-%d")
        if self.last_daily_report_day != today_str and current_dt.hour == 0:
            self.last_daily_report_day = today_str
            if on_daily_report_cb:
                logger.info(f"📄 Triggering Automated Daily Report for {today_str}...")
                on_daily_report_cb("daily")
