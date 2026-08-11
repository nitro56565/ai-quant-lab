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

from live_trading_engine.config import LiveTradingConfig
from live_trading_engine.events import EventBus, Event, EventType
from live_trading_engine.persistence.database import DatabaseManager
from live_trading_engine.models import SignalEngine
from live_trading_engine.decision import DecisionEngine
from live_trading_engine.risk import PreTradeRiskGuardian
from live_trading_engine.execution.order_manager import OrderManager
from live_trading_engine.broker.local_paper import LocalPaperBroker
from live_trading_engine.data import RealTimeDataStreamer
from live_trading_engine.monitoring.telegram_notifier import TelegramNotifier
from live_trading_engine.monitoring.metrics import get_metrics_exporter

from live_trading_engine.clock import RealClock
from live_trading_engine.data.oanda_provider import OANDAMarketDataProvider
from live_trading_engine.broker import ExecutionSimulator, LocalPaperBroker, OANDALiveBrokerGateway

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

    db_manager = DatabaseManager("live_trading_engine/logs/institutional_ledger.db")
    event_bus = EventBus()

    # Metrics & Telegram
    metrics = get_metrics_exporter()
    telegram = TelegramNotifier(event_bus=event_bus, db=db_manager)

    # Core Pipeline & Execution Layer
    signal_engine = SignalEngine(event_bus=event_bus, model_dir="models/production")
    decision_engine = DecisionEngine(event_bus=event_bus, db_manager=db_manager)
    risk_guardian = PreTradeRiskGuardian(config=config)
    order_manager = OrderManager(config=config, clock=clock)

    if broker_mode in ["OANDA_PRACTICE", "OANDA_LIVE", "OANDA"]:
        broker = OANDALiveBrokerGateway(config=config, order_manager=order_manager, clock=clock)
        logger.info("🟢 Registered OANDALiveBrokerGateway: Orders will be submitted directly to OANDA Practice REST API!")
    else:
        broker = ExecutionSimulator(config=config, order_manager=order_manager, clock=clock)
        logger.info("🟢 Registered ExecutionSimulator: Orders executed in high-fidelity local paper simulator.")

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

        # Pre-Trade Risk Audit
        risk_res = risk_guardian.evaluate_entry_risk(
            symbol=symbol,
            current_equity=equity,
            open_positions_count=open_pos_count,
            pending_orders_count=pending_orders_count,
            current_time=now_dt,
            vol_rank_pct=50.0,
            signal_direction=direction,
            active_direction=active_direction
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
                logger.info(f"📉 POSITION CLOSED: {t.get('position_id')} | PnL: ${t.get('pnl_usd'):+.2f} ({t.get('r_multiple'):+.2f}R)")
                event_bus.publish(Event(EventType.POSITION_CLOSED, t))

            # Emit tick update to EventBus (Every Tick/Minute)
            event_bus.publish(Event(EventType.TICK_UPDATE, {
                "timestamp": utc_ts_str,
                "symbol": "EURUSD",
                "ask": ask,
                "bid": bid,
                "rolling_bars_df": rolling_df
            }))

            # H1 Candle Close Guard: Fire ML Inference ONCE per H1 candle completion
            current_h1_ts = curr_time.strftime("%Y-%m-%d %H:00") if hasattr(curr_time, "strftime") else str(curr_time)[:13]
            if last_evaluated_h1_ts is None or current_h1_ts > last_evaluated_h1_ts:
                last_evaluated_h1_ts = current_h1_ts
                logger.info(f"⏰ NEW H1 CANDLE COMPLETED ({current_h1_ts} UTC) — Triggering ML Feature Extraction & Signal Inference...")
                
                event_bus.publish(Event(EventType.BAR_CLOSED, {
                    "timestamp": utc_ts_str,
                    "symbol": "EURUSD",
                    "ask": ask,
                    "bid": bid,
                    "rolling_bars_df": rolling_df
                }))

            summary = broker.get_account_summary()
            logger.info(f"{format_ist_utc()}] 🟢 Live Tick #{eval_bar_count} | Ask: {ask:.5f} | Bid: {bid:.5f} | Equity: ${summary['equity']:,.2f} | Open Pos: {summary['open_positions_count']} | Closed: {summary['closed_trades_count']}")
            
        except Exception as e:
            logger.error(f"{format_ist_utc()}] ⚠️ Live Bar Loop Exception: {e}")
            
        time.sleep(60.0)


if __name__ == "__main__":
    main()
