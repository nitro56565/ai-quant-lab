"""
Signal Engine & Model Registry Loader Module.
Loads certified models from models/production/ and generates H1 predictions upon BAR_CLOSED events.
"""

import json
import os
import numpy as np
import pandas as pd
import logging
from research_engine.feature_matrix import FeatureMatrixBuilder
from ai_engine.ensemble import LightGBMCatBoostEnsemble
from live_trading_engine.event_bus import EventBus, Event, EventType

logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self, event_bus: EventBus, model_dir: str = "models/production"):
        self.event_bus = event_bus
        self.model_dir = model_dir
        self.feature_builder = FeatureMatrixBuilder()
        self.ensemble = LightGBMCatBoostEnsemble()
        self.metadata = self._load_model_metadata()
        self.is_trained = False

        # Load pre-trained certified model suite if available
        model_file = os.path.join(self.model_dir, "model_suite.joblib")
        if not os.path.exists(model_file):
            model_file = "models/EURUSD/2026/model_suite.joblib"
        if os.path.exists(model_file):
            import joblib
            try:
                self.ensemble = joblib.load(model_file)
                self.is_trained = True
                logger.info(f"🟢 Certified Production Model Weights Loaded from '{model_file}'")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load model weights from {model_file}: {e}")

        # Subscribe to BAR_CLOSED events on Event Bus
        self.event_bus.subscribe(EventType.BAR_CLOSED, self.on_bar_closed)


    def _load_model_metadata(self) -> dict:

        meta_file = os.path.join(self.model_dir, "metadata.json")
        if os.path.exists(meta_file):
            with open(meta_file, "r") as f:
                data = json.load(f)
            logger.info(f"🟢 Certified Production Model Loaded: {data.get('model_id')} (PSR: {data.get('benchmark_metrics', {}).get('psr')})")
            return data
        else:
            logger.warning(f"⚠️ Production metadata not found in {self.model_dir}. Falling back to default settings.")
            return {"model_id": "DEFAULT_V1", "version": "1.0.0"}

    def warmup_model(self, historical_df: pd.DataFrame):
        """
        Warms up feature matrix and model ensemble on multi-year dataset.
        """
        if self.is_trained:
            logger.info("🟢 SignalEngine already loaded certified pre-trained weights. Skipping re-training.")
            return

        if len(historical_df) < 5000:

            from data_loader import DataLoader, DataRequest
            logger.info("⚡ Loading 12-Year Cumulative Historical Dataset (2014-2026) for Master Model Training...")
            loader = DataLoader()
            req = DataRequest(symbol=self.metadata.get("symbol", "EURUSD"), timeframe="1h", start="2014-01-01", end="2026-08-06")
            historical_df = loader.load(req)


        logger.info(f"⚡ SignalEngine: Warming up production model ensemble on {len(historical_df):,} bars...")
        df_feat = self.feature_builder.build(historical_df.copy())

        close = df_feat['close'].values
        high = df_feat['high'].values
        low = df_feat['low'].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values
        df_feat['feat_vol_atr'] = atr
        df_feat['feat_vol_atr_pct'] = df_feat['feat_vol_atr'].rank(pct=True) * 100.0

        from research_engine.labeler import TripleBarrierLabeler
        tb_lab = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_bars=24)
        df_lbl = tb_lab.label(df_feat)
        df_lbl['label_dir_long'] = np.where(df_lbl['label_tb_target_long'] == 1, 1, 0)
        df_lbl['label_dir_short'] = np.where(df_lbl['label_tb_target_short'] == 1, 1, 0)

        feat_cols = [c for c in df_lbl.columns if c.startswith('feat_')]
        df_lbl[feat_cols] = df_lbl[feat_cols].bfill().ffill().fillna(0.0)
        df_clean = df_lbl.dropna(subset=['label_dir_long'])

        X_train = df_clean[feat_cols]
        targets = {
            'dir_long': df_clean['label_dir_long'],
            'dir_short': df_clean['label_dir_short'],
            'mfe_long': df_clean['label_mfe_long_pips'],
            'mfe_short': df_clean['label_mfe_short_pips'],
            'mae_long': df_clean['label_mae_long_pips'],
            'mae_short': df_clean['label_mae_short_pips']
        }
        self.ensemble.fit(X_train=X_train, targets=targets)
        self.is_trained = True

        # Save model suite joblib for deterministic replay parity
        os.makedirs(self.model_dir, exist_ok=True)
        model_file = os.path.join(self.model_dir, "model_suite.joblib")
        import joblib
        joblib.dump(self.ensemble, model_file)
        logger.info(f"✅ SignalEngine Warmup Complete. Saved model suite weights to '{model_file}'.")


    def on_bar_closed(self, event: Event):
        """
        Event Bus Callback: Triggered when an H1 candle closes. Runs model inference ONCE.
        """
        bars_df = event.data.get("rolling_bars_df")
        symbol = event.data.get("symbol")
        timestamp = event.data.get("timestamp")

        if not self.is_trained:
            self.warmup_model(bars_df)

        df_feat = self.feature_builder.build(bars_df.copy())
        close = df_feat['close'].values
        high = df_feat['high'].values
        low = df_feat['low'].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
        atr = pd.Series(np.insert(tr, 0, high[0] - low[0])).rolling(14, min_periods=1).mean().values
        df_feat['feat_vol_atr'] = atr
        df_feat['feat_vol_atr_pct'] = df_feat['feat_vol_atr'].rank(pct=True) * 100.0

        feat_cols = [c for c in df_feat.columns if c.startswith('feat_')]
        df_feat[feat_cols] = df_feat[feat_cols].bfill().ffill().fillna(0.0)
        latest_row = df_feat.iloc[[-1]][feat_cols]

        preds = self.ensemble.predict(latest_row)
        prob_long = float(preds['prob_long'][0])
        prob_short = float(preds['prob_short'][0])
        mfe_long = float(preds['mfe_50_long'][0])
        mfe_short = float(preds['mfe_50_short'][0])
        mae_long = float(preds['mae_50_long'][0])
        mae_short = float(preds['mae_50_short'][0])

        latest_atr = float(df_feat['feat_vol_atr'].iloc[-1])
        vol_rank = float(df_feat['feat_vol_atr_pct'].iloc[-1])

        cost_drag = 1.50
        net_ev_long = (prob_long * mfe_long) - ((1.0 - prob_long) * mae_long) - cost_drag
        net_ev_short = (prob_short * mfe_short) - ((1.0 - prob_short) * mae_short) - cost_drag

        pred_event_data = {
            "timestamp": timestamp,
            "symbol": symbol,
            "prob_long": prob_long,
            "prob_short": prob_short,
            "net_ev_long": net_ev_long,
            "net_ev_short": net_ev_short,
            "atr": latest_atr,
            "vol_rank_pct": vol_rank,
            "model_id": self.metadata.get("model_id"),
            "ask": event.data.get("ask"),
            "bid": event.data.get("bid")
        }

        # Publish MODEL_PREDICTION and SIGNAL_GENERATED events to Event Bus
        self.event_bus.publish(Event(EventType.MODEL_PREDICTION, pred_event_data))
        self.event_bus.publish(Event(EventType.SIGNAL_GENERATED, {
            "symbol": symbol,
            "probability_long": prob_long,
            "probability_short": prob_short,
            "ev_long_pips": net_ev_long,
            "ev_short_pips": net_ev_short,
            "ask": event.data.get("ask"),
            "bid": event.data.get("bid"),
            "timestamp": timestamp,
            "rolling_bars_df": bars_df,
            "feature_snapshot": latest_row.to_dict(orient="records")[0] if len(latest_row) > 0 else {}
        }))

