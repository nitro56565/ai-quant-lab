"""
Signal Engine & Model Registry Loader Module.
Loads certified models from models/production_deployment/ and generates H1 predictions upon BAR_CLOSED events.
"""

import json
import os
import numpy as np
import pandas as pd
import logging
from research_and_training_engine.feature_matrix import FeatureMatrixBuilder
from core_machine_learning.ensemble import LightGBMCatBoostEnsemble, RegimeFusedEnsemble
from live_execution_engine.event_bus import EventBus, Event, EventType


logger = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self, event_bus: EventBus, model_dir: str = "trained_model_artifacts/production_deployment"):
        self.event_bus = event_bus
        self.model_dir = model_dir
        self.feature_builder = FeatureMatrixBuilder()
        self.ensemble = LightGBMCatBoostEnsemble()
        self.metadata = self._load_model_metadata()
        self.is_trained = False

        # Load pre-trained certified model suite if available
        model_file = os.path.join(self.model_dir, "model_suite.joblib")
        if not os.path.exists(model_file):
            model_file = "trained_model_artifacts/EURUSD/2026/model_suite.joblib"
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

            from historical_data_ingestion import DataLoader, DataRequest
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

        from research_and_training_engine.labeler import TripleBarrierLabeler
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

        if bars_df is None or len(bars_df) == 0:
            logger.warning("⚠️ BAR_CLOSED event received empty bars_df. Skipping feature extraction.")
            return

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
        latest_atr = float(df_feat['feat_vol_atr'].iloc[-1])
        vol_rank = float(df_feat['feat_vol_atr_pct'].iloc[-1])
        atr_pips = latest_atr / 0.0001
        mfe_long, mfe_short = 1.8 * atr_pips, 1.8 * atr_pips
        mae_long, mae_short = 1.0 * atr_pips, 1.0 * atr_pips

        if isinstance(self.ensemble, dict) and self.ensemble.get("architecture") == "FourStateRegimeEnsemble_v3":
            hmm_det = self.ensemble["hmm_detector"]
            hmm_state = int(hmm_det.predict(df_feat.iloc[[-1]])[0])
            vol_pct = float(df_feat['feat_vol_atr_pct'].iloc[-1])
            v_st = 1 if vol_pct >= 50.0 else 0
            regime_state = (hmm_state * 2) + v_st

            m_l_dict = self.ensemble["models_long"].get(regime_state)
            m_s_dict = self.ensemble["models_short"].get(regime_state)

            if m_l_dict and m_s_dict:
                feat_vals = latest_row[self.ensemble["feat_cols"]].values
                pl_cat = float(m_l_dict['cat'].predict_proba(feat_vals)[:, 1][0])
                pl_lgb = float(m_l_dict['lgb'].predict_proba(feat_vals)[:, 1][0])
                pl_xgb = float(m_l_dict['xgb'].predict_proba(feat_vals)[:, 1][0])
                prob_long = (pl_cat * 0.50) + (pl_lgb * 0.25) + (pl_xgb * 0.25)

                ps_cat = float(m_s_dict['cat'].predict_proba(feat_vals)[:, 1][0])
                ps_lgb = float(m_s_dict['lgb'].predict_proba(feat_vals)[:, 1][0])
                ps_xgb = float(m_s_dict['xgb'].predict_proba(feat_vals)[:, 1][0])
                prob_short = (ps_cat * 0.50) + (ps_lgb * 0.25) + (ps_xgb * 0.25)
                raw_prob_long = prob_long
                raw_prob_short = prob_short

            # Removed hardcoded overrides that zero out probabilities to preserve telemetry
            req_p = 0.42 if hmm_state == 1 else 0.38
            
            regime_label = "Range Market" if hmm_state == 1 else "Trend Market"
            logger.info(f"📊 H1 CANDLE ML EVALUATION | Market Regime = {regime_label} | Volatility = {vol_pct:.1f}% | Buy Prob = {raw_prob_long*100:.1f}%, Sell Prob = {raw_prob_short*100:.1f}% | Minimum Required = {req_p*100:.1f}%")

            regime_9 = regime_state
        elif isinstance(self.ensemble, dict) and self.ensemble.get("architecture") == "NineStateRegimeEnsemble":
            hmm_det = self.ensemble["hmm_detector"]
            hmm_state = int(hmm_det.predict(df_feat.iloc[[-1]])[0])
            vol_pct = float(df_feat['feat_vol_atr_pct'].iloc[-1])
            v_st = 0
            if vol_pct >= self.ensemble.get("vol_low_thresh", 33.33):
                v_st = 1
            if vol_pct >= self.ensemble.get("vol_high_thresh", 66.67):
                v_st = 2
            regime_9 = (hmm_state * 3) + v_st

            m_l = self.ensemble["models_long"].get(regime_9)
            m_s = self.ensemble["models_short"].get(regime_9)

            if m_l and m_s:
                prob_long = float(m_l.predict_proba(latest_row.values)[:, 1][0])
                prob_short = float(m_s.predict_proba(latest_row.values)[:, 1][0])
            else:
                prob_long, prob_short = 0.30, 0.30
        else:
            preds = self.ensemble.predict(latest_row)
            prob_long = float(preds['prob_long'][0])
            prob_short = float(preds['prob_short'][0])
            regime_9 = 4

        cost_drag = 0.30  # 0.30 pips total friction
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
            "regime_state_9": regime_9,
            "model_id": self.metadata.get("model_id"),
            "ask": event.data.get("ask"),
            "bid": event.data.get("bid")
        }


        # Publish MODEL_PREDICTION and SIGNAL_GENERATED events to Event Bus
        self.event_bus.publish(Event(EventType.MODEL_PREDICTION, pred_event_data))
        # Default to blended prob if individual models are not present
        p_l_lgb = locals().get('pl_lgb', prob_long)
        p_l_cat = locals().get('pl_cat', prob_long)
        p_l_xgb = locals().get('pl_xgb', prob_long)
        p_s_lgb = locals().get('ps_lgb', prob_short)
        p_s_cat = locals().get('ps_cat', prob_short)
        p_s_xgb = locals().get('ps_xgb', prob_short)

        self.event_bus.publish(Event(EventType.SIGNAL_GENERATED, {
            "symbol": symbol,
            "probability_long": prob_long,
            "probability_short": prob_short,
            "p_long_lgb": p_l_lgb, "p_long_cat": p_l_cat, "p_long_xgb": p_l_xgb,
            "p_short_lgb": p_s_lgb, "p_short_cat": p_s_cat, "p_short_xgb": p_s_xgb,
            "ev_long_pips": net_ev_long,
            "ev_short_pips": net_ev_short,
            "regime_state_9": regime_9,
            "ask": event.data.get("ask"),
            "bid": event.data.get("bid"),
            "timestamp": timestamp,
            "rolling_bars_df": bars_df,
            "feature_snapshot": latest_row.to_dict(orient="records")[0] if len(latest_row) > 0 else {}
        }))

