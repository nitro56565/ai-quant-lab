"""
Live Trading Engine v3.0 Master Package.
Decoupled 5-stage execution pipeline with decision engine, Prometheus metrics, and state recovery.
"""

from live_trading_engine.config import get_config, ConfigLoader, LiveTradingConfig
from live_trading_engine.persistence.database import DatabaseManager, TradeLedger
from live_trading_engine.events.event_bus import EventBus, Event, EventType
from live_trading_engine.data.streamer import RealTimeDataStreamer
from live_trading_engine.models.signal_engine import SignalEngine
from live_trading_engine.models.model_runner import ModelRunner
from live_trading_engine.decision.decision_engine import DecisionEngine, DecisionOutcome
from live_trading_engine.decision.trade_decision import TradeDecisionEngine, TradeDecisionReason
from live_trading_engine.risk.risk_guardian import PreTradeRiskGuardian
from live_trading_engine.execution.order_manager import OrderManager
from live_trading_engine.execution.reconciler import DailyMidnightReconciler
from live_trading_engine.broker.local_paper import LocalPaperBroker
from live_trading_engine.persistence.state_recovery import StateRecoveryEngine
from live_trading_engine.persistence.prediction_ledger import PredictionLedger
from live_trading_engine.monitoring.metrics import get_metrics_exporter, PrometheusMetricsExporter
from live_trading_engine.monitoring.heartbeat import SystemHeartbeatMonitor
from live_trading_engine.monitoring.kill_switch import EmergencyKillSwitch
from live_trading_engine.monitoring.telegram_notifier import TelegramNotifier
from live_trading_engine.scheduler.scheduler import SchedulerDaemon


__all__ = [
    "get_config",
    "ConfigLoader",
    "LiveTradingConfig",
    "DatabaseManager",
    "TradeLedger",
    "EventBus",
    "Event",
    "EventType",
    "RealTimeDataStreamer",
    "SignalEngine",
    "ModelRunner",
    "DecisionEngine",
    "DecisionOutcome",
    "TradeDecisionEngine",
    "TradeDecisionReason",
    "PreTradeRiskGuardian",
    "OrderManager",
    "DailyMidnightReconciler",
    "LocalPaperBroker",
    "StateRecoveryEngine",
    "PredictionLedger",
    "get_metrics_exporter",
    "PrometheusMetricsExporter",
    "SystemHeartbeatMonitor",
    "EmergencyKillSwitch",
    "SchedulerDaemon",
    "TelegramNotifier"
]

