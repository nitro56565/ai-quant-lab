"""
H1 Bar Guard Component for Market Data Integrity Verification.
Validates incoming H1 candles against:
1. Normal H1 Bar Completion
2. Duplicate Bar Suppression
3. Out-of-Order Bar Detection
4. Missing Bar Gap Detection & Safe Hold Policy
5. Stale Data Rejection
6. Future Timestamp Rejection
7. Malformed OHLC / NaN / Inf Rejection
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

class H1BarGuard:
    def __init__(self, stale_threshold_hours: float = 2.0, future_tolerance_minutes: float = 5.0):
        self.stale_threshold = timedelta(hours=stale_threshold_hours)
        self.future_tolerance = timedelta(minutes=future_tolerance_minutes)
        self.last_processed_timestamp: Optional[datetime] = None
        self.processed_timestamps: set = set()

    def reset(self):
        self.last_processed_timestamp = None
        self.processed_timestamps.clear()

    def validate_bar(self, bar: Dict[str, Any], current_time: Optional[datetime] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates an incoming H1 bar dictionary.
        Expected bar format:
        {
            'timestamp': datetime object or ISO string,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': float or int
        }
        Returns:
            (is_valid: bool, reason_code: str, cleaned_bar: Optional[dict])
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        elif current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # 1. Check Malformed Structure / Missing Keys
        required_keys = ['timestamp', 'open', 'high', 'low', 'close']
        for k in required_keys:
            if k not in bar:
                return False, "MALFORMED_MISSING_KEY", None

        # 2. Parse & Check Timestamp Format
        ts = bar['timestamp']
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return False, "MALFORMED_TIMESTAMP", None
        elif not isinstance(ts, datetime):
            return False, "MALFORMED_TIMESTAMP", None

        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # 3. Check Malformed OHLC Numerical Values (NaN, Inf, Negative, Invalid Bounds)
        try:
            o = float(bar['open'])
            h = float(bar['high'])
            l = float(bar['low'])
            c = float(bar['close'])
            v = float(bar.get('volume', 1.0))
        except (ValueError, TypeError):
            return False, "MALFORMED_NUMERICAL_TYPE", None

        for val in [o, h, l, c, v]:
            if math.isnan(val) or math.isinf(val):
                return False, "MALFORMED_OHLC_NAN_INF", None
            if val < 0:
                return False, "MALFORMED_NEGATIVE_PRICE", None

        # Price Boundary Validation
        if h < l or h < o or h < c or l > o or l > c:
            return False, "MALFORMED_OHLC_BOUNDS", None

        if o == 0 or h == 0 or l == 0 or c == 0:
            return False, "MALFORMED_ZERO_PRICE", None

        # 4. Check Future Timestamp
        if ts > (current_time + self.future_tolerance):
            return False, "FUTURE_TIMESTAMP", None

        # 5. Check Stale Data
        if (current_time - ts) > self.stale_threshold:
            return False, "STALE_DATA", None

        # 6. Check Duplicate Bar
        if ts in self.processed_timestamps:
            return False, "DUPLICATE_BAR", None

        # 7. Check Out-of-Order Bar
        if self.last_processed_timestamp is not None and ts < self.last_processed_timestamp:
            return False, "OUT_OF_ORDER_BAR", None

        # 8. Check Missing Bar Gap
        status_reason = "VALID_H1_BAR"
        if self.last_processed_timestamp is not None:
            gap_seconds = (ts - self.last_processed_timestamp).total_seconds()
            if gap_seconds > 3600.0 * 1.1: # Gap > 1.1 hours (skipped H1 candle)
                status_reason = "VALID_H1_BAR_WITH_MISSING_GAP"

        # Mark as processed
        self.last_processed_timestamp = ts
        self.processed_timestamps.add(ts)

        cleaned_bar = {
            'timestamp': ts,
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume': v,
            'status_reason': status_reason
        }

        return True, status_reason, cleaned_bar
