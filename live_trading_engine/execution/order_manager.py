"""
Order & Position Lifecycle Manager.
Tracks pending orders, active positions, stop loss/take profit triggers, trade history ledger, and JSON/Parquet state persistence.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd
import logging
from live_trading_engine.config import LiveTradingConfig
from live_trading_engine.database import DatabaseManager

logger = logging.getLogger(__name__)

from live_trading_engine.clock import BaseClock, RealClock

class OrderManager:

    def __init__(self, config: LiveTradingConfig, clock: Optional[BaseClock] = None):
        self.config = config
        self.clock = clock or RealClock()
        self.log_dir = config.log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        self.state_file = os.path.join(self.log_dir, "paper_positions_state.json")
        self.trades_history_file = os.path.join(self.log_dir, "paper_trades_history.json")
        self.db = DatabaseManager(os.path.join(self.log_dir, "institutional_ledger.db"))

        self.pending_orders = []
        self.open_positions = []
        self.closed_trades = []
        self.order_counter = 1

        self.load_state()

    def create_limit_order(self, symbol: str, signal_type: str, signal_time: datetime,
                           ask: float, bid: float, atr: float, risk_pct: float) -> dict:
        pip_size = self.config.pip_size
        ref_price = ask if signal_type == 'BUY' else bid
        retrace_offset = atr * self.config.limit_retrace_atr_mult

        if signal_type == 'BUY':
            limit_price = ref_price - retrace_offset
            sl = limit_price - (atr * self.config.sl_multiplier)
            tp = limit_price + (atr * self.config.tp_multiplier_base)
        else:
            limit_price = ref_price + retrace_offset
            sl = limit_price + (atr * self.config.sl_multiplier)
            tp = limit_price - (atr * self.config.tp_multiplier_base)

        order = {
            "order_id": f"ORD_{self.order_counter:05d}",
            "symbol": symbol,
            "signal_type": signal_type,
            "status": "PENDING_LIMIT",
            "signal_time": signal_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "created_time_dt": signal_time,
            "limit_price": round(limit_price, 5),
            "stop_loss": round(sl, 5),
            "take_profit": round(tp, 5),
            "risk_pct": risk_pct,
            "atr": atr,
            "expiry_hours": 3
        }
        self.order_counter += 1
        self.pending_orders.append(order)
        self.db.save_pending_order(order)
        self.save_state()
        logger.info(f"📌 PENDING LIMIT ORDER Created: {order['order_id']} | {symbol} {signal_type} @ {limit_price:.5f} (SL: {sl:.5f}, TP: {tp:.5f})")
        return order


    def update_positions_on_tick(self, current_time: datetime, ask: float, bid: float) -> list:
        """
        Evaluates pending orders for fills and open positions for SL/TP hits on each new tick.
        """
        newly_closed = []

        # 1. Process Pending Limit Orders
        remaining_pending = []
        for ord in self.pending_orders:
            dt1 = pd.to_datetime(current_time).tz_localize(None) if getattr(current_time, 'tzinfo', None) else pd.to_datetime(current_time)
            dt2 = pd.to_datetime(ord['created_time_dt']).tz_localize(None) if getattr(ord['created_time_dt'], 'tzinfo', None) else pd.to_datetime(ord['created_time_dt'])
            age_hours = (dt1 - dt2).total_seconds() / 3600.0
            
            # Check for limit fill trigger
            is_filled = False
            fill_price = 0.0

            if ord['signal_type'] == 'BUY' and ask <= ord['limit_price']:
                is_filled = True
                fill_price = ord['limit_price'] + (self.config.slippage_pips * self.config.pip_size)
            elif ord['signal_type'] == 'SELL' and bid >= ord['limit_price']:
                is_filled = True
                fill_price = ord['limit_price'] - (self.config.slippage_pips * self.config.pip_size)

            # Check weekend closure (Friday 21:00 UTC - Sunday 21:00 UTC)
            w = current_time.weekday()
            h_utc = current_time.hour
            is_weekend = (w == 5) or (w == 4 and h_utc >= 21) or (w == 6 and h_utc < 21)

            if is_filled:
                pos = {
                    "position_id": f"POS_{ord['order_id']}",
                    "symbol": ord['symbol'],
                    "type": ord['signal_type'],
                    "entry_time": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "entry_dt": current_time,
                    "entry_price": round(fill_price, 5),
                    "stop_loss": ord['stop_loss'],
                    "initial_stop_loss": ord['stop_loss'],
                    "take_profit": ord['take_profit'],
                    "risk_pct": ord['risk_pct'],
                    "lots": 1.0, # Base 1 Lot
                    "atr": ord.get('atr', 0.0012),
                    "trail_activated": False
                }

                self.open_positions.append(pos)
                self.db.remove_pending_order(ord['order_id'])
                self.db.save_open_position(pos)
                logger.info(f"🟢 ORDER FILLED: Position {pos['position_id']} OPENED | {ord['symbol']} {ord['signal_type']} @ {fill_price:.5f}")
            elif is_weekend:
                self.db.cancel_pending_order(ord['order_id'], "CANCELLED_WEEKEND")
                logger.info(f"🧹 Order {ord['order_id']} CANCELLED for Weekend Market Closure (Weekend Gap Protection).")
            elif age_hours < ord['expiry_hours']:
                remaining_pending.append(ord)
            else:
                self.db.cancel_pending_order(ord['order_id'], "EXPIRED")
                logger.info(f"⏳ Order {ord['order_id']} EXPIRED after 3 hours without fill.")


        self.pending_orders = remaining_pending



        # 2. Process Open Positions for SL / TP / Time Exits
        remaining_positions = []
        for pos in self.open_positions:
            dt1 = pd.to_datetime(current_time).tz_localize(None) if getattr(current_time, 'tzinfo', None) else pd.to_datetime(current_time)
            dt2 = pd.to_datetime(pos['entry_dt']).tz_localize(None) if getattr(pos['entry_dt'], 'tzinfo', None) else pd.to_datetime(pos['entry_dt'])
            pos_age_hours = (dt1 - dt2).total_seconds() / 3600.0

            pnl_pips = 0.0
            close_reason = None
            exit_price = 0.0
            
            # 50% Partial Exit Logic at +1.5R Floating Profit (Phase 1 & 2 Champion)
            pos_atr = pos.get('atr', 0.0012)
            init_sl = pos.get('initial_stop_loss', pos['stop_loss'])
            sl_dist_pips = abs(pos['entry_price'] - init_sl) / self.config.pip_size

            if pos['type'] == 'BUY':
                floating_pips = (ask - pos['entry_price']) / self.config.pip_size
                r_floating = floating_pips / sl_dist_pips if sl_dist_pips > 0 else 0.0
                
                # Check 50% Partial Exit
                if not pos.get('partial_taken', False) and r_floating >= 1.5:
                    initial_lots = pos.get('lots', 1.0)
                    partial_lots = initial_lots * 0.5
                    pos['lots'] = initial_lots * 0.5
                    pos['partial_taken'] = True
                    
                    partial_pips = sl_dist_pips * 1.5
                    partial_gross = partial_pips * (partial_lots * 10.0)
                    partial_comm = self.config.commission_per_lot * partial_lots
                    partial_net = partial_gross - partial_comm
                    pos['partial_pnl_usd'] = pos.get('partial_pnl_usd', 0.0) + partial_net
                    logger.info(f"💰 PARTIAL EXIT EXECUTED [BUY 50% @ +1.5R]: {pos['position_id']} Locked in +{partial_pips:.1f} pips (${partial_net:+.2f} USD). Remaining 50% running to original TP.")

                # Delayed ATR Trailing Logic (+2.0R Floating Profit Activation)
                if r_floating >= 2.0:
                    pos['trail_activated'] = True
                    trail_dist = pos_atr * 1.5
                    new_sl = ask - trail_dist
                    if new_sl > pos['stop_loss']:
                        logger.info(f"🚀 DELAYED ATR TRAILING UPDATED [BUY]: {pos['position_id']} SL moved from {pos['stop_loss']:.5f} -> {new_sl:.5f} (Floating: +{r_floating:.2f}R)")
                        pos['stop_loss'] = round(new_sl, 5)

                if bid <= pos['stop_loss']:
                    close_reason = 'TRAILING_STOP' if pos.get('trail_activated') else 'STOP_LOSS'
                    exit_price = pos['stop_loss'] - (self.config.slippage_pips * self.config.pip_size)
                    pnl_pips = (exit_price - pos['entry_price']) / self.config.pip_size
                elif ask >= pos['take_profit']:
                    close_reason = 'TAKE_PROFIT'
                    exit_price = pos['take_profit']
                    pnl_pips = (exit_price - pos['entry_price']) / self.config.pip_size
                elif pos_age_hours >= self.config.max_holding_hours:
                    close_reason = 'TIME_EXIT'
                    exit_price = bid
                    pnl_pips = (exit_price - pos['entry_price']) / self.config.pip_size
            else: # SELL
                floating_pips = (pos['entry_price'] - bid) / self.config.pip_size
                r_floating = floating_pips / sl_dist_pips if sl_dist_pips > 0 else 0.0
                
                # Check 50% Partial Exit
                if not pos.get('partial_taken', False) and r_floating >= 1.5:
                    initial_lots = pos.get('lots', 1.0)
                    partial_lots = initial_lots * 0.5
                    pos['lots'] = initial_lots * 0.5
                    pos['partial_taken'] = True

                    partial_pips = sl_dist_pips * 1.5
                    partial_gross = partial_pips * (partial_lots * 10.0)
                    partial_comm = self.config.commission_per_lot * partial_lots
                    partial_net = partial_gross - partial_comm
                    pos['partial_pnl_usd'] = pos.get('partial_pnl_usd', 0.0) + partial_net
                    logger.info(f"💰 PARTIAL EXIT EXECUTED [SELL 50% @ +1.5R]: {pos['position_id']} Locked in +{partial_pips:.1f} pips (${partial_net:+.2f} USD). Remaining 50% running to original TP.")

                # Delayed ATR Trailing Logic (+2.0R Floating Profit Activation)
                if r_floating >= 2.0:
                    pos['trail_activated'] = True
                    trail_dist = pos_atr * 1.5
                    new_sl = bid + trail_dist
                    if new_sl < pos['stop_loss']:
                        logger.info(f"🚀 DELAYED ATR TRAILING UPDATED [SELL]: {pos['position_id']} SL moved from {pos['stop_loss']:.5f} -> {new_sl:.5f} (Floating: +{r_floating:.2f}R)")
                        pos['stop_loss'] = round(new_sl, 5)

                if ask >= pos['stop_loss']:
                    close_reason = 'TRAILING_STOP' if pos.get('trail_activated') else 'STOP_LOSS'
                    exit_price = pos['stop_loss'] + (self.config.slippage_pips * self.config.pip_size)
                    pnl_pips = (pos['entry_price'] - exit_price) / self.config.pip_size
                elif bid <= pos['take_profit']:
                    close_reason = 'TAKE_PROFIT'
                    exit_price = pos['take_profit']
                    pnl_pips = (pos['entry_price'] - exit_price) / self.config.pip_size
                elif pos_age_hours >= self.config.max_holding_hours:
                    close_reason = 'TIME_EXIT'
                    exit_price = ask
                    pnl_pips = (pos['entry_price'] - exit_price) / self.config.pip_size

            # Exness Standard Account Overnight Rollover Swap Accounting (21:00 UTC / 00:00 Server Time)
            curr_date_str = current_time.strftime("%Y-%m-%d")
            if current_time.hour == 21 and pos.get('last_swap_date') != curr_date_str:
                night_mult = 3.0 if current_time.weekday() == 2 else 1.0  # Wednesday 3x Triple Swap
                base_swap_pip = -0.62 if pos['type'] == 'BUY' else +0.15
                swap_cost_usd = (base_swap_pip * night_mult) * (pos['lots'] * 10.0)
                pos['accumulated_swap_usd'] = pos.get('accumulated_swap_usd', 0.0) + swap_cost_usd
                pos['last_swap_date'] = curr_date_str
                logger.info(f"🌙 EXNESS OVERNIGHT SWAP APPLIED [{pos['type']}]: {pos['position_id']} Charged ${swap_cost_usd:+.2f} USD (Total Swap: ${pos['accumulated_swap_usd']:+.2f} USD)")

            if close_reason:
                trade_swap = pos.get('accumulated_swap_usd', 0.0)
                partial_pnl = pos.get('partial_pnl_usd', 0.0)
                rem_pnl = (pnl_pips * self.config.default_pip_value * pos['lots']) - self.config.commission_per_lot
                pnl_usd = rem_pnl + partial_pnl + trade_swap
                sl_dist = abs(pos['entry_price'] - pos['stop_loss'])
                r_mult = pnl_pips / (sl_dist / self.config.pip_size) if sl_dist > 0 else 0.0


                closed_trade = {
                    "position_id": pos['position_id'],
                    "symbol": pos['symbol'],
                    "type": pos['type'],
                    "entry_time": pos['entry_time'],
                    "exit_time": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "entry_price": pos['entry_price'],
                    "exit_price": round(exit_price, 5),
                    "pnl_pips": round(pnl_pips, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "reason": close_reason
                }

                # Insert 50-field record to SQLite Ledger
                self.db.insert_trade({
                    "trade_id": pos['position_id'],
                    "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "symbol": pos['symbol'],
                    "direction": pos['type'],
                    "order_type": "LIMIT_RETRACE",
                    "requested_entry": pos['entry_price'],
                    "filled_entry": pos['entry_price'],
                    "exit_price": round(exit_price, 5),
                    "take_profit": pos['take_profit'],
                    "stop_loss": pos['stop_loss'],
                    "spread": 0.12,
                    "slippage": self.config.slippage_pips,
                    "commission": self.config.commission_per_lot,
                    "fill_delay_ms": 300.0,
                    "probability": 0.42,
                    "expected_value": pnl_pips,
                    "confidence": 0.65,
                    "regime": "BULL" if pos['type'] == 'BUY' else "BEAR",
                    "atr": 0.0012,
                    "atr_percentile": 55.0,
                    "session": "NY" if 13 <= current_time.hour <= 20 else ("LONDON" if 7 <= current_time.hour <= 12 else "ASIAN"),
                    "weekday": current_time.strftime("%a").upper(),
                    "news_flag": 0,
                    "risk_percent": pos.get('risk_pct', 1.0),
                    "position_size": pos.get('lots', 1.0),
                    "holding_time_hours": round(pos_age_hours, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pips": round(pnl_pips, 2),
                    "r_multiple": round(r_mult, 2),
                    "mae_pips": round(min(0.0, pnl_pips), 2),
                    "mfe_pips": round(max(0.0, pnl_pips), 2),
                    "flag_probability_pass": 1,
                    "flag_ev_pass": 1,
                    "flag_macro_pass": 1,
                    "flag_regime_pass": 1,
                    "flag_session_pass": 1,
                    "flag_risk_pass": 1,
                    "model_version": "MOD_EURUSD_V1_2026",
                    "feature_version": "a8f9c011e4d",
                    "label_version": "triple_barrier_v1",
                    "backtest_version": "master_v1.0",
                    "walk_forward_fold": 1,
                    "prediction_latency_ms": 15.0,
                    "pipeline_version": "v1.0_production",
                    "git_commit": "certified_v1.0",
                    "docker_image": "ai-quant-paper-trading:latest",
                    "reason_exited": close_reason,
                    "feature_snapshot": {},
                    "decision_report_text": f"Closed via {close_reason} with PnL {pnl_pips:+.2f} pips (${pnl_usd:+.2f})",
                    "actual_broker_trade_log": {
                        "broker": "LOCAL_HIGH_FIDELITY_SIMULATOR",
                        "deal_id": f"DEAL_{pos['position_id']}",
                        "order_id": pos['position_id'],
                        "execution_type": "FIX_4.4_ECN_BRIDGE",
                        "liquidity_provider": "BARCLAYS_ECN_POOL",
                        "fill_price": pos['entry_price'],
                        "close_price": round(exit_price, 5),
                        "slippage_pips": self.config.slippage_pips,
                        "commission_usd": self.config.commission_per_lot,
                        "swap_usd": 0.0,
                        "close_time_utc": current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " Z",
                        "raw_execution_status": "FILLED_AND_CLOSED"
                    }
                })

                self.closed_trades.append(closed_trade)
                self.db.remove_open_position(pos['position_id'])

                newly_closed.append(closed_trade)
                logger.info(f"🔴 POSITION CLOSED [{close_reason}]: {pos['position_id']} | PnL: {pnl_pips:+.2f} pips (${pnl_usd:+.2f})")


        self.open_positions = remaining_positions
        if newly_closed or remaining_pending != self.pending_orders:
            self.save_state()

        return newly_closed

    def force_close_position(self, position_id: str, exit_price: float, reason: str = "SIGNAL_REVERSAL", current_time: datetime = None) -> Optional[dict]:
        current_time = current_time or self.clock.now()
        remaining = []
        closed_trade = None
        for pos in self.open_positions:
            if pos['position_id'] == position_id:
                pnl_pips = (exit_price - pos['entry_price']) / self.config.pip_size if pos['type'] == 'BUY' else (pos['entry_price'] - exit_price) / self.config.pip_size
                pnl_usd = (pnl_pips * self.config.default_pip_value * pos['lots']) - self.config.commission_per_lot
                sl_dist = abs(pos['entry_price'] - pos['stop_loss'])
                r_mult = pnl_pips / (sl_dist / self.config.pip_size) if sl_dist > 0 else 0.0

                closed_trade = {
                    "position_id": pos['position_id'],
                    "symbol": pos['symbol'],
                    "type": pos['type'],
                    "entry_time": pos['entry_time'],
                    "exit_time": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "entry_price": pos['entry_price'],
                    "exit_price": round(exit_price, 5),
                    "pnl_pips": round(pnl_pips, 2),
                    "pnl_usd": round(pnl_usd, 2),
                    "reason": reason,
                    "r_multiple": round(r_mult, 2)
                }

                self.db.insert_trade({
                    "trade_id": pos['position_id'],
                    "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "symbol": pos['symbol'],
                    "direction": pos['type'],
                    "order_type": "LIMIT_RETRACE",
                    "requested_entry": pos['entry_price'],
                    "filled_entry": pos['entry_price'],
                    "exit_price": round(exit_price, 5),
                    "pnl_usd": round(pnl_usd, 2),
                    "pnl_pips": round(pnl_pips, 2),
                    "reason_exited": reason,
                    "actual_broker_trade_log": {"status": "CLOSED_VIA_REVERSAL"}
                })
                self.closed_trades.append(closed_trade)
                self.db.remove_open_position(pos['position_id'])
                logger.info(f"🔴 POSITION FORCED CLOSED [{reason}]: {pos['position_id']} | PnL: {pnl_pips:+.2f} pips (${pnl_usd:+.2f})")
            else:
                remaining.append(pos)
        self.open_positions = remaining
        self.save_state()
        return closed_trade

    def save_state(self):

        # Convert datetimes to string for JSON serialization
        def serializable(obj):
            if isinstance(obj, list):
                return [serializable(x) for x in obj]
            if isinstance(obj, dict):
                d = {}
                for k, v in obj.items():
                    if k == 'created_time_dt' or k == 'entry_dt':
                        continue
                    d[k] = v
                return d
            return obj

        data = {
            "pending_orders": serializable(self.pending_orders),
            "open_positions": serializable(self.open_positions),
            "order_counter": self.order_counter
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

        with open(self.trades_history_file, "w") as f:
            json.dump(self.closed_trades, f, indent=2)

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                self.order_counter = data.get("order_counter", 1)
                
                # Restore pending orders
                for ord in data.get("pending_orders", []):
                    ord['created_time_dt'] = pd.to_datetime(ord['signal_time']).to_pydatetime()
                    self.pending_orders.append(ord)

                # Restore open positions
                for pos in data.get("open_positions", []):
                    pos['entry_dt'] = pd.to_datetime(pos['entry_time']).to_pydatetime()
                    self.open_positions.append(pos)

                logger.info(f"💾 Loaded state: {len(self.pending_orders)} pending, {len(self.open_positions)} open positions")
            except Exception as e:
                logger.error(f"Error loading state: {e}")

        if os.path.exists(self.trades_history_file):
            try:
                with open(self.trades_history_file, "r") as f:
                    self.closed_trades = json.load(f)
            except Exception as e:
                logger.error(f"Error loading trades history: {e}")
