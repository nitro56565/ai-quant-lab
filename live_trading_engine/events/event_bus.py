"""
Asynchronous Pub/Sub Event Bus Module.
Decouples data streaming, model inference, trade decision, risk auditing, execution, and logging.
"""

from enum import Enum, auto
from typing import Callable, Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class EventType(Enum):
    BAR_CLOSED = auto()
    TICK_UPDATE = auto()
    MODEL_PREDICTION = auto()
    SIGNAL_GENERATED = auto()
    ORDER_REQUEST = auto()
    RISK_AUDIT_PASSED = auto()
    RISK_VETOED = auto()
    ORDER_CREATED = auto()
    ORDER_FILLED = auto()
    POSITION_CLOSED = auto()
    HEARTBEAT_TICK = auto()
    RECONCILIATION_ALERT = auto()


class Event:
    def __init__(self, event_type: EventType, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data
        self.timestamp = data.get("timestamp")

    def __repr__(self):
        return f"<Event {self.event_type.name} at {self.timestamp}>"

class EventBus:
    def __init__(self):
        self._listeners: Dict[EventType, List[Callable[[Event], None]]] = {
            et: [] for et in EventType
        }

    def subscribe(self, event_type: EventType, listener: Callable[[Event], None]):
        """
        Subscribes a callback function to a specific EventType.
        """
        if event_type in self._listeners:
            self._listeners[event_type].append(listener)
            logger.debug(f"Subscribed listener {listener.__name__} to {event_type.name}")

    def publish(self, event: Event):
        """
        Dispatches an Event to all subscribed listeners.
        """
        listeners = self._listeners.get(event.event_type, [])
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error handling event {event.event_type.name} in {listener.__name__}: {e}", exc_info=True)
