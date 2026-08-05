"""
Feature Analyzer v2
===================
Multiple analysis methods:
  1. MFE Regression (RandomForest) — predicts how much favorable move to expect
  2. Trade Quality Classification — predicts HIGH vs LOW quality setups
  3. Volatility Regime Prediction — predicts future volatility expansion
  4. SHAP Values — directional feature impact (High ATR → Good or Bad?)
  5. Best vs Worst Trade Analysis — feature profile of winners vs losers
  6. Feature stability across time splits
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score, r2_score, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings('ignore')


class FeatureAnalyzer:
    """Multi-model quantitative research analyzer."""

    def __init__(self, n_estimators: int = 200, max_depth: int = 8, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state

    # =================================================================
    # MODEL A: MFE REGRESSION — "How many pips of favorable move?"
    # =================================================================
    def run_mfe_regression(self, df: pd.DataFrame, feature_cols: list) -> dict:
        """Predicts label_mfe_best_atr (ATR-normalized MFE) using regression."""
        target = 'label_mfe_best_atr'
        valid = df[feature_cols + [target]].dropna()

        if len(valid) < 200:
            return {'error': f'Insufficient samples: {len(valid)}'}

        X = valid[feature_cols].values
        y = valid[target].values

        tscv = TimeSeriesSplit(n_splits=5)
        cv_r2 = []
        cv_mae = []

        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            rf = RandomForestRegressor(
                n_estimators=self.n_estimators, max_depth=self.max_depth,
                random_state=self.random_state, n_jobs=-1
            )
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_test)
            cv_r2.append(r2_score(y_test, y_pred))
            cv_mae.append(mean_absolute_error(y_test, y_pred))

        # Final model
        final_rf = RandomForestRegressor(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            random_state=self.random_state, n_jobs=-1
        )
        final_rf.fit(X, y)

        importances = pd.DataFrame({
            'feature': feature_cols,
            'importance': final_rf.feature_importances_
        }).sort_values('importance', ascending=False).reset_index(drop=True)

        return {
            'model_name': 'MFE Regression (RandomForest)',
            'target': target,
            'samples': len(valid),
            'importances': importances,
            'model': final_rf,
            'cv_r2_mean': round(np.mean(cv_r2), 4),
            'cv_r2_std': round(np.std(cv_r2), 4),
            'cv_mae_mean': round(np.mean(cv_mae), 4),
            'cv_r2_scores': [round(s, 4) for s in cv_r2],
        }

    # =================================================================
    # MODEL B: TRADE QUALITY CLASSIFICATION — "Is this a good setup?"
    # =================================================================
    def run_quality_classification(self, df: pd.DataFrame, feature_cols: list) -> dict:
        """Predicts label_trade_quality (HIGH vs LOW)."""
        target = 'label_trade_quality'
        valid = df[feature_cols + [target]].dropna()
        valid = valid[valid[target].isin(['HIGH', 'LOW'])].copy()

        if len(valid) < 200:
            return {'error': f'Insufficient samples: {len(valid)}'}

        X = valid[feature_cols].values
        le = LabelEncoder()
        y = le.fit_transform(valid[target].values)

        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []
        all_y_true, all_y_pred = [], []
        all_y_prob = []

        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            gb = GradientBoostingClassifier(
                n_estimators=self.n_estimators, max_depth=self.max_depth,
                random_state=self.random_state
            )
            gb.fit(X_train, y_train)
            y_pred = gb.predict(X_test)
            y_prob = gb.predict_proba(X_test)

            cv_scores.append(accuracy_score(y_test, y_pred))
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)
            if y_prob.shape[1] == 2:
                all_y_prob.extend(y_prob[:, 1])

        # Final model
        final_gb = GradientBoostingClassifier(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            random_state=self.random_state
        )
        final_gb.fit(X, y)

        importances = pd.DataFrame({
            'feature': feature_cols,
            'importance': final_gb.feature_importances_
        }).sort_values('importance', ascending=False).reset_index(drop=True)

        report = classification_report(all_y_true, all_y_pred,
                                       target_names=le.classes_, output_dict=True)

        return {
            'model_name': 'Trade Quality (GradientBoosting)',
            'target': target,
            'samples': len(valid),
            'class_distribution': dict(zip(le.classes_, np.bincount(y))),
            'importances': importances,
            'model': final_gb,
            'label_encoder': le,
            'cv_accuracy_mean': round(np.mean(cv_scores), 4),
            'cv_accuracy_std': round(np.std(cv_scores), 4),
            'cv_scores': [round(s, 4) for s in cv_scores],
            'classification_report': report,
        }

    # =================================================================
    # MODEL C: VOLATILITY REGIME — "Will volatility expand?"
    # =================================================================
    def run_volatility_prediction(self, df: pd.DataFrame, feature_cols: list) -> dict:
        """Predicts label_vol_regime (HIGH / MEDIUM / LOW)."""
        target = 'label_vol_regime'
        valid = df[feature_cols + [target]].dropna()
        valid = valid[valid[target].isin(['HIGH', 'MEDIUM', 'LOW'])].copy()

        if len(valid) < 200:
            return {'error': f'Insufficient samples: {len(valid)}'}

        X = valid[feature_cols].values
        le = LabelEncoder()
        y = le.fit_transform(valid[target].values)

        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []

        for train_idx, test_idx in tscv.split(X):
            rf = RandomForestClassifier(
                n_estimators=self.n_estimators, max_depth=self.max_depth,
                random_state=self.random_state, n_jobs=-1, class_weight='balanced'
            )
            rf.fit(X[train_idx], y[train_idx])
            cv_scores.append(accuracy_score(y[test_idx], rf.predict(X[test_idx])))

        final_rf = RandomForestClassifier(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            random_state=self.random_state, n_jobs=-1, class_weight='balanced'
        )
        final_rf.fit(X, y)

        importances = pd.DataFrame({
            'feature': feature_cols,
            'importance': final_rf.feature_importances_
        }).sort_values('importance', ascending=False).reset_index(drop=True)

        return {
            'model_name': 'Volatility Regime (RandomForest)',
            'target': target,
            'samples': len(valid),
            'class_distribution': dict(zip(le.classes_, np.bincount(y))),
            'importances': importances,
            'cv_accuracy_mean': round(np.mean(cv_scores), 4),
            'cv_scores': [round(s, 4) for s in cv_scores],
        }

    # =================================================================
    # SHAP ANALYSIS — Directional feature impact
    # =================================================================
    def run_shap_analysis(self, df: pd.DataFrame, feature_cols: list, model, 
                          sample_size: int = 2000) -> pd.DataFrame:
        """
        Computes SHAP values to understand HOW each feature affects the prediction.
        Returns DataFrame: feature, mean_abs_shap, mean_shap (signed direction).
        """
        import shap

        valid = df[feature_cols].dropna()
        if len(valid) > sample_size:
            valid = valid.sample(n=sample_size, random_state=42)

        X = valid[feature_cols].values

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # Handle multi-class (take mean across classes) or single-output
        if isinstance(shap_values, list):
            # Multi-class: average absolute SHAP across classes
            shap_abs = np.mean([np.abs(sv) for sv in shap_values], axis=0)
            shap_signed = np.mean(shap_values, axis=0)
        else:
            shap_abs = np.abs(shap_values)
            shap_signed = shap_values

        result = pd.DataFrame({
            'feature': feature_cols,
            'mean_abs_shap': np.mean(shap_abs, axis=0),
            'mean_shap': np.mean(shap_signed, axis=0),
            'std_shap': np.std(shap_signed, axis=0),
        }).sort_values('mean_abs_shap', ascending=False).reset_index(drop=True)

        return result

    # =================================================================
    # BEST vs WORST TRADE ANALYSIS
    # =================================================================
    def run_best_vs_worst(self, df: pd.DataFrame, feature_cols: list,
                          top_pct: float = 0.10) -> pd.DataFrame:
        """
        Compares feature profiles of top vs bottom trades by MFE.
        """
        valid = df[feature_cols + ['label_mfe_best_atr']].dropna()
        n = len(valid)
        cutoff = int(n * top_pct)

        sorted_df = valid.sort_values('label_mfe_best_atr')
        bottom = sorted_df.head(cutoff)
        top = sorted_df.tail(cutoff)

        results = []
        for feat in feature_cols:
            top_mean = top[feat].mean()
            bot_mean = bottom[feat].mean()
            overall_std = valid[feat].std()
            diff = top_mean - bot_mean
            effect_size = diff / overall_std if overall_std > 0 else 0

            results.append({
                'feature': feat,
                'top10_mean': round(top_mean, 4),
                'bottom10_mean': round(bot_mean, 4),
                'difference': round(diff, 4),
                'effect_size': round(effect_size, 4),
            })

        return pd.DataFrame(results).sort_values('effect_size', ascending=False, key=abs).reset_index(drop=True)

    # =================================================================
    # STABILITY ANALYSIS
    # =================================================================
    def run_stability_analysis(self, df: pd.DataFrame, feature_cols: list,
                                target: str = 'label_mfe_best_atr', n_splits: int = 4) -> pd.DataFrame:
        """Checks feature importance stability across time periods."""
        valid = df[feature_cols + [target]].dropna()
        if len(valid) < 400:
            return pd.DataFrame()

        X = valid[feature_cols].values
        y = valid[target].values
        split_size = len(X) // n_splits
        imp_matrix = []

        for i in range(n_splits):
            s, e = i * split_size, (i + 1) * split_size if i < n_splits - 1 else len(X)
            rf = RandomForestRegressor(n_estimators=100, max_depth=self.max_depth,
                                       random_state=self.random_state, n_jobs=-1)
            rf.fit(X[s:e], y[s:e])
            imp_matrix.append(rf.feature_importances_)

        imp_df = pd.DataFrame(imp_matrix, columns=feature_cols)
        return pd.DataFrame({
            'feature': feature_cols,
            'mean_importance': imp_df.mean().values,
            'std_importance': imp_df.std().values,
            'cv': (imp_df.std() / imp_df.mean().replace(0, 1e-9)).values
        }).sort_values('mean_importance', ascending=False).reset_index(drop=True)
