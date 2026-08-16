"""
Thread-Safe Ring Buffer v3.0.
High-throughput buffer for incoming tick streams with configurable capacity.
"""

import threading
from collections import deque
from typing import Dict, Any, List

class TickBuffer:
    """
    Thread-safe Ring Buffer for real-time tick ingestion.
    """
    def __init__(self, maxlen: int = 50000):
        self._buffer = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, tick: Dict[str, Any]):
        """
        Pushes a tick object into ring buffer.
        """
        with self._lock:
            self._buffer.append(tick)

    def pop_all(self) -> List[Dict[str, Any]]:
        """
        Thread-safely pops and returns all buffered ticks.
        """
        with self._lock:
            ticks = list(self._buffer)
            self._buffer.clear()
            return ticks

    def peek(self) -> List[Dict[str, Any]]:
        """
        Returns a copy of buffered ticks without clearing.
        """
        with self._lock:
            return list(self._buffer)

    def __len__(self):
        with self._lock:
            return len(self._buffer)
