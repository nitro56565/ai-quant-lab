"""
Institutional Database & ORM Ledger Module.
Provides SQLite / PostgreSQL relational database management with 50-field schema tracking.
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import logging
import pandas as pd


from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()

class TradeLedger(Base):
    __tablename__ = "trades_ledger"

    # Metadata & Identifiers
    trade_uuid = Column(String(36), primary_key=True)
    trade_id = Column(String(32), index=True, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    symbol = Column(String(16), index=True, nullable=False)
    
    # Execution Microstructure
    direction = Column(String(8), nullable=False) # BUY or SELL
    order_type = Column(String(16), default="LIMIT_RETRACE") # LIMIT_RETRACE or MARKET
    requested_entry = Column(Float, nullable=False)
    filled_entry = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    spread = Column(Float, default=0.0) # pips
    slippage = Column(Float, default=0.0) # pips
    commission = Column(Float, default=0.0) # $ USD drag
    fill_delay_ms = Column(Float, default=300.0) # ms

    # Model AI & Probability Predictions
    probability = Column(Float, nullable=False) # 0.0 to 1.0
    expected_value = Column(Float, nullable=False) # EV net in pips
    confidence = Column(Float, nullable=False) # 0.0 to 1.0
    
    # Market Context & Volatility
    regime = Column(String(16), nullable=False) # BULL, BEAR, RANGE
    atr = Column(Float, nullable=False)
    atr_percentile = Column(Float, nullable=False) # 0.0 to 100.0%
    session = Column(String(16), nullable=False) # LONDON, NY, ASIAN
    weekday = Column(String(8), nullable=False) # MON, TUE, WED, THU, FRI
    news_flag = Column(Integer, default=0) # 1 if high-impact economic news event nearby, 0 otherwise

    # Risk & Sizing
    risk_percent = Column(Float, default=1.0) # % of equity
    position_size = Column(Float, default=1.0) # Standard lots
    holding_time_hours = Column(Float, nullable=False)

    # Realized Performance Metrics
    pnl_usd = Column(Float, nullable=False)
    pnl_pips = Column(Float, nullable=False)
    r_multiple = Column(Float, nullable=False) # Realized R-ratio
    mae_pips = Column(Float, default=0.0) # Maximum Adverse Excursion
    mfe_pips = Column(Float, default=0.0) # Maximum Favorable Excursion

    # Structured Decision Flags (1/0 Boolean integers for fast SQL queries)
    flag_probability_pass = Column(Integer, default=1)
    flag_ev_pass = Column(Integer, default=1)
    flag_macro_pass = Column(Integer, default=1)
    flag_regime_pass = Column(Integer, default=1)
    flag_session_pass = Column(Integer, default=1)
    flag_risk_pass = Column(Integer, default=1)

    # Versioning & Reproducibility Audit Metadata
    model_version = Column(String(64), nullable=False) # e.g. MOD_EURUSD_V1_2026
    feature_version = Column(String(32), nullable=False) # Feature matrix schema hash
    label_version = Column(String(32), default="triple_barrier_v1")
    backtest_version = Column(String(32), default="master_v1.0")
    walk_forward_fold = Column(Integer, default=1)
    prediction_latency_ms = Column(Float, default=15.0) # ms
    pipeline_version = Column(String(32), default="v1.0_production")
    git_commit = Column(String(40), default="certified_v1.0")
    docker_image = Column(String(64), default="ai-quant-lab-paper-trading-daemon:latest")
    
    # Explainability, Microstructure & Raw Broker Audit Logs
    reason_exited = Column(String(32), nullable=False) # TAKE_PROFIT, STOP_LOSS, TIME_LIMIT
    feature_snapshot_json = Column(Text, nullable=True) # Full 104-feature JSON vector
    decision_report_text = Column(Text, nullable=True) # Human-readable decision summary
    actual_broker_trade_log = Column(Text, default="{}")


class CandleLedger(Base):
    __tablename__ = "candles_ledger"

    candle_id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime, index=True, nullable=False)
    symbol = Column(String(16), index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    bid_open = Column(Float, nullable=False)
    bid_high = Column(Float, nullable=False)
    bid_low = Column(Float, nullable=False)
    bid_close = Column(Float, nullable=False)
    ask_open = Column(Float, nullable=False)
    ask_high = Column(Float, nullable=False)
    ask_low = Column(Float, nullable=False)
    ask_close = Column(Float, nullable=False)
    spread_min = Column(Float, nullable=False)
    spread_max = Column(Float, nullable=False)
    tick_volume = Column(Integer, nullable=False)


class PendingOrderLedger(Base):
    __tablename__ = "pending_orders"

    order_id = Column(String(32), primary_key=True)
    symbol = Column(String(16), index=True, nullable=False)
    signal_type = Column(String(8), nullable=False) # BUY or SELL
    status = Column(String(16), default="PENDING_LIMIT")
    signal_time = Column(String(32), nullable=False)
    created_time_dt = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    limit_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_pct = Column(Float, default=0.5)
    atr = Column(Float, default=0.0012)
    expiry_hours = Column(Integer, default=3)


class OpenPositionLedger(Base):
    __tablename__ = "open_positions"

    position_id = Column(String(32), primary_key=True)
    symbol = Column(String(16), index=True, nullable=False)
    type = Column(String(8), nullable=False) # BUY or SELL
    entry_time = Column(String(32), nullable=False)
    entry_dt = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_pct = Column(Float, default=0.5)
    lots = Column(Float, default=1.0)


class DecisionTraceLedger(Base):
    __tablename__ = "decision_trace"


    trace_id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, index=True, nullable=False)
    symbol = Column(String(16), index=True, nullable=False)
    prob_long = Column(Float, nullable=False)
    prob_short = Column(Float, nullable=False)
    ev_long = Column(Float, nullable=False)
    ev_short = Column(Float, nullable=False)
    outcome = Column(String(16), nullable=False)  # EXECUTE, SKIP, REDUCE_RISK, REJECT
    reason = Column(Text, nullable=False)
    feature_pipeline_version = Column(String(32), default="v1.0")
    label_pipeline_version = Column(String(32), default="v1.0")
    config_version = Column(String(32), default="v3.0")
    model_version = Column(String(32), default="MOD_EURUSD_V1_2026")


class EventSourcingLedger(Base):
    __tablename__ = "events_sourcing_ledger"

    event_id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, index=True, nullable=False)
    event_type = Column(String(32), index=True, nullable=False)
    payload_json = Column(Text, nullable=False)


class NotificationLedger(Base):
    __tablename__ = "notifications_ledger"

    notification_id = Column(String(36), primary_key=True)
    trade_id = Column(String(64), index=True, nullable=True)
    decision_trace_id = Column(String(64), index=True, nullable=True)
    timestamp = Column(DateTime, index=True, nullable=False)
    event_type = Column(String(32), index=True, nullable=False)
    status = Column(String(16), nullable=False) # DELIVERED, FAILED, RETRYING
    telegram_message_id = Column(String(64), nullable=True)
    retry_count = Column(Integer, default=0)
    delivery_time_ms = Column(Float, default=0.0)
    payload_text = Column(Text, nullable=False)


class DatabaseManager:

    def __init__(self, db_path: str = "local_data_workspace/databases/institutional_ledger.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        from sqlalchemy import text
        with self.engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE trades_ledger ADD COLUMN actual_broker_trade_log TEXT"))
                conn.commit()
            except Exception:
                pass

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        logger.info(f"🟢 DatabaseManager Initialized with SQLite Database at '{db_path}'")


    def insert_trade(self, record: Dict[str, Any]) -> str:
        session = self.SessionLocal()
        try:
            trade_uuid = record.get("trade_uuid") or str(uuid.uuid4())
            dt = record.get("timestamp")
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace(" UTC", ""))
            elif dt is None:
                dt = datetime.now(timezone.utc)

            trade = TradeLedger(
                trade_uuid=trade_uuid,
                trade_id=record.get("trade_id", f"TRD_{trade_uuid[:8]}"),
                timestamp=dt,
                symbol=record.get("symbol", "EURUSD"),
                direction=record.get("direction", "BUY"),
                order_type=record.get("order_type", "LIMIT_RETRACE"),
                requested_entry=float(record.get("requested_entry", 0.0)),
                filled_entry=float(record.get("filled_entry", 0.0)),
                exit_price=float(record.get("exit_price", 0.0)),
                take_profit=float(record.get("take_profit", 0.0)),
                stop_loss=float(record.get("stop_loss", 0.0)),
                spread=float(record.get("spread", 0.12)),
                slippage=float(record.get("slippage", 0.30)),
                commission=float(record.get("commission", 7.00)),
                fill_delay_ms=float(record.get("fill_delay_ms", 300.0)),
                probability=float(record.get("probability", 0.50)),
                expected_value=float(record.get("expected_value", 0.0)),
                confidence=float(record.get("confidence", 0.50)),
                regime=record.get("regime", "RANGE"),
                atr=float(record.get("atr", 0.0010)),
                atr_percentile=float(record.get("atr_percentile", 50.0)),
                session=record.get("session", "NY"),
                weekday=record.get("weekday", "MON"),
                news_flag=int(record.get("news_flag", 0)),
                risk_percent=float(record.get("risk_percent", 1.0)),
                position_size=float(record.get("position_size", 1.0)),
                holding_time_hours=float(record.get("holding_time_hours", 1.0)),
                pnl_usd=float(record.get("pnl_usd", 0.0)),
                pnl_pips=float(record.get("pnl_pips", 0.0)),
                r_multiple=float(record.get("r_multiple", 0.0)),
                mae_pips=float(record.get("mae_pips", 0.0)),
                mfe_pips=float(record.get("mfe_pips", 0.0)),
                flag_probability_pass=int(record.get("flag_probability_pass", 1)),
                flag_ev_pass=int(record.get("flag_ev_pass", 1)),
                flag_macro_pass=int(record.get("flag_macro_pass", 1)),
                flag_regime_pass=int(record.get("flag_regime_pass", 1)),
                flag_session_pass=int(record.get("flag_session_pass", 1)),
                flag_risk_pass=int(record.get("flag_risk_pass", 1)),
                model_version=record.get("model_version", "MOD_EURUSD_V1_2026"),
                feature_version=record.get("feature_version", "a8f9c011e4d"),
                label_version=record.get("label_version", "triple_barrier_v1"),
                backtest_version=record.get("backtest_version", "master_v1.0"),
                walk_forward_fold=int(record.get("walk_forward_fold", 1)),
                prediction_latency_ms=float(record.get("prediction_latency_ms", 15.0)),
                pipeline_version=record.get("pipeline_version", "v1.0_production"),
                git_commit=record.get("git_commit", "certified_v1.0"),
                docker_image=record.get("docker_image", "ai-quant-paper-trading:latest"),
                reason_exited=record.get("reason_exited", "TAKE_PROFIT"),
                feature_snapshot_json=json.dumps(record.get("feature_snapshot", {})),
                decision_report_text=record.get("decision_report_text", ""),
                actual_broker_trade_log=json.dumps(record.get("actual_broker_trade_log", {})) if isinstance(record.get("actual_broker_trade_log"), (dict, list)) else str(record.get("actual_broker_trade_log", ""))
            )

            session.add(trade)
            session.commit()
            return trade_uuid
        except Exception as e:
            session.rollback()
            logger.error(f"Error inserting trade into SQLite ledger: {e}")
            return ""
        finally:
            session.close()

    def save_notification_audit(self, notification_data: Dict[str, Any]) -> str:
        session = self.SessionLocal()
        notif_uuid = str(uuid.uuid4())
        try:
            notif = NotificationLedger(
                notification_id=notif_uuid,
                trade_id=notification_data.get("trade_id", ""),
                decision_trace_id=notification_data.get("decision_trace_id", ""),
                timestamp=datetime.now(timezone.utc),
                event_type=notification_data.get("event_type", "GENERIC"),
                status=notification_data.get("status", "DELIVERED"),
                telegram_message_id=str(notification_data.get("telegram_message_id", "")),
                retry_count=int(notification_data.get("retry_count", 0)),
                delivery_time_ms=float(notification_data.get("delivery_time_ms", 0.0)),
                payload_text=notification_data.get("payload_text", "")
            )
            session.add(notif)
            session.commit()
            return notif_uuid
        except Exception as e:
            session.rollback()
            logger.error(f"Error inserting notification audit into SQLite ledger: {e}")
            return ""
        finally:
            session.close()

    def get_all_trades(self) -> List[Dict[str, Any]]:


        session = self.SessionLocal()
        try:
            trades = session.query(TradeLedger).order_by(TradeLedger.timestamp.asc()).all()
            res = []
            for t in trades:
                res.append({
                    "trade_uuid": t.trade_uuid,
                    "trade_id": t.trade_id,
                    "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if t.timestamp else "",
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "order_type": t.order_type,
                    "requested_entry": t.requested_entry,
                    "filled_entry": t.filled_entry,
                    "exit_price": t.exit_price,
                    "take_profit": t.take_profit,
                    "stop_loss": t.stop_loss,
                    "spread": t.spread,
                    "slippage": t.slippage,
                    "commission": t.commission,
                    "fill_delay_ms": t.fill_delay_ms,
                    "probability": t.probability,
                    "expected_value": t.expected_value,
                    "confidence": t.confidence,
                    "regime": t.regime,
                    "atr": t.atr,
                    "atr_percentile": t.atr_percentile,
                    "session": t.session,
                    "weekday": t.weekday,
                    "news_flag": t.news_flag,
                    "risk_percent": t.risk_percent,
                    "position_size": t.position_size,
                    "holding_time_hours": t.holding_time_hours,
                    "pnl_usd": t.pnl_usd,
                    "pnl_pips": t.pnl_pips,
                    "r_multiple": t.r_multiple,
                    "mae_pips": t.mae_pips,
                    "mfe_pips": t.mfe_pips,
                    "flag_probability_pass": t.flag_probability_pass,
                    "flag_ev_pass": t.flag_ev_pass,
                    "flag_macro_pass": t.flag_macro_pass,
                    "flag_regime_pass": t.flag_regime_pass,
                    "flag_session_pass": t.flag_session_pass,
                    "flag_risk_pass": t.flag_risk_pass,
                    "model_version": t.model_version,
                    "feature_version": t.feature_version,
                    "label_version": t.label_version,
                    "backtest_version": t.backtest_version,
                    "walk_forward_fold": t.walk_forward_fold,
                    "prediction_latency_ms": t.prediction_latency_ms,
                    "pipeline_version": t.pipeline_version,
                    "git_commit": t.git_commit,
                    "docker_image": t.docker_image,
                    "reason_exited": t.reason_exited,
                    "feature_snapshot": json.loads(t.feature_snapshot_json) if t.feature_snapshot_json else {},
                    "decision_report_text": t.decision_report_text,
                    "actual_broker_trade_log": json.loads(t.actual_broker_trade_log) if getattr(t, "actual_broker_trade_log", None) else {}
                })
            return res
        finally:
            session.close()

    def get_trade_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        session = self.SessionLocal()
        try:
            t = session.query(TradeLedger).filter((TradeLedger.trade_id == trade_id) | (TradeLedger.trade_uuid == trade_id)).first()
            if not t:
                return None
            return {
                "trade_uuid": t.trade_uuid,
                "trade_id": t.trade_id,
                "timestamp": t.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if t.timestamp else "",
                "symbol": t.symbol,
                "direction": t.direction,
                "order_type": t.order_type,
                "requested_entry": t.requested_entry,
                "filled_entry": t.filled_entry,
                "exit_price": t.exit_price,
                "take_profit": t.take_profit,
                "stop_loss": t.stop_loss,
                "spread": t.spread,
                "slippage": t.slippage,
                "commission": t.commission,
                "fill_delay_ms": t.fill_delay_ms,
                "probability": t.probability,
                "expected_value": t.expected_value,
                "confidence": t.confidence,
                "regime": t.regime,
                "atr": t.atr,
                "atr_percentile": t.atr_percentile,
                "session": t.session,
                "weekday": t.weekday,
                "news_flag": t.news_flag,
                "risk_percent": t.risk_percent,
                "position_size": t.position_size,
                "holding_time_hours": t.holding_time_hours,
                "pnl_usd": t.pnl_usd,
                "pnl_pips": t.pnl_pips,
                "r_multiple": t.r_multiple,
                "mae_pips": t.mae_pips,
                "mfe_pips": t.mfe_pips,
                "flag_probability_pass": t.flag_probability_pass,
                "flag_ev_pass": t.flag_ev_pass,
                "flag_macro_pass": t.flag_macro_pass,
                "flag_regime_pass": t.flag_regime_pass,
                "flag_session_pass": t.flag_session_pass,
                "flag_risk_pass": t.flag_risk_pass,
                "model_version": t.model_version,
                "feature_version": t.feature_version,
                "label_version": t.label_version,
                "backtest_version": t.backtest_version,
                "walk_forward_fold": t.walk_forward_fold,
                "prediction_latency_ms": t.prediction_latency_ms,
                "pipeline_version": t.pipeline_version,
                "git_commit": t.git_commit,
                "docker_image": t.docker_image,
                "reason_exited": t.reason_exited,
                "feature_snapshot": json.loads(t.feature_snapshot_json) if t.feature_snapshot_json else {},
                "decision_report_text": t.decision_report_text,
                "actual_broker_trade_log": json.loads(t.actual_broker_trade_log) if getattr(t, "actual_broker_trade_log", None) else {}
            }
        finally:
            session.close()

    def save_candle(self, candle: Dict[str, Any]) -> str:
        session = self.SessionLocal()
        try:
            ts = candle.get("timestamp")
            ts_dt = pd.to_datetime(ts).to_pydatetime() if isinstance(ts, (str, pd.Timestamp)) else ts
            candle_id = f"CND_{candle.get('symbol', 'EURUSD')}_{ts_dt.strftime('%Y%m%d%H%M%S')}"

            entry = session.query(CandleLedger).filter(CandleLedger.candle_id == candle_id).first()
            if not entry:
                entry = CandleLedger(
                    candle_id=candle_id,
                    timestamp=ts_dt,
                    symbol=candle.get("symbol", "EURUSD"),
                    open=float(candle.get("open", 0.0)),
                    high=float(candle.get("high", 0.0)),
                    low=float(candle.get("low", 0.0)),
                    close=float(candle.get("close", 0.0)),
                    bid_open=float(candle.get("bid_open", 0.0)),
                    bid_high=float(candle.get("bid_high", 0.0)),
                    bid_low=float(candle.get("bid_low", 0.0)),
                    bid_close=float(candle.get("bid_close", 0.0)),
                    ask_open=float(candle.get("ask_open", 0.0)),
                    ask_high=float(candle.get("ask_high", 0.0)),
                    ask_low=float(candle.get("ask_low", 0.0)),
                    ask_close=float(candle.get("ask_close", 0.0)),
                    spread_min=float(candle.get("spread_min", 0.0)),
                    spread_max=float(candle.get("spread_max", 0.0)),
                    tick_volume=int(candle.get("tick_volume", 1))
                )
                session.add(entry)
                session.commit()
            return candle_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving candle to database: {e}")
            return ""
        finally:
            session.close()

    def save_decision_trace(self, decision_data: Dict[str, Any]) -> str:
        session = self.SessionLocal()
        try:
            trace_id = str(uuid.uuid4())
            ts = decision_data.get("timestamp")
            ts_dt = pd.to_datetime(ts).to_pydatetime() if isinstance(ts, (str, pd.Timestamp)) else datetime.now(timezone.utc)

            trace = DecisionTraceLedger(
                trace_id=trace_id,
                timestamp=ts_dt,
                symbol=decision_data.get("symbol", "EURUSD"),
                prob_long=float(decision_data.get("prob_long", 0.0)),
                prob_short=float(decision_data.get("prob_short", 0.0)),
                ev_long=float(decision_data.get("ev_long", 0.0)),
                ev_short=float(decision_data.get("ev_short", 0.0)),
                outcome=str(decision_data.get("outcome", "SKIP")),
                reason=str(decision_data.get("reason", "")),
                feature_pipeline_version=str(decision_data.get("feature_pipeline_version", "v1.0")),
                label_pipeline_version=str(decision_data.get("label_pipeline_version", "v1.0")),
                config_version=str(decision_data.get("config_version", "v3.0")),
                model_version=str(decision_data.get("model_version", "MOD_EURUSD_V1_2026"))
            )
            session.add(trace)
            session.commit()
            return trace_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving decision trace: {e}")
            return ""
        finally:
            session.close()

    def save_event_sourcing_record(self, event_type: str, payload: Dict[str, Any]) -> str:
        session = self.SessionLocal()
        try:
            event_id = str(uuid.uuid4())
            rec = EventSourcingLedger(
                event_id=event_id,
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                payload_json=json.dumps(payload, default=str)
            )
            session.add(rec)
            session.commit()
            return event_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving event sourcing record: {e}")
            return ""
    def save_pending_order(self, order_dict: Dict[str, Any]):
        session = self.SessionLocal()
        try:
            order_id = str(order_dict.get("order_id"))
            entry = session.query(PendingOrderLedger).filter(PendingOrderLedger.order_id == order_id).first()
            if not entry:
                sig_time = str(order_dict.get("signal_time", ""))
                created_dt = order_dict.get("created_time_dt")
                if isinstance(created_dt, str):
                    created_dt = pd.to_datetime(created_dt).to_pydatetime()
                elif created_dt is None:
                    created_dt = datetime.now(timezone.utc)

                entry = PendingOrderLedger(
                    order_id=order_id,
                    symbol=str(order_dict.get("symbol", "EURUSD")),
                    signal_type=str(order_dict.get("signal_type", "BUY")),
                    status=str(order_dict.get("status", "PENDING_LIMIT")),
                    signal_time=sig_time,
                    created_time_dt=created_dt,
                    limit_price=float(order_dict.get("limit_price", 0.0)),
                    stop_loss=float(order_dict.get("stop_loss", 0.0)),
                    take_profit=float(order_dict.get("take_profit", 0.0)),
                    risk_pct=float(order_dict.get("risk_pct", 0.5)),
                    atr=float(order_dict.get("atr", 0.0012)),
                    expiry_hours=int(order_dict.get("expiry_hours", 3))
                )
                session.add(entry)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving pending order to database: {e}")
        finally:
            session.close()

    def update_order_status(self, order_id: str, new_status: str):
        session = self.SessionLocal()
        try:
            entry = session.query(PendingOrderLedger).filter(PendingOrderLedger.order_id == order_id).first()
            if entry:
                entry.status = new_status
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating order status in database: {e}")
        finally:
            session.close()

    def remove_pending_order(self, order_id: str):
        self.update_order_status(order_id, "FILLED")

    def cancel_pending_order(self, order_id: str, reason: str = "CANCELLED"):
        self.update_order_status(order_id, reason)

    def clear_all_pending_orders(self):
        session = self.SessionLocal()
        try:
            session.query(PendingOrderLedger).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error clearing pending orders from database: {e}")
        finally:
            session.close()

    def get_all_orders_ledger(self) -> List[Dict[str, Any]]:
        session = self.SessionLocal()
        try:
            records = session.query(PendingOrderLedger).order_by(PendingOrderLedger.created_time_dt.desc()).all()
            res = []
            for r in records:
                res.append({
                    "order_id": r.order_id,
                    "symbol": r.symbol,
                    "signal_type": r.signal_type,
                    "status": r.status,
                    "signal_time": r.signal_time,
                    "created_time_dt": r.created_time_dt.strftime("%Y-%m-%d %H:%M:%S UTC") if r.created_time_dt else r.signal_time,
                    "limit_price": r.limit_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "risk_pct": r.risk_pct,
                    "atr": r.atr,
                    "expiry_hours": r.expiry_hours
                })
            return res
        finally:
            session.close()

    def get_active_pending_orders(self) -> List[Dict[str, Any]]:
        session = self.SessionLocal()
        try:
            records = session.query(PendingOrderLedger).filter(PendingOrderLedger.status == "PENDING_LIMIT").all()
            res = []
            for r in records:
                res.append({
                    "order_id": r.order_id,
                    "symbol": r.symbol,
                    "signal_type": r.signal_type,
                    "status": r.status,
                    "signal_time": r.signal_time,
                    "created_time_dt": r.created_time_dt.strftime("%Y-%m-%d %H:%M:%S UTC") if r.created_time_dt else r.signal_time,
                    "limit_price": r.limit_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "risk_pct": r.risk_pct,
                    "atr": r.atr,
                    "expiry_hours": r.expiry_hours
                })
            return res
        finally:
            session.close()


    def save_open_position(self, pos_dict: Dict[str, Any]):
        session = self.SessionLocal()
        try:
            pos_id = str(pos_dict.get("position_id"))
            entry = session.query(OpenPositionLedger).filter(OpenPositionLedger.position_id == pos_id).first()
            if not entry:
                entry_dt = pos_dict.get("entry_dt")
                if isinstance(entry_dt, str):
                    entry_dt = pd.to_datetime(entry_dt).to_pydatetime()
                elif entry_dt is None:
                    entry_dt = datetime.now(timezone.utc)

                entry = OpenPositionLedger(
                    position_id=pos_id,
                    symbol=str(pos_dict.get("symbol", "EURUSD")),
                    type=str(pos_dict.get("type", "BUY")),
                    entry_time=str(pos_dict.get("entry_time", "")),
                    entry_dt=entry_dt,
                    entry_price=float(pos_dict.get("entry_price", 0.0)),
                    stop_loss=float(pos_dict.get("stop_loss", 0.0)),
                    take_profit=float(pos_dict.get("take_profit", 0.0)),
                    risk_pct=float(pos_dict.get("risk_pct", 0.5)),
                    lots=float(pos_dict.get("lots", 1.0))
                )
                session.add(entry)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving open position to database: {e}")
        finally:
            session.close()

    def remove_open_position(self, pos_id: str):
        session = self.SessionLocal()
        try:
            session.query(OpenPositionLedger).filter(OpenPositionLedger.position_id == pos_id).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error removing open position from database: {e}")
        finally:
            session.close()

    def get_active_open_positions(self) -> List[Dict[str, Any]]:
        session = self.SessionLocal()
        try:
            records = session.query(OpenPositionLedger).all()
            res = []
            for r in records:
                res.append({
                    "position_id": r.position_id,
                    "symbol": r.symbol,
                    "type": r.type,
                    "entry_time": r.entry_time,
                    "entry_dt": r.entry_dt,
                    "entry_price": r.entry_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "risk_pct": r.risk_pct,
                    "lots": r.lots
                })
            return res
        finally:
            session.close()


