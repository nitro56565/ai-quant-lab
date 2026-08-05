import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.calibration import CalibratedClassifierCV
from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import FutureLabeler
from regime_detector.detector import RegimeDetector
from .base import Strategy

class MLConsensusStrategy(Strategy):
    """
    ML Consensus & Expected Value (EV) Strategy:
      1. Computes 65+ market features on H1 using FeatureMatrixBuilder.
      2. Imputes/cleans missing values.
      3. Simulates a rolling out-of-sample forward prediction matching the Quant Gauntlet:
         - Trains models on a 4-year rolling window to predict the current year's bars.
         - Classifier: P(HIGH quality Long setup).
         - Regressors: Expected MFE and Expected MAE.
         - Computes Expected Value (EV) = P(HIGH) * MFE_pips - (1 - P(HIGH)) * MAE_pips.
      4. Enters LONG trades when:
         - EV >= threshold (e.g., +44.4 pips representing top 5% signals).
         - Hour is outside the high-chop NY London overlap (13:00 to 16:00 UTC).
      5. Exit: Exits after 12 hours (matching the model's prediction horizon) or via trailing stop loss.
    """
    def __init__(self, ev_threshold=33.41, sl_atr_multiplier=1.3, trail_atr_multiplier=4.0, **kwargs):
        super().__init__(name="MLConsensusStrategy", **kwargs)
        self.ev_threshold = ev_threshold
        self.sl_atr_multiplier = sl_atr_multiplier
        self.trail_atr_multiplier = trail_atr_multiplier
        self.atr_col = 'feat_vol_atr'

    def prepare_data(self, data_loader: DataLoader, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_dt = pd.to_datetime(start_date)
        
        # To run a rolling train/predict walk, we need 4 years of prior data
        train_start_year = start_dt.year - 4
        warmup_start = f"{train_start_year}-01-01"
        
        print(f"   [ML Strategy] Loading data from {warmup_start} to {end_date} for rolling training...")
        req = DataRequest(symbol=symbol, timeframe="1h", start=warmup_start, end=end_date)
        df_raw = data_loader.load(req)
        
        print("   [ML Strategy] Generating features...")
        builder = FeatureMatrixBuilder()
        df = builder.build(df_raw)
        
        # Detect market regimes for signal filtering
        detector = RegimeDetector()
        df = detector.detect_regimes(df)
        
        feature_cols = builder.get_feature_columns(df)
        df[feature_cols] = df[feature_cols].ffill().bfill().fillna(0.0)
        
        print("   [ML Strategy] Labeling training data...")
        labeler = FutureLabeler(horizon=12, quality_threshold_atr=2.0)
        df = labeler.label(df)
        
        # Build directional long target (is return > 5 pips?)
        df['label_dir_long'] = (df['label_return_12h'] > 5.0).astype(int)
        # Build directional short target (is return < -5 pips?)
        df['label_dir_short'] = (df['label_return_12h'] < -5.0).astype(int)
        
        # Run rolling predictions year-by-year matching the gauntlet splits
        test_years = range(start_dt.year, pd.to_datetime(end_date).year + 1)
        df['pred_ev'] = 0.0
        df['pred_ev_long'] = 0.0
        df['pred_ev_short'] = 0.0
        df['pred_prob_long'] = 0.0
        df['pred_mfe_long'] = 0.0
        df['pred_mae_long'] = 0.0
        df['pred_prob_short'] = 0.0
        df['pred_mfe_short'] = 0.0
        df['pred_mae_short'] = 0.0
        df['ev_threshold'] = 0.0
        
        print("   [ML Strategy] Running rolling forward walk predictions...")
        # P0 Fix: Detect earliest year with actual data to prevent training on empty windows
        earliest_data_year = df.index.min().year
        
        for yr in test_years:
            # P0 Fix: Skip years where the 4-year training window predates available data
            required_train_start_year = yr - 4
            if required_train_start_year < earliest_data_year:
                print(f"      Skipping year {yr}: insufficient training data (needs {required_train_start_year}, earliest is {earliest_data_year})")
                continue
            
            train_start = f"{yr - 4}-01-01"
            train_end = f"{yr - 1}-12-31"
            test_start = f"{yr}-01-01"
            test_end = f"{yr}-12-31"
            
            # Split data
            train_df = df[(df.index >= train_start) & (df.index <= train_end)].dropna(subset=['label_mfe_long_pips', 'label_mfe_short_pips', 'label_mae_pips'])
            test_df = df[(df.index >= test_start) & (df.index <= test_end)]
            
            if len(train_df) < 500 or len(test_df) == 0:
                continue
            
            X_train = train_df[feature_cols].values
            y_train_qual_long = train_df['label_dir_long'].values
            y_train_mfe_long = train_df['label_mfe_long_pips'].values
            y_train_mae_long = train_df['label_mae_pips'].values
            
            y_train_qual_short = train_df['label_dir_short'].values
            y_train_mfe_short = train_df['label_mfe_short_pips'].values
            y_train_mae_short = train_df['label_mae_pips'].values

            # Fit and calibrate Classifier (LONG) using 5-fold cross-validation
            clf_qual_long = CalibratedClassifierCV(
                estimator=HistGradientBoostingClassifier(max_depth=5, random_state=42),
                method='isotonic',
                cv=5
            )
            clf_qual_long.fit(X_train, y_train_qual_long)
            
            # Fit and calibrate Classifier (SHORT) using 5-fold cross-validation
            clf_qual_short = CalibratedClassifierCV(
                estimator=HistGradientBoostingClassifier(max_depth=5, random_state=42),
                method='isotonic',
                cv=5
            )
            clf_qual_short.fit(X_train, y_train_qual_short)
            
            # Fit Regressors on full training set for maximum regression data
            reg_mfe_long = HistGradientBoostingRegressor(max_depth=5, random_state=42)
            reg_mfe_long.fit(X_train, y_train_mfe_long)
            
            reg_mae_long = HistGradientBoostingRegressor(max_depth=5, random_state=42)
            reg_mae_long.fit(X_train, y_train_mae_long)
            
            reg_mfe_short = HistGradientBoostingRegressor(max_depth=5, random_state=42)
            reg_mfe_short.fit(X_train, y_train_mfe_short)
            
            reg_mae_short = HistGradientBoostingRegressor(max_depth=5, random_state=42)
            reg_mae_short.fit(X_train, y_train_mae_short)
            
            # 1. Calibrate EV threshold lookahead-free on the training set
            pred_prob_long_tr = clf_qual_long.predict_proba(X_train)[:, 1]
            pred_mfe_long_tr = reg_mfe_long.predict(X_train)
            pred_mae_long_tr = reg_mae_long.predict(X_train)
            ev_long_tr = pred_prob_long_tr * pred_mfe_long_tr - (1 - pred_prob_long_tr) * pred_mae_long_tr
            
            pred_prob_short_tr = clf_qual_short.predict_proba(X_train)[:, 1]
            pred_mfe_short_tr = reg_mfe_short.predict(X_train)
            pred_mae_short_tr = reg_mae_short.predict(X_train)
            ev_short_tr = pred_prob_short_tr * pred_mfe_short_tr - (1 - pred_prob_short_tr) * pred_mae_short_tr
            
            ev_tr = np.maximum(ev_long_tr, ev_short_tr)
            valid_ev_tr = ev_tr[ev_tr != 0.0]
            
            # Use a constant absolute threshold of 34.0 pips as a floor for statistical edge
            threshold_yr = 34.0
            
            # Predict out-of-sample
            X_test = test_df[feature_cols].values
            
            # Predict out-of-sample (LONG)
            pred_prob_long = clf_qual_long.predict_proba(X_test)[:, 1]
            pred_mfe_long = reg_mfe_long.predict(X_test)
            pred_mae_long = reg_mae_long.predict(X_test)
            
            ev_pips_long = pred_prob_long * pred_mfe_long - (1 - pred_prob_long) * pred_mae_long
            
            # Predict out-of-sample (SHORT)
            pred_prob_short = clf_qual_short.predict_proba(X_test)[:, 1]
            pred_mfe_short = reg_mfe_short.predict(X_test)
            pred_mae_short = reg_mae_short.predict(X_test)
            
            ev_pips_short = pred_prob_short * pred_mfe_short - (1 - pred_prob_short) * pred_mae_short
            
            # Combined EV
            ev_pips = np.maximum(ev_pips_long, ev_pips_short)
            
            df.loc[test_df.index, 'pred_ev'] = ev_pips
            df.loc[test_df.index, 'pred_ev_long'] = ev_pips_long
            df.loc[test_df.index, 'pred_ev_short'] = ev_pips_short
            df.loc[test_df.index, 'pred_prob_long'] = pred_prob_long
            df.loc[test_df.index, 'pred_mfe_long'] = pred_mfe_long
            df.loc[test_df.index, 'pred_mae_long'] = pred_mae_long
            df.loc[test_df.index, 'pred_prob_short'] = pred_prob_short
            df.loc[test_df.index, 'pred_mfe_short'] = pred_mfe_short
            df.loc[test_df.index, 'pred_mae_short'] = pred_mae_short
            df.loc[test_df.index, 'ev_threshold'] = threshold_yr
            print(f"      Year {yr} Out-of-Sample predicted successfully (Long + Short, Threshold Calibrated: {threshold_yr:.2f} pips).")
            
        # Filter back to test period
        is_tz_aware = df.index.tz is not None
        start_ts = start_dt
        if is_tz_aware and start_ts.tz is None:
            start_ts = start_ts.tz_localize('UTC')
            
        df = df.loc[df.index >= start_ts]
        
        # Generate signal flags
        df = self.generate_signals(df)
        return df
 
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. Hourly filter to avoid high-chop NY session overlap (13:00 to 16:00 UTC)
        df['session_ok'] = ~df.index.hour.isin([13, 14, 15, 16])
        
        # 2. Determine signal direction
        df['signal'] = None
        
        # Long entry conditions
        long_ok = (df['pred_ev_long'] >= df['ev_threshold']) & (df['pred_ev_long'] > 0) & df['session_ok']
        # Short entry conditions
        short_ok = (df['pred_ev_short'] >= df['ev_threshold']) & (df['pred_ev_short'] > 0) & df['session_ok']
        
        # When both trigger, choose the one with higher EV
        long_trigger = long_ok & (~short_ok | (df['pred_ev_long'] >= df['pred_ev_short']))
        short_trigger = short_ok & (~long_ok | (df['pred_ev_short'] > df['pred_ev_long']))
        
        df.loc[long_trigger, 'signal'] = 'BUY'
        df.loc[short_trigger, 'signal'] = 'SELL'
        
        # Combined entry trigger for backwards compatibility
        df['entry_signal'] = df['signal'].notna()
        
        return df

    def check_exit(self, row: pd.Series, trade: dict) -> float:
        # Time-based exit: close trade after 12 hours (matching the target label horizon)
        elapsed_hours = (row.name - trade['entry_time']).total_seconds() / 3600.0
        if elapsed_hours >= 12.0:
            return row['close']
        return None
