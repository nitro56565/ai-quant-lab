"""
Prometheus Metrics Exporter Module v3.0.
Tracks quantitative performance, prediction latency, order fill delays, and system health metrics.
"""

import time
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MetricsExporter:
    def __init__(self):
        self.metrics = {
            "prediction_latency_ms": 0.0,
            "db_write_latency_ms": 0.0,
            "order_fill_delay_ms": 0.0,
            "total_trades_count": 0,
            "realized_pnl_usd": 0.0,
            "current_drawdown_pct": 0.0,
            "heartbeat_timestamp": time.time()
        }
        logger.info("🟢 Prometheus Metrics Exporter Initialized")

    def record_prediction_latency(self, latency_ms: float):
        self.metrics["prediction_latency_ms"] = latency_ms

    def record_db_write_latency(self, latency_ms: float):
        self.metrics["db_write_latency_ms"] = latency_ms

    def record_trade(self, pnl_usd: float, drawdown_pct: float):
        self.metrics["total_trades_count"] += 1
        self.metrics["realized_pnl_usd"] += pnl_usd
        self.metrics["current_drawdown_pct"] = drawdown_pct

    def record_heartbeat(self):
        self.metrics["heartbeat_timestamp"] = time.time()

    def generate_prometheus_format(self) -> str:
        """
        Generates standard Prometheus text exposition format.
        """
        lines = [
            "# HELP quant_prediction_latency_ms ML prediction inference latency in milliseconds",
            "# TYPE quant_prediction_latency_ms gauge",
            f"quant_prediction_latency_ms {self.metrics['prediction_latency_ms']:.2f}",
            "# HELP quant_db_write_latency_ms SQLite database write latency in milliseconds",
            "# TYPE quant_db_write_latency_ms gauge",
            f"quant_db_write_latency_ms {self.metrics['db_write_latency_ms']:.2f}",
            "# HELP quant_trades_total Total count of closed paper trades",
            "# TYPE quant_trades_total counter",
            f"quant_trades_total {self.metrics['total_trades_count']}",
            "# HELP quant_realized_pnl_usd Total cumulative realized paper PnL in USD",
            "# TYPE quant_realized_pnl_usd gauge",
            f"quant_realized_pnl_usd {self.metrics['realized_pnl_usd']:.2f}",
            "# HELP quant_current_drawdown_pct Current daily drawdown percentage",
            "# TYPE quant_current_drawdown_pct gauge",
            f"quant_current_drawdown_pct {self.metrics['current_drawdown_pct']:.4f}",
            "# HELP quant_heartbeat_timestamp_seconds Last heartbeat timestamp",
            "# TYPE quant_heartbeat_timestamp_seconds gauge",
            f"quant_heartbeat_timestamp_seconds {self.metrics['heartbeat_timestamp']:.2f}"
        ]
        return "\n".join(lines) + "\n"

_metrics_instance = None

def get_metrics_exporter() -> MetricsExporter:
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsExporter()
    return _metrics_instance

PrometheusMetricsExporter = MetricsExporter

