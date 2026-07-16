"""
Feature Analyzer
================
Runs statistical analysis on the feature matrix + labels to discover
which features predict positive expectancy.

Methods:
  1. RandomForest feature importance (Gini / permutation)
  2. Correlation analysis (feature vs future return)
  3. Feature stability analysis (importance across time splits)
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings('ignore')


class FeatureAnalyzer:
    """
    Discovers which features predict future price direction
    using statistical and ML methods.
    """

    def __init__(self, n_estimators: int = 200, max_depth: int = 8, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state

    def run_importance_analysis(self, df: pd.DataFrame, feature_cols: list,
                                label_col: str = 'label') -> dict:
        """
        Trains a RandomForest classifier on features → label and returns
        feature importances ranked by predictive power.

        Args:
            df: DataFrame with feature columns and label column.
            feature_cols: List of feature column names.
            label_col: Column containing BUY/SELL/NO_TRADE labels.

        Returns:
            dict with keys:
              - importances: DataFrame of features ranked by importance
              - model: trained RandomForest model
              - accuracy: out-of-sample accuracy
              - classification_report: per-class precision/recall
              - cv_scores: cross-validation accuracy scores
        """
        # Drop rows with NaN in features or labels
        valid = df[feature_cols + [label_col]].dropna()
        valid = valid[valid[label_col] != 'NO_TRADE'].copy()  # Only trade-worthy bars

        if len(valid) < 100:
            return {
                'error': f'Insufficient labeled samples: {len(valid)} (need >= 100)',
                'total_samples': len(valid)
            }

        X = valid[feature_cols].values
        le = LabelEncoder()
        y = le.fit_transform(valid[label_col].values)

        # Time-series cross-validation (no shuffle to avoid lookahead)
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = []
        all_y_true = []
        all_y_pred = []

        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            rf = RandomForestClassifier(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=self.random_state,
                n_jobs=-1,
                class_weight='balanced'
            )
            rf.fit(X_train, y_train)
            y_pred = rf.predict(X_test)

            cv_scores.append(accuracy_score(y_test, y_pred))
            all_y_true.extend(y_test)
            all_y_pred.extend(y_pred)

        # Train final model on full data for importance extraction
        final_rf = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.random_state,
            n_jobs=-1,
            class_weight='balanced'
        )
        final_rf.fit(X, y)

        # Extract and rank importances
        importances = pd.DataFrame({
            'feature': feature_cols,
            'importance': final_rf.feature_importances_
        }).sort_values('importance', ascending=False).reset_index(drop=True)

        # Compute correlation with raw return
        correlations = []
        if 'label_return_pips' in df.columns:
            for feat in feature_cols:
                corr = df[[feat, 'label_return_pips']].dropna().corr().iloc[0, 1]
                correlations.append(corr)
        else:
            correlations = [0.0] * len(feature_cols)

        importances['return_correlation'] = [
            correlations[feature_cols.index(f)] for f in importances['feature']
        ]

        report = classification_report(
            all_y_true, all_y_pred,
            target_names=le.classes_,
            output_dict=True
        )

        return {
            'importances': importances,
            'model': final_rf,
            'label_encoder': le,
            'total_samples': len(valid),
            'class_distribution': dict(zip(le.classes_, np.bincount(y))),
            'cv_accuracy_mean': round(np.mean(cv_scores), 4),
            'cv_accuracy_std': round(np.std(cv_scores), 4),
            'cv_scores': [round(s, 4) for s in cv_scores],
            'classification_report': report
        }

    def run_stability_analysis(self, df: pd.DataFrame, feature_cols: list,
                                label_col: str = 'label', n_splits: int = 4) -> pd.DataFrame:
        """
        Checks if feature importance is stable across different time periods.
        Trains separate models on each time split and compares rankings.

        Returns DataFrame with feature importance per split and coefficient of variation.
        """
        valid = df[feature_cols + [label_col]].dropna()
        valid = valid[valid[label_col] != 'NO_TRADE'].copy()

        if len(valid) < 200:
            return pd.DataFrame()

        X = valid[feature_cols].values
        le = LabelEncoder()
        y = le.fit_transform(valid[label_col].values)

        split_size = len(X) // n_splits
        importance_matrix = []

        for i in range(n_splits):
            start = i * split_size
            end = start + split_size if i < n_splits - 1 else len(X)

            X_split = X[start:end]
            y_split = y[start:end]

            if len(np.unique(y_split)) < 2:
                continue

            rf = RandomForestClassifier(
                n_estimators=100,
                max_depth=self.max_depth,
                random_state=self.random_state,
                n_jobs=-1,
                class_weight='balanced'
            )
            rf.fit(X_split, y_split)
            importance_matrix.append(rf.feature_importances_)

        if not importance_matrix:
            return pd.DataFrame()

        imp_df = pd.DataFrame(importance_matrix, columns=feature_cols)

        result = pd.DataFrame({
            'feature': feature_cols,
            'mean_importance': imp_df.mean().values,
            'std_importance': imp_df.std().values,
            'cv': (imp_df.std() / imp_df.mean().replace(0, 1e-9)).values
        }).sort_values('mean_importance', ascending=False).reset_index(drop=True)

        return result

    def print_report(self, results: dict):
        """Pretty-prints the analysis results to stdout."""
        if 'error' in results:
            print(f"\n❌ {results['error']}")
            return

        print("\n" + "=" * 80)
        print("📊 QUANTITATIVE FEATURE IMPORTANCE ANALYSIS")
        print("=" * 80)

        print(f"\n📈 Dataset: {results['total_samples']} labeled samples")
        print(f"📊 Class Distribution: {results['class_distribution']}")
        print(f"🎯 Cross-Validation Accuracy: {results['cv_accuracy_mean']:.2%} ± {results['cv_accuracy_std']:.2%}")
        print(f"   Fold Scores: {results['cv_scores']}")

        print("\n" + "-" * 80)
        print("🏆 TOP 25 FEATURES BY PREDICTIVE IMPORTANCE")
        print("-" * 80)
        print(f"{'Rank':<6}{'Feature':<40}{'Importance':<14}{'Corr w/ Return':<16}")
        print("-" * 80)

        imp = results['importances']
        for i, row in imp.head(25).iterrows():
            corr_str = f"{row['return_correlation']:+.4f}" if not np.isnan(row['return_correlation']) else "N/A"
            print(f"{i+1:<6}{row['feature']:<40}{row['importance']:<14.4f}{corr_str:<16}")

        print("\n" + "-" * 80)
        print("📉 BOTTOM 10 (LEAST USEFUL FEATURES)")
        print("-" * 80)
        for i, row in imp.tail(10).iterrows():
            print(f"{i+1:<6}{row['feature']:<40}{row['importance']:<14.4f}")

        # Classification report
        report = results['classification_report']
        print("\n" + "-" * 80)
        print("📋 CLASSIFICATION REPORT (Per-Class Precision/Recall)")
        print("-" * 80)
        for cls in ['BUY', 'SELL']:
            if cls in report:
                r = report[cls]
                print(f"  {cls:>6}: Precision={r['precision']:.2%}  Recall={r['recall']:.2%}  F1={r['f1-score']:.2%}  Support={int(r['support'])}")

        print("=" * 80)
