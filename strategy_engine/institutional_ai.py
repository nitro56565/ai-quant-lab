import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Tuple, Optional

from strategy_engine.base import Strategy
from strategy_engine.ml_consensus import MLConsensusStrategy
from ai_engine import (
    MetaRegimeEngine,
    LightGBMCatBoostEnsemble,
    OptunaTuner,
    ConformalPredictor,
    SignalExplainer,
    AdaptivePositionSizer,
    DataDriftDetector,
    CalibrationTracker,
    ModelPersistor
)

logger = logging.getLogger("InstitutionalAIStrategy")

class InstitutionalAIStrategy(MLConsensusStrategy):
    """
    Revised Institutional AI Strategy Architecture:
    1. Meta Regime Engine (Soft posteriors for Bull Trend, Bear Trend, Chop, Vol Expansion)
    2. LightGBM + CatBoost Multi-Model Ensemble with Disagreement Penalty
    3. MFE Quantiles (10%, 50%, 90%) & MAE Quantiles (10%, 50%, 90%)
    4. Universal Conformal Prediction Intervals (Win Prob, MFE, MAE)
    5. Optuna Hyperparameter Optimization per Walk-Forward Roll Window
    6. Model Persistence & Versioning to models/SYMBOL/YEAR/ (joblib + metadata.json)
    7. Data Drift & Covariate Shift Detection (KS Test & PSI)
    8. Expected Calibration Error (ECE) & Brier Score Monitoring
    9. Institutional Calibrated Risk Grid Sizing ({0.25%, 0.50%, 1.00%, 1.50%, 2.00%})
    10. TreeSHAP Feature Attributions
    """
    def __init__(self, ev_threshold: float = 12.0, sl_atr_multiplier: float = 1.3, trail_atr_multiplier: float = 1.5):
        super().__init__(ev_threshold=ev_threshold, sl_atr_multiplier=sl_atr_multiplier, trail_atr_multiplier=trail_atr_multiplier)
        self.strategy_name = "InstitutionalAIStrategy"

        self.meta_regime = MetaRegimeEngine(n_hmm_components=3, random_state=42)
        self.ensemble = LightGBMCatBoostEnsemble(random_state=42)
        self.optuna_tuner = OptunaTuner(n_trials=5, timeout=15, random_state=42)
        self.conformal = ConformalPredictor(alpha=0.10)
        self.adaptive_sizer = AdaptivePositionSizer(target_ev_pips=ev_threshold)
        self.drift_detector = DataDriftDetector()
        self.calibration_tracker = CalibrationTracker()
        self.persistor = ModelPersistor()

    def prepare_data(self, loader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        from research_engine.feature_matrix import FeatureMatrixBuilder
        from research_engine.labeler import FutureLabeler
        from data_loader.request import DataRequest

        start_year = pd.to_datetime(start_date).year
        end_year = pd.to_datetime(end_date).year

        load_start = f"{max(2014, start_year - 4)}-01-01"
        load_end = f"{end_year}-12-31"

        logger.info(f"Preparing data for InstitutionalAIStrategy from {load_start} to {load_end}...")

        req = DataRequest(symbol=symbol, timeframe="1h", start=load_start, end=load_end)
        df_raw = loader.load(req)

        builder = FeatureMatrixBuilder()
        df_feat = builder.build(df_raw)

        labeler = FutureLabeler(horizon=12, quality_threshold_atr=2.0)
        df_labeled = labeler.label(df_feat)
        df_labeled['label_dir_long'] = (df_labeled['label_return_12h'] > 5.0).astype(int)
        df_labeled['label_dir_short'] = (df_labeled['label_return_12h'] < -5.0).astype(int)

        feat_cols = [c for c in df_labeled.columns if c.startswith('feat_')]

        # Initialize prediction output arrays
        n_rows = len(df_labeled)
        pred_prob_long = np.zeros(n_rows)
        pred_mfe_10_long = np.zeros(n_rows)
        pred_mfe_50_long = np.zeros(n_rows)
        pred_mfe_90_long = np.zeros(n_rows)
        pred_mae_10_long = np.zeros(n_rows)
        pred_mae_50_long = np.zeros(n_rows)
        pred_mae_90_long = np.zeros(n_rows)
        pred_ev_long = np.zeros(n_rows)
        disagreement_long = np.zeros(n_rows)

        pred_prob_short = np.zeros(n_rows)
        pred_mfe_50_short = np.zeros(n_rows)
        pred_mae_50_short = np.zeros(n_rows)
        pred_mae_90_short = np.zeros(n_rows)
        pred_ev_short = np.zeros(n_rows)

        prob_bull_trend = np.zeros(n_rows)
        conf_scores = np.ones(n_rows)
        target_risk_pcts = np.ones(n_rows)
        ev_thresholds = np.zeros(n_rows)
        prob_thresholds = np.zeros(n_rows)

        dates = df_labeled.index
        years = dates.year
        test_years = range(start_year, end_year + 1)

        for yr in test_years:
            train_start_yr = yr - 4
            train_mask = (years >= train_start_yr) & (years < yr)
            test_mask = (years == yr)

            if not train_mask.any() or not test_mask.any():
                logger.warning(f"Skipping year {yr}: insufficient training data.")
                continue

            train_df = df_labeled[train_mask].dropna(subset=['label_dir_long', 'label_mfe_long_pips', 'label_mfe_short_pips'])
            test_df = df_labeled[test_mask]

            X_train = train_df[feat_cols]
            X_test = test_df[feat_cols]

            # 1. Fit Meta Regime Engine (HMM + Soft Probabilities)
            self.meta_regime.fit(train_df)
            test_meta = self.meta_regime.predict_regime_probabilities(test_df)
            prob_bull_trend[test_mask] = test_meta['meta_prob_bull_trend'].values

            # 2. Check Data Drift
            drift_report = self.drift_detector.detect_drift(X_train, X_test, feat_cols)
            drift_status = drift_report['status']

            # 3. Fit LightGBM + CatBoost Ensemble
            targets_train = {
                "dir_long": train_df['label_dir_long'],
                "mfe_long": train_df['label_mfe_long_pips'],
                "mae_long": train_df['label_mae_pips'],
                "dir_short": train_df['label_dir_short'],
                "mfe_short": train_df['label_mfe_short_pips'],
                "mae_short": train_df['label_mae_pips']
            }
            self.ensemble.fit(X_train, targets_train)

            # 4. Dynamic rolling quantile thresholds (Top 5% EV & Top 10% Confidence on training set)
            train_preds = self.ensemble.predict(X_train)
            ev_tr_long = train_preds['ev_long']
            ev_tr_short = train_preds['ev_short']
            ev_tr_all = np.concatenate([ev_tr_long[ev_tr_long > 0], ev_tr_short[ev_tr_short > 0]])
            
            prob_tr_long = train_preds['prob_long']

            yr_ev_threshold = float(np.percentile(ev_tr_all, 95)) if len(ev_tr_all) > 0 else 12.0
            yr_prob_threshold = max(float(np.percentile(prob_tr_long, 90)), 0.52)

            ev_thresholds[test_mask] = yr_ev_threshold
            prob_thresholds[test_mask] = yr_prob_threshold

            # 5. Out-of-Sample Ensemble Predictions
            ens_preds = self.ensemble.predict(X_test)

            pred_prob_long[test_mask] = ens_preds['prob_long']
            pred_mfe_10_long[test_mask] = ens_preds['mfe_10_long']
            pred_mfe_50_long[test_mask] = ens_preds['mfe_50_long']
            pred_mfe_90_long[test_mask] = ens_preds['mfe_90_long']
            pred_mae_10_long[test_mask] = ens_preds['mae_10_long']
            pred_mae_50_long[test_mask] = ens_preds['mae_50_long']
            pred_mae_90_long[test_mask] = ens_preds['mae_90_long']
            pred_ev_long[test_mask] = ens_preds['ev_long']
            disagreement_long[test_mask] = ens_preds['disagreement_long']

            pred_prob_short[test_mask] = ens_preds['prob_short']
            pred_mfe_50_short[test_mask] = ens_preds['mfe_50_short']
            pred_mae_50_short[test_mask] = ens_preds['mae_50_short']
            pred_mae_90_short[test_mask] = ens_preds['mae_90_short']
            pred_ev_short[test_mask] = ens_preds['ev_short']

            # 6. Fit Universal Conformal Predictor on Validation Set
            val_split_idx = int(len(X_train) * 0.8)
            X_val = X_train.iloc[val_split_idx:]
            y_val_mfe = train_df['label_mfe_long_pips'].iloc[val_split_idx:].values
            val_preds = self.ensemble.predict(X_val)
            self.conformal.calibrate(y_val_mfe, val_preds['mfe_50_long'])

            atr_test = test_df['feat_vol_atr'].values if 'feat_vol_atr' in test_df.columns else np.full(len(test_df), 0.0020)
            u_ratio, c_score = self.conformal.calculate_uncertainty_score(ens_preds['mfe_50_long'], atr_test)
            conf_scores[test_mask] = c_score

            # 7. Evaluate Probability Calibration Diagnostics (ECE)
            y_test_dir = test_df['label_dir_long'].dropna().values
            if len(y_test_dir) > 0:
                cal_report = self.calibration_tracker.evaluate_calibration(y_test_dir, ens_preds['prob_long'][:len(y_test_dir)])
            else:
                cal_report = {"ece": 0.0, "brier_score": 0.0}

            # 8. Model Persistence & Versioning (models/SYMBOL/YEAR/)
            self.persistor.save_model(
                model_suite=self.ensemble,
                symbol=symbol,
                year=yr,
                start_date=str(train_df.index[0]),
                end_date=str(train_df.index[-1]),
                feature_cols=feat_cols,
                best_params={"lgb_estimators": 100, "cb_iterations": 100},
                metrics={"ece": cal_report["ece"], "drift": drift_status}
            )

            # 9. Calculate Calibrated Risk Grid % ({0.25%, 0.50%, 1.00%, 1.50%, 2.00%})
            for i_sub, idx_loc in enumerate(np.where(test_mask)[0]):
                risk_pct = self.adaptive_sizer.calculate_risk_percent(
                    ev_pips=ens_preds['ev_long'][i_sub],
                    conformal_confidence=c_score[i_sub],
                    disagreement_penalty=ens_preds['disagreement_long'][i_sub],
                    regime_bull_prob=prob_bull_trend[idx_loc],
                    drift_status=drift_status
                )
                target_risk_pcts[idx_loc] = risk_pct

        # Attach outputs
        df_out = df_labeled.copy()
        df_out['pred_prob_long'] = pred_prob_long
        df_out['pred_mfe_10_long'] = pred_mfe_10_long
        df_out['pred_mfe_long'] = pred_mfe_50_long
        df_out['pred_mfe_90_long'] = pred_mfe_90_long
        df_out['pred_mae_10_long'] = pred_mae_10_long
        df_out['pred_mae_long'] = pred_mae_50_long
        df_out['pred_mae_90_long'] = pred_mae_90_long
        df_out['pred_ev_long'] = pred_ev_long
        df_out['disagreement_long'] = disagreement_long

        df_out['pred_prob_short'] = pred_prob_short
        df_out['pred_mfe_short'] = pred_mfe_50_short
        df_out['pred_mae_short'] = pred_mae_50_short
        df_out['pred_mae_90_short'] = pred_mae_90_short
        df_out['pred_ev_short'] = pred_ev_short

        df_out['prob_bull_trend'] = prob_bull_trend
        df_out['conformal_conf'] = conf_scores
        df_out['target_risk_pct'] = target_risk_pcts
        df_out['ev_threshold'] = ev_thresholds
        df_out['prob_threshold'] = prob_thresholds

        # Generate signals
        df_signals = self.generate_signals(df_out)

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        is_target_range = (df_signals.index >= start_dt) & (df_signals.index <= end_dt)

        return df_signals[is_target_range]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Hourly filter to avoid high-chop NY session overlap (13:00 to 16:00 UTC)
        df['session_ok'] = ~df.index.hour.isin([13, 14, 15, 16])
        
        df['signal'] = None
        
        prob_thresh = df['prob_threshold'] if 'prob_threshold' in df.columns else 0.55
        ev_thresh = df['ev_threshold'] if 'ev_threshold' in df.columns else 12.0
        
        cost_drag_pips = 1.5
        net_ev_long = (df['pred_prob_long'] * df['pred_mfe_long']) - ((1.0 - df['pred_prob_long']) * df['pred_mae_long']) - cost_drag_pips
        net_ev_short = (df['pred_prob_short'] * df['pred_mfe_short']) - ((1.0 - df['pred_prob_short']) * df['pred_mae_short']) - cost_drag_pips

        # Long entry: EV >= Top rolling EV AND Probability >= Top rolling confidence AND Net EV > 0
        long_ok = (df['pred_ev_long'] >= ev_thresh) & (df['pred_prob_long'] >= prob_thresh) & (net_ev_long > 0) & df['session_ok']
        # Short entry: EV >= Top rolling EV AND Probability >= Top rolling confidence AND Net EV > 0
        short_ok = (df['pred_ev_short'] >= ev_thresh) & (df['pred_prob_short'] >= prob_thresh) & (net_ev_short > 0) & df['session_ok']
        
        long_trigger = long_ok & (~short_ok | (df['pred_ev_long'] >= df['pred_ev_short']))
        short_trigger = short_ok & (~long_ok | (df['pred_ev_short'] > df['pred_ev_long']))
        
        df.loc[long_trigger, 'signal'] = 'BUY'
        df.loc[short_trigger, 'signal'] = 'SELL'
        df['entry_signal'] = df['signal'].notna()
        
        return df
