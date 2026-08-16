"""
OANDA v20 Live / Practice Broker Execution Gateway — AI Quant Lab v5.0.
Implements BaseExecutionGateway and BaseBrokerAdapter to submit actual Limit Orders,
Stop Losses, and Take Profits directly to OANDA Practice / Live Broker Accounts via v20 REST API.
Orders placed via this gateway appear live inside the OANDA Web Trading Console & Mobile App.
"""

import os
import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from live_execution_engine.config import LiveTradingConfig
from live_execution_engine.order_manager import OrderManager
from live_execution_engine.broker.base_gateway import BaseExecutionGateway
from live_execution_engine.clock import BaseClock, RealClock
from live_execution_engine.broker.broker_authoritative_sync import BrokerAuthoritativeReconciler

logger = logging.getLogger(__name__)

class OANDALiveBrokerGateway(BaseExecutionGateway):
    """
    OANDA v20 REST API Live/Practice Broker Gateway.
    Submits real limit retrace orders, stop losses, and take profits directly to OANDA servers.
    Enforces 100% Broker-Authoritative Sync rules.
    """
    def __init__(self, config: LiveTradingConfig, order_manager: OrderManager, clock: Optional[BaseClock] = None):
        self.config = config
        self.order_manager = order_manager
        self.clock = clock or RealClock()

        self.api_key = os.getenv("OANDA_API_KEY")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.environment = os.getenv("OANDA_ENV", "practice").lower()
        self.base_domain = "api-fxpractice.oanda.com" if self.environment == "practice" else "api-fxtrade.oanda.com"
        self.reconciler = BrokerAuthoritativeReconciler(order_manager=self.order_manager, config=self.config)

        if not (self.api_key and self.account_id):
            logger.warning("⚠️ OANDALiveBrokerGateway missing OANDA_API_KEY or OANDA_ACCOUNT_ID credentials!")

    def place_order(self, symbol: str, signal_type: str, signal_time: datetime,
                    ask: float, bid: float, atr: float, risk_pct: float) -> dict:
        """
        Creates local order spec in OrderManager AND submits limit order payload to OANDA REST API.
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
        
        max_lots_leverage = (base_capital * self.config.max_leverage) / 100000.0
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
                "timeInForce": "GFD", # Good for Day (auto-expires end of day or 3h)
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
                oanda_tx_id = res_data.get("orderCreateTransaction", {}).get("id")
                logger.info(f"🌐 [OANDA API CONFIRMED] Limit Order Submitted to OANDA Practice Account! OANDA Transaction ID: {oanda_tx_id} | {symbol} {signal_type} @ {price_str}")
                local_order["oanda_transaction_id"] = oanda_tx_id
        except Exception as e:
            logger.error(f"❌ Failed to submit order to OANDA REST API: {e}")

        return local_order

    def on_tick(self, current_time: datetime, ask: float, bid: float) -> list:
        """
        Evaluates local order state and reconciles fills with OANDA broker state.
        Enforces 100% Broker-Authoritative Sync rules.
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

        # Execute 10-point Authoritative Reconciliation
        reconciled = self.reconciler.reconcile_state(
            local_pending=self.order_manager.pending_orders,
            local_positions=self.order_manager.open_positions,
            broker_orders=broker_orders,
            broker_trades=broker_trades,
            broker_mode=bool(self.api_key and self.account_id)
        )

        self.order_manager.pending_orders = reconciled["reconciled_pending"]
        self.order_manager.open_positions = reconciled["reconciled_positions"]
        self.order_manager.save_state()

        return self.order_manager.open_positions

    def get_account_summary(self) -> dict:
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
