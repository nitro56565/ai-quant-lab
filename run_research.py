#!/usr/bin/env python3
"""
run_research.py
===============
Quantitative Research Pipeline

This script asks a fundamentally different question than a strategy backtest:

  "What market characteristics predict positive expectancy?"

Pipeline:
  1. Load raw H1 EURUSD data (2018-2026)
  2. Compute 50+ features per candle (no strategy logic)
  3. Label every candle with future outcome (MFE/MAE over next 12 bars)
  4. Train RandomForest on features → label
  5. Rank features by predictive importance
  6. Check stability of importance across time splits
  7. Output findings

The strategy is DISCOVERED from the data, not invented.
"""
import sys
import os
import time
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import FutureLabeler
from research_engine.analyzer import FeatureAnalyzer


# =====================================================================
# CONFIGURATION
# =====================================================================
SYMBOL = "EURUSD"
START_DATE = "2018-01-01"
END_DATE = "2026-06-30"
TIMEFRAME = "1h"

# Labeling parameters
HORIZON = 12        # Look forward 12 H1 bars (12 hours)
MIN_RR = 1.5        # Minimum reward-to-risk ratio
MIN_MOVE_ATR = 1.0  # Minimum MFE in ATR multiples

# Model parameters
N_ESTIMATORS = 200
MAX_DEPTH = 8
# =====================================================================


def main():
    t0 = time.time()

    print("=" * 80)
    print("🔬 QUANTITATIVE RESEARCH ENGINE")
    print("=" * 80)
    print(f"Symbol:     {SYMBOL}")
    print(f"Timeframe:  {TIMEFRAME}")
    print(f"Date Range: {START_DATE} to {END_DATE}")
    print(f"Horizon:    {HORIZON} bars ({HORIZON} hours)")
    print(f"Min R:R:    {MIN_RR}")
    print(f"Min Move:   {MIN_MOVE_ATR} × ATR")
    print("-" * 80)

    # =====================================================================
    # STEP 1: Load raw data
    # =====================================================================
    print("\n⏳ Step 1: Loading raw market data...")
    loader = DataLoader()
    warmup_start = (pd.to_datetime(START_DATE) - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
    req = DataRequest(symbol=SYMBOL, timeframe=TIMEFRAME, start=warmup_start, end=END_DATE)
    df_raw = loader.load(req)
    print(f"   ✅ Loaded {len(df_raw):,} {TIMEFRAME} candles ({df_raw.index[0]} to {df_raw.index[-1]})")

    # =====================================================================
    # STEP 2: Feature Engineering (50+ features)
    # =====================================================================
    print("\n⏳ Step 2: Computing feature matrix (50+ features per candle)...")
    builder = FeatureMatrixBuilder()
    df_featured = builder.build(df_raw)

    feature_cols = builder.get_feature_columns(df_featured)
    print(f"   ✅ Computed {len(feature_cols)} features:")
    # Group by category
    categories = {}
    for col in feature_cols:
        parts = col.split('_')
        if len(parts) >= 2:
            cat = parts[1]
        else:
            cat = 'other'
        categories.setdefault(cat, []).append(col)

    for cat, cols in sorted(categories.items()):
        print(f"      {cat:<12}: {len(cols)} features")

    # =====================================================================
    # STEP 3: Label the future
    # =====================================================================
    print(f"\n⏳ Step 3: Labeling future outcomes (horizon={HORIZON} bars)...")
    labeler = FutureLabeler(horizon=HORIZON, min_rr=MIN_RR, min_move_atr=MIN_MOVE_ATR)
    df_labeled = labeler.label(df_featured)

    # Filter to target date range (remove warmup)
    df_labeled = df_labeled[df_labeled.index >= START_DATE]

    stats = labeler.get_label_stats(df_labeled)
    print(f"   ✅ Label distribution:")
    print(f"      Total bars:  {stats['total_labeled_bars']:,}")
    print(f"      BUY:         {stats['BUY']:,} ({stats['buy_pct']:.1f}%)")
    print(f"      SELL:        {stats['SELL']:,} ({stats['sell_pct']:.1f}%)")
    print(f"      NO_TRADE:    {stats['NO_TRADE']:,} ({stats['no_trade_pct']:.1f}%)")

    # =====================================================================
    # STEP 4: Feature Importance Analysis
    # =====================================================================
    print(f"\n⏳ Step 4: Training RandomForest classifier (n={N_ESTIMATORS}, depth={MAX_DEPTH})...")
    print(f"   Using TimeSeriesSplit cross-validation (5 folds, no shuffle)...")

    # Exclude non-numeric, swing prices (absolute levels), and label columns
    exclude = ['feat_struct_swing_high', 'feat_struct_swing_low',
               'feat_time_hour', 'feat_time_dow', 'feat_time_month']
    analysis_features = [c for c in feature_cols if c not in exclude]

    analyzer = FeatureAnalyzer(n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH)
    results = analyzer.run_importance_analysis(df_labeled, analysis_features)
    analyzer.print_report(results)

    # =====================================================================
    # STEP 5: Stability Analysis
    # =====================================================================
    print("\n⏳ Step 5: Running feature stability analysis (4 time splits)...")
    stability = analyzer.run_stability_analysis(df_labeled, analysis_features)

    if not stability.empty:
        print("\n" + "-" * 80)
        print("📊 FEATURE STABILITY (Coefficient of Variation across time splits)")
        print("-" * 80)
        print(f"{'Rank':<6}{'Feature':<40}{'Mean Imp.':<12}{'CV':<10}{'Verdict':<12}")
        print("-" * 80)

        for i, row in stability.head(20).iterrows():
            cv = row['cv']
            if cv < 0.3:
                verdict = "✅ Stable"
            elif cv < 0.6:
                verdict = "⚠️ Moderate"
            else:
                verdict = "❌ Unstable"
            print(f"{i+1:<6}{row['feature']:<40}{row['mean_importance']:<12.4f}{cv:<10.3f}{verdict:<12}")

    elapsed = time.time() - t0
    print(f"\n⏱️  Total research time: {elapsed:.1f}s")
    print("=" * 80)

    # =====================================================================
    # STEP 6: Save results
    # =====================================================================
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

    if 'importances' in results:
        results['importances'].to_csv(os.path.join(output_dir, 'research_feature_importance.csv'), index=False)
        print(f"\n💾 Feature importance saved to: research_feature_importance.csv")

    if not stability.empty:
        stability.to_csv(os.path.join(output_dir, 'research_feature_stability.csv'), index=False)
        print(f"💾 Feature stability saved to: research_feature_stability.csv")


if __name__ == '__main__':
    main()
