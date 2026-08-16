#!/usr/bin/env python3
"""
Master Production Live Paper Trading Daemon v3.0 — 24/7 Engine
Runs real-time paper trading loop with live OANDA H1 candle sync, Pre-Trade Risk Guardian, Local Paper Broker, Telegram alerts, and SQLite audit ledgers.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.events import EventBus, Event, EventType
from live_execution_engine.persistence.database import DatabaseManager
from live_execution_engine.models import SignalEngine
from live_execution_engine.decision import DecisionEngine
from live_execution_engine.risk import PreTradeRiskGuardian
from live_execution_engine.execution.order_manager import OrderManager
from live_execution_engine.broker.local_paper import LocalPaperBroker
from live_execution_engine.data import RealTimeDataStreamer
from live_execution_engine.monitoring.telegram_notifier import TelegramNotifier
from live_execution_engine.monitoring.metrics import get_metrics_exporter

from live_execution_engine.clock import RealClock
from live_execution_engine.data.oanda_provider import OANDAMarketDataProvider
from live_execution_engine.broker import ExecutionSimulator, LocalPaperBroker, OANDALiveBrokerGateway

# IST Timezone Helper
def format_ist_utc():
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
    return f"{now_ist.strftime('%Y-%m-%d %H:%M:%S IST')} [{now_utc.strftime('%H:%M:%S UTC')}]"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - INFO - [%(message)s]")
logger = logging.getLogger("InstitutionalPaperTradingDaemon")

def main():
    broker_mode = os.getenv("OANDA_BROKER_TYPE", "LOCAL_SIMULATOR").upper()
    print("=================================================================================")
    print(f"  🚀 STARTING INSTITUTIONAL LIVE PAPER TRADING DAEMON v5.0 — EURUSD")
    print(f"  Broker Gateway: {broker_mode} | Initial Capital: $10,000.00")
    print(f"  Data Adapter: DECOUPLED OANDA MARKET DATA PROVIDER | Clock: REAL UTC CLOCK")
    print("=================================================================================\n")

    config = LiveTradingConfig()
    clock = RealClock()
    provider = OANDAMarketDataProvider(clock=clock)

    db_manager = DatabaseManager("live_execution_engine/logs/institutional_ledger.db")
    event_bus = EventBus()

    # Metrics & Telegram
    metrics = get_metrics_exporter()
    telegram = TelegramNotifier(event_bus=event_bus, db=db_manager)

    # Core Pipeline & Execution Layer
    signal_engine = SignalEngine(event_bus=event_bus, model_dir="trained_model_artifacts/production_deployment")
    decision_engine = DecisionEngine(event_bus=event_bus, db_manager=db_manager)
    risk_guardian = PreTradeRiskGuardian(config=config)
    order_manager = OrderManager(config=config, clock=clock)

    from live_execution_engine.execution.simulation_execution_engine import SimulationExecutionEngine
    from live_execution_engine.execution.oanda_execution_engine import OANDAExecutionEngine

    if broker_mode in ["OANDA_PRACTICE", "OANDA_LIVE", "OANDA"]:
        broker = OANDAExecutionEngine(config=config, order_manager=order_manager, clock=clock, event_bus=event_bus)
        logger.info("🟢 Registered OANDAExecutionEngine: Production OANDA v20 REST API Execution Active (Broker-Authoritative Events Only).")
    else:
        broker = SimulationExecutionEngine(config=config, order_manager=order_manager)
        logger.info("🟢 Registered SimulationExecutionEngine: Orders executed in high-fidelity local paper simulator.")

    streamer = RealTimeDataStreamer(symbol=config.symbol, timeframe=config.timeframe, clock=clock, provider=provider)



    def handle_order_request(event: Event):
        trade_req = event.data
        symbol = trade_req.get("symbol", "EURUSD")
        direction = trade_req.get("direction")
        ask = trade_req.get("ask", 1.1555)
        bid = trade_req.get("bid", 1.1554)
        rolling_df = trade_req.get("rolling_bars_df")
        
        atr = 0.0012
        if rolling_df is not None and "feat_vol_atr" in rolling_df.columns:
            atr = float(rolling_df["feat_vol_atr"].iloc[-1])

        now_dt = datetime.now(timezone.utc)
        equity = broker.get_account_summary()["equity"]
        open_pos = order_manager.open_positions
        pending_ords = order_manager.pending_orders
        open_pos_count = len(open_pos)
        pending_orders_count = len(pending_ords)
        
        active_direction = None
        if open_pos:
            active_direction = open_pos[0].get("type") or open_pos[0].get("direction")
        elif pending_ords:
            active_direction = pending_ords[0].get("type") or pending_ords[0].get("direction")

        vol_rank = 50.0
        if rolling_df is not None and "feat_vol_atr_pct" in rolling_df.columns:
            vol_rank = float(rolling_df["feat_vol_atr_pct"].iloc[-1])

        # TEMPORARY OANDA FIFO FIX: MAX ACTIVE TRADE LOGIC = 1
        # Skip this check only if it's a valid Signal Reversal (which closes the old trade)
        is_reversal = (active_direction is not None and active_direction != direction)
        if not is_reversal and (open_pos_count + pending_orders_count >= 1):
            logger.warning("🛑 TEMPORARY BLOCK: MAX ACTIVE TRADE LOGIC = 1 not met (Trade already active/pending). Order rejected to comply with OANDA FIFO rules.")
            event_bus.publish(Event(EventType.RISK_VETOED, {"reason": "MAX_ACTIVE_TRADE_LOGIC_1", "symbol": symbol, "direction": direction}))
            return

        # Pre-Trade Risk Audit
        risk_res = risk_guardian.evaluate_entry_risk(
            symbol=symbol,
            current_equity=equity,
            open_positions_count=open_pos_count,
            pending_orders_count=pending_orders_count,
            current_time=now_dt,
            vol_rank_pct=vol_rank,
            signal_direction=direction,
            active_direction=active_direction,
            atr=atr
        )

        if not risk_res["allowed"]:
            reason = risk_res["reason"]
            logger.warning(f"🛡️ Pre-Trade Risk Guardian VETOED Order: {reason}")
            event_bus.publish(Event(EventType.RISK_VETOED, {"reason": reason, "symbol": symbol, "direction": direction}))
            return

        # Handle Signal Reversal Protocol
        if risk_res.get("action") == "SIGNAL_REVERSAL":
            logger.info(f"🔄 SIGNAL REVERSAL PROTOCOL TRIGGERED: Closing active {active_direction} position to flip into {direction}")
            # Cancel pending orders
            order_manager.pending_orders.clear()
            
            # Force close active position at current market price
            for pos in list(order_manager.open_positions):
                close_price = bid if active_direction == "BUY" else ask
                order_manager.force_close_position(pos["position_id"], exit_price=close_price, reason="SIGNAL_REVERSAL", current_time=now_dt)
                logger.info(f"📉 SIGNAL REVERSAL EXIT: Position {pos['position_id']} closed @ {close_price:.5f}")



        # Place Paper Order
        order = broker.place_order(
            symbol=symbol,
            signal_type=direction,
            signal_time=now_dt,
            ask=ask,
            bid=bid,
            atr=atr,
            risk_pct=config.risk_per_trade_pct * risk_res["risk_multiplier"]
        )
        logger.info(f"📈 ORDER CREATED: {order['order_id']} | {symbol} {direction} @ {order['limit_price']:.5f}")
        event_bus.publish(Event(EventType.ORDER_CREATED, order))


    event_bus.subscribe(EventType.ORDER_REQUEST, handle_order_request)

    streamer = RealTimeDataStreamer(symbol="EURUSD", timeframe="1h")
    streamer.initialize_stream()
    
    # Warmup
    signal_engine.warmup_model(streamer.full_df)

    eval_bar_count = 0
    last_evaluated_h1_ts = None
    print(f"[{format_ist_utc()}] 🟢 Daemon fully initialized with live OANDA stream. Entering live tick evaluation loop...\n")

    while True:
        try:
            eval_bar_count += 1
            curr_time, ask, bid, rolling_df = streamer.get_next_tick_and_bars()
            utc_ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            # Update paper broker on each tick for pending order limit fills and TP/SL hits
            closed_trades = broker.on_tick(datetime.now(timezone.utc), ask, bid)
            for t in closed_trades:
                pnl_u = float(t.get('pnl_usd', 0.0) or 0.0)
                pnl_r = float(t.get('r_multiple', 0.0) or 0.0)
                logger.info(f"📉 POSITION CLOSED: {t.get('position_id')} | PnL: ${pnl_u:+.2f} ({pnl_r:+.2f}R)")
                event_bus.publish(Event(EventType.POSITION_CLOSED, t))

            # Emit tick update to EventBus (Every Tick/Minute)
            event_bus.publish(Event(EventType.TICK_UPDATE, {
                "timestamp": utc_ts_str,
                "symbol": "EURUSD",
                "ask": ask,
                "bid": bid,
                "rolling_bars_df": rolling_df
            }))

            # H1 Candle Close Guard: Fire ML Inference ONLY on fresh H1 candle completion (XX:00:00 UTC)
            current_h1_ts = curr_time.strftime("%Y-%m-%d %H:00") if hasattr(curr_time, "strftime") else str(curr_time)[:13]
            if last_evaluated_h1_ts is None:
                # On startup mid-hour, set baseline to current H1 bar to prevent stale mid-hour orders
                last_evaluated_h1_ts = current_h1_ts
                logger.info(f"🟢 Initialized H1 Candle Guard to [{current_h1_ts} UTC]. Waiting for next top-of-the-hour candle close...")
            elif current_h1_ts > last_evaluated_h1_ts:
                last_evaluated_h1_ts = current_h1_ts
                logger.info(f"⏰ NEW H1 CANDLE COMPLETED ({current_h1_ts} UTC) — Triggering ML Feature Extraction & Signal Inference...")
                
                # Fetch fresh completed candle from OANDA to prevent feature stagnation
                streamer.sync_latest_closed_candles(count=2)
                # Re-fetch the updated rolling bars
                _, updated_ask, updated_bid, updated_rolling_df = streamer.get_next_tick_and_bars()

                event_bus.publish(Event(EventType.BAR_CLOSED, {
                    "timestamp": utc_ts_str,
                    "symbol": "EURUSD",
                    "ask": updated_ask,
                    "bid": updated_bid,
                    "rolling_bars_df": updated_rolling_df
                }))

            summary = broker.get_account_summary()
            logger.info(f"{format_ist_utc()}] 🟢 Live Tick #{eval_bar_count} | Ask: {ask:.5f} | Bid: {bid:.5f} | Equity: ${summary['equity']:,.2f} | Open Pos: {summary['open_positions_count']} | Closed: {summary['closed_trades_count']}")
            
        except Exception as e:
            logger.error(f"{format_ist_utc()}] ⚠️ Live Bar Loop Exception: {e}")
            
        # Dynamic Top-of-Minute Sleep: Align tick loop exactly to XX:XX:01 UTC
        now_dt = datetime.now(timezone.utc)
        sleep_sec = 60.0 - (now_dt.second + now_dt.microsecond / 1e6) + 0.5
        if sleep_sec <= 0 or sleep_sec > 60.0:
            sleep_sec = 60.0
        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()
