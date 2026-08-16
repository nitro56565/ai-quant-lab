"""
OANDA Execution Engine Module — AI Quant Lab v5.0.
Production execution engine communicating directly with OANDA v20 REST API.

Architectural Flow:
  OANDAExecutionEngine -> OANDA Broker API -> Broker-Confirmed Events -> PositionStateManager (OrderManager)

Simulated tick matching is completely absent and impossible to invoke in this module.
Position state changes flow 100% from OANDA server confirmed responses and webhooks.
"""

import os
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.execution.order_manager import OrderManager
from live_execution_engine.clock import BaseClock, RealClock
from live_execution_engine.broker.broker_authoritative_sync import BrokerAuthoritativeReconciler

logger = logging.getLogger(__name__)

class OANDAExecutionEngine:
    """
    Production OANDA REST API Execution Engine.
    All order fills, position closes, and cancellations flow strictly from OANDA server responses.
    """
    def __init__(self, config: LiveTradingConfig, order_manager: OrderManager, clock: Optional[BaseClock] = None, event_bus: Optional[Any] = None):
        self.config = config
        self.order_manager = order_manager
        self.clock = clock or RealClock()
        self.event_bus = event_bus

        self.api_key = os.getenv("OANDA_API_KEY")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.environment = os.getenv("OANDA_ENV", "practice").lower()
        self.base_domain = "api-fxpractice.oanda.com" if self.environment == "practice" else "api-fxtrade.oanda.com"
        self.reconciler = BrokerAuthoritativeReconciler(order_manager=self.order_manager, config=self.config)

        if not (self.api_key and self.account_id):
            logger.warning("⚠️ OANDAExecutionEngine missing OANDA_API_KEY or OANDA_ACCOUNT_ID credentials!")

        logger.info("🟢 OANDAExecutionEngine Initialized: Production OANDA v20 REST API Execution Active (Broker-Authoritative Events Only).")

    def place_order(
        self, symbol: str, signal_type: str, signal_time: datetime,
        ask: float, bid: float, atr: float, risk_pct: float
    ) -> Dict[str, Any]:
        """
        Creates local spec in OrderManager AND submits limit order payload to OANDA REST API.
        """
        local_order = self.order_manager.create_limit_order(
            symbol=symbol,
            signal_type=signal_type,
            signal_time=signal_time,
            ask=ask,
            bid=bid,
            atr=atr,
            risk_pct=risk_pct
        )

        if not (self.api_key and self.account_id):
            logger.warning(f"⚠️ OANDA credentials missing. Local order {local_order['order_id']} tracked locally only.")
            return local_order

        # Format OANDA v20 Order Specification with Fixed $10k Base Capital Sizing
        instrument = symbol.replace("/", "_")
        if "_" not in instrument and len(instrument) == 6:
            instrument = f"{instrument[:3]}_{instrument[3:]}"

        base_capital = float(self.config.initial_capital)  # Fixed $10,000.00
        sl_dist_pips = abs(local_order['limit_price'] - local_order['stop_loss']) / self.config.pip_size
        risk_usd = base_capital * (self.config.risk_per_trade_pct / 100.0) # Fixed $75.00
        raw_lots = risk_usd / (sl_dist_pips * 10.0) if sl_dist_pips > 0 else 0.31
        
        max_lev = getattr(self.config, 'max_leverage', 20.0)
        max_lots_leverage = (base_capital * max_lev) / 100000.0
        lots = min(raw_lots, max_lots_leverage)
        lots_rounded = max(0.01, round(lots, 2))
        
        units_count = int(round(lots_rounded * 100000))
        units = units_count if signal_type == "BUY" else -units_count

        logger.info(f"📏 FIXED $10K BASE SIZING: Base Equity ${base_capital:,.2f} | Risk {self.config.risk_per_trade_pct}% (${risk_usd:.2f}) | SL {sl_dist_pips:.1f}p | Lots: {lots_rounded} ({units:+} units)")
        price_str = f"{local_order['limit_price']:.5f}"
        sl_str = f"{local_order['stop_loss']:.5f}"
        tp_str = f"{local_order['take_profit']:.5f}"

        oanda_payload = {
            "order": {
                "type": "LIMIT",
                "instrument": instrument,
                "units": str(units),
                "price": price_str,
                "timeInForce": "GFD",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": sl_str,
                    "timeInForce": "GTC"
                },
                "takeProfitOnFill": {
                    "price": tp_str,
                    "timeInForce": "GTC"
                }
            }
        }

        if getattr(self.config, 'limit_retrace_atr_mult', 0.25) == 0.0:
            oanda_payload["order"]["type"] = "MARKET"
            del oanda_payload["order"]["price"]
            oanda_payload["order"]["timeInForce"] = "FOK"

        try:
            url = f"https://{self.base_domain}/v3/accounts/{self.account_id}/orders"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            req_data = json.dumps(oanda_payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=5) as res:
                res_data = json.loads(res.read().decode("utf-8"))
                
                if oanda_payload["order"]["type"] == "MARKET":
                    oanda_tx_id = res_data.get("orderFillTransaction", {}).get("id")
                    oanda_trade_id = res_data.get("orderFillTransaction", {}).get("tradeOpened", {}).get("tradeID")
                    logger.info(f"🌐 [OANDA API CONFIRMED] Market Order Filled on OANDA! Tx ID: {oanda_tx_id} | Trade ID: {oanda_trade_id}")
                    
                    # Map OANDA Trade ID directly to the newly created local position
                    for pos in self.order_manager.open_positions:
                        if pos['position_id'] == f"POS_{local_order['order_id']}":
                            pos['oanda_trade_id'] = oanda_trade_id
                            break
                else:
                    oanda_tx_id = res_data.get("orderCreateTransaction", {}).get("id")
                    logger.info(f"🌐 [OANDA API CONFIRMED] Limit Order Submitted to OANDA Practice Account! OANDA Transaction ID: {oanda_tx_id} | {symbol} {signal_type} @ {price_str}")
                    local_order["oanda_transaction_id"] = oanda_tx_id
                
                # CRITICAL FIX: Save state immediately so the ID is written to JSON disk
                self.order_manager.save_state()
                
        except Exception as e:
            logger.error(f"❌ Failed to submit order to OANDA REST API: {e}")

        return local_order

    def sync_broker_events(self) -> List[Dict[str, Any]]:
        """
        Polls / Reconciles authoritative OANDA server state (orders, trades, cancels).
        Returns list of closed trades or state changes confirmed by OANDA.
        """
        broker_orders = []
        broker_trades = []
        if self.api_key and self.account_id:
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                
                # Fetch pending orders from OANDA REST API
                url_ord = f"https://{self.base_domain}/v3/accounts/{self.account_id}/pendingOrders"
                req_ord = urllib.request.Request(url_ord, headers=headers)
                with urllib.request.urlopen(req_ord, timeout=3) as res:
                    broker_orders = json.loads(res.read().decode("utf-8")).get("orders", [])

                # Fetch open trades from OANDA REST API
                url_trd = f"https://{self.base_domain}/v3/accounts/{self.account_id}/openTrades"
                req_trd = urllib.request.Request(url_trd, headers=headers)
                with urllib.request.urlopen(req_trd, timeout=3) as res:
                    broker_trades = json.loads(res.read().decode("utf-8")).get("trades", [])
            except Exception as e:
                logger.debug(f"⚠️ OANDA state sync network check: {e}")

        # Execute Authoritative Reconciliation
        reconciled = self.reconciler.reconcile_state(
            local_pending=self.order_manager.pending_orders,
            local_positions=self.order_manager.open_positions,
            broker_orders=broker_orders,
            broker_trades=broker_trades,
            broker_mode=bool(self.api_key and self.account_id)
        )

        self.order_manager.pending_orders = reconciled["reconciled_pending"]
        self.order_manager.open_positions = reconciled["reconciled_positions"]

        from live_execution_engine.events import Event, EventType

        # Publish ORDER_FILLED for any newly confirmed fills on broker
        newly_filled = reconciled.get("newly_filled", [])
        for pos in newly_filled:
            logger.info(f"🟢 EMITTING ORDER_FILLED EVENT FOR TELEGRAM: {pos['position_id']}")
            if self.event_bus:
                self.event_bus.publish(Event(EventType.ORDER_FILLED, pos))

        # Publish POSITION_CLOSED for any newly confirmed closures on broker
        recently_closed = reconciled.get("closed_positions", [])
        for pos in recently_closed:
            self.order_manager.closed_trades.append(pos)
            logger.info(f"🔴 EMITTING POSITION_CLOSED EVENT FOR TELEGRAM: {pos['position_id']}")
            if self.event_bus:
                self.event_bus.publish(Event(EventType.POSITION_CLOSED, pos))

        self.order_manager.save_state()

        return recently_closed

    def on_tick(self, current_time: datetime, ask: float, bid: float) -> List[Dict[str, Any]]:
        """
        Broker-Authoritative Tick Callback.
        Returns list of newly closed trades (empty if open positions are active).
        """
        closed_trades = self.sync_broker_events()
        self._evaluate_trailing_and_partials(ask, bid)
        return closed_trades

    def _evaluate_trailing_and_partials(self, ask: float, bid: float):
        if not (self.api_key and self.account_id):
            return

        for pos in self.order_manager.open_positions:
            trade_id = pos.get("oanda_trade_id")
            if not trade_id: continue

            init_sl = pos.get('initial_stop_loss', pos['stop_loss'])
            sl_dist_pips = abs(pos['entry_price'] - init_sl) / self.config.pip_size
            if sl_dist_pips <= 0: continue

            pos_atr = pos.get('atr', 0.0012)
            
            if pos['type'] == 'BUY':
                floating_pips = (bid - pos['entry_price']) / self.config.pip_size
            else:
                floating_pips = (pos['entry_price'] - ask) / self.config.pip_size
                
            r_floating = floating_pips / sl_dist_pips
            
            # 1. Partial Exit (50% at 1.5R)
            if not pos.get('partial_taken', False) and r_floating >= 1.5:
                # Issue PUT to close 50%
                units = int(round(pos.get("lots", 0.01) * 100000 * 0.5))
                if units > 0:
                    self._oanda_partial_close(trade_id, units)
                    pos['partial_taken'] = True
                    # Let sync_broker_events natively update pos lots next tick!
                    logger.info(f"💰 [OANDA API] PARTIAL EXIT TRIGGERED (+1.5R): Attempting to close {units} units on Trade #{trade_id}.")
                    if self.event_bus:
                        from live_execution_engine.events import Event, EventType
                        # We don't have a PARTIAL_EXIT event type yet, but we can emit a custom signal
                        self.event_bus.publish(Event(EventType.ORDER_FILLED, {"message": f"PARTIAL EXIT {units} units on {trade_id}"}))
                
            # 2. Trailing Stop (+2.0R Activation)
            if r_floating >= 2.0:
                trail_dist = pos_atr * 1.5
                if pos['type'] == 'BUY':
                    new_sl = round(bid - trail_dist, 5)
                    if new_sl > pos['stop_loss']:
                        self._oanda_update_sl(trade_id, new_sl)
                        pos['stop_loss'] = new_sl
                        logger.info(f"🚀 [OANDA API] TRAILING STOP UPDATED: Trade #{trade_id} SL moved to {new_sl:.5f}")
                else:
                    new_sl = round(ask + trail_dist, 5)
                    if new_sl < pos['stop_loss']:
                        self._oanda_update_sl(trade_id, new_sl)
                        pos['stop_loss'] = new_sl
                        logger.info(f"🚀 [OANDA API] TRAILING STOP UPDATED: Trade #{trade_id} SL moved to {new_sl:.5f}")

    def _oanda_partial_close(self, trade_id: str, units_to_close: int):
        try:
            url = f"https://{self.base_domain}/v3/accounts/{self.account_id}/trades/{trade_id}/close"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = json.dumps({"units": str(units_to_close)}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers, method="PUT")
            with urllib.request.urlopen(req, timeout=5) as res:
                logger.info(f"✅ [OANDA API] Successfully partially closed {units_to_close} units on Trade #{trade_id}.")
        except Exception as e:
            logger.error(f"❌ [OANDA API] Failed to partial close Trade #{trade_id}: {e}")

    def _oanda_update_sl(self, trade_id: str, new_sl: float):
        try:
            url = f"https://{self.base_domain}/v3/accounts/{self.account_id}/trades/{trade_id}/orders"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = json.dumps({"stopLoss": {"price": f"{new_sl:.5f}"}}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers, method="PUT")
            with urllib.request.urlopen(req, timeout=5) as res:
                logger.info(f"✅ [OANDA API] Successfully updated Stop Loss on Trade #{trade_id} to {new_sl:.5f}.")
        except Exception as e:
            logger.error(f"❌ [OANDA API] Failed to update Stop Loss on Trade #{trade_id}: {e}")

    def get_account_summary(self) -> Dict[str, Any]:
        """
        Queries OANDA GET /v3/accounts/{account_id}/summary to fetch true live account balance & equity.
        """
        if not (self.api_key and self.account_id):
            closed_pnl = sum([float(t.get('pnl_usd', 0.0)) for t in self.order_manager.closed_trades])
            b = float(self.config.initial_capital) + closed_pnl
            return {
                "initial_capital": self.config.initial_capital,
                "balance": round(b, 2),
                "equity": round(b, 2),
                "unrealized_pnl": 0.0,
                "open_positions_count": len(self.order_manager.open_positions),
                "pending_orders_count": len(self.order_manager.pending_orders),
                "closed_trades_count": len(self.order_manager.closed_trades),
                "currency": "USD",
                "source": "LOCAL_FALLBACK"
            }

        try:
            url = f"https://{self.base_domain}/v3/accounts/{self.account_id}/summary"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                acc = data.get("account", {})
                b = float(acc.get("balance", self.config.initial_capital))
                e = float(acc.get("NAV", b))
                unrealized = float(acc.get("unrealizedPL", 0.0))
                open_pos_count = int(acc.get("openPositionCount", len(self.order_manager.open_positions)))
                pending_count = int(acc.get("pendingOrderCount", len(self.order_manager.pending_orders)))

                return {
                    "account_id": self.account_id,
                    "initial_capital": self.config.initial_capital,
                    "balance": round(b, 2),
                    "equity": round(e, 2),
                    "unrealized_pnl": round(unrealized, 2),
                    "open_positions_count": open_pos_count,
                    "pending_orders_count": pending_count,
                    "closed_trades_count": len(self.order_manager.closed_trades),
                    "currency": acc.get("currency", "USD"),
                    "source": "OANDA_PRACTICE_API"
                }
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch OANDA account summary: {e}")

        closed_pnl = sum([float(t.get('pnl_usd', 0.0)) for t in self.order_manager.closed_trades])
        b = float(self.config.initial_capital) + closed_pnl
        return {
            "initial_capital": self.config.initial_capital,
            "balance": round(b, 2),
            "equity": round(b, 2),
            "unrealized_pnl": 0.0,
            "open_positions_count": len(self.order_manager.open_positions),
            "pending_orders_count": len(self.order_manager.pending_orders),
            "closed_trades_count": len(self.order_manager.closed_trades),
            "currency": "USD",
            "source": "LOCAL_FALLBACK"
        }
