#!/usr/bin/env python3
"""
run_research.py v2 — Quantitative Research Engine
==================================================
Asks the RIGHT questions:

  Model A: "How many pips of favorable move to expect?" (MFE Regression)
  Model B: "Is this a high-quality trade setup?"        (Quality Classification)
  Model C: "Will volatility expand?"                    (Volatility Regime)
  SHAP:    "HOW does each feature affect the outcome?"  (Directional impact)
  Best/Worst: "What separates winners from losers?"     (Feature profiling)
"""
import sys, os, time
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import DataLoader, DataRequest
from research_engine.feature_matrix import FeatureMatrixBuilder
from research_engine.labeler import FutureLabeler
from research_engine.analyzer import FeatureAnalyzer

# =====================================================================
SYMBOL = "EURUSD"
START_DATE = "2018-01-01"
END_DATE = "2026-06-30"
TIMEFRAME = "1h"
HORIZON = 12
QUALITY_THRESHOLD_ATR = 2.0   # Tighter: MFE must be >= 2.0 × ATR
# =====================================================================


def print_importances(title, importances, top_n=15):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")
    print(f"  {'Rank':<5}{'Feature':<42}{'Importance':<12}")
    print(f"  {'─' * 60}")
    for i, row in importances.head(top_n).iterrows():
        print(f"  {i+1:<5}{row['feature']:<42}{row['importance']:<12.4f}")


def main():
    t0 = time.time()
    print("=" * 70)
    print("🔬 QUANTITATIVE RESEARCH ENGINE v2")
    print("   Asking the right questions")
    print("=" * 70)
    print(f"  Symbol:     {SYMBOL} | Timeframe: {TIMEFRAME}")
    print(f"  Range:      {START_DATE} → {END_DATE}")
    print(f"  Horizon:    {HORIZON} bars | Quality: ≥{QUALITY_THRESHOLD_ATR} ATR MFE + 2:1 R:R")
    print("─" * 70)

    # ── STEP 1: Load data ──
    print("\n⏳ Step 1: Loading data...")
    loader = DataLoader()
    warmup = (pd.to_datetime(START_DATE) - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
    df_raw = loader.load(DataRequest(symbol=SYMBOL, timeframe=TIMEFRAME, start=warmup, end=END_DATE))
    print(f"   ✅ {len(df_raw):,} candles loaded")

    # ── STEP 2: Features ──
    print("\n⏳ Step 2: Computing 65+ features (including 12 interaction features)...")
    builder = FeatureMatrixBuilder()
    df = builder.build(df_raw)
    feature_cols = builder.get_feature_columns(df)

    cats = {}
    for c in feature_cols:
        cat = c.split('_')[1]
        cats.setdefault(cat, []).append(c)
    for cat, cols in sorted(cats.items()):
        print(f"      {cat:<12}: {len(cols)} features")
    print(f"   ✅ Total: {len(feature_cols)} features")

    # ── STEP 3: Labels ──
    print(f"\n⏳ Step 3: Labeling future outcomes...")
    labeler = FutureLabeler(horizon=HORIZON, quality_threshold_atr=QUALITY_THRESHOLD_ATR)
    df = labeler.label(df)
    df = df[df.index >= START_DATE]

    stats = labeler.get_label_stats(df)
    print(f"   Total bars:        {stats['total_bars']:,}")
    print(f"   HIGH quality:      {stats['quality_HIGH']:,} ({stats['quality_HIGH_pct']:.1f}%)")
    print(f"   LOW quality:       {stats['quality_LOW']:,}")
    print(f"   Vol regime HIGH:   {stats['vol_HIGH']:,}")
    print(f"   Vol regime MEDIUM: {stats['vol_MEDIUM']:,}")
    print(f"   Vol regime LOW:    {stats['vol_LOW']:,}")
    print(f"   MFE mean:          {stats['mfe_mean']:.1f} pips | median: {stats['mfe_median']:.1f} | p90: {stats['mfe_p90']:.1f}")

    analyzer = FeatureAnalyzer(n_estimators=200, max_depth=8)

    # ── MODEL A: MFE Regression ──
    print("\n" + "=" * 70)
    print("📈 MODEL A: MFE REGRESSION — 'How many pips of favorable move?'")
    print("=" * 70)
    mfe_results = analyzer.run_mfe_regression(df, feature_cols)
    if 'error' not in mfe_results:
        print(f"   Samples:    {mfe_results['samples']:,}")
        print(f"   CV R²:      {mfe_results['cv_r2_mean']:.4f} ± {mfe_results['cv_r2_std']:.4f}")
        print(f"   CV MAE:     {mfe_results['cv_mae_mean']:.4f} ATR")
        print(f"   Fold R²:    {mfe_results['cv_r2_scores']}")
        print_importances("Top Features for Predicting MFE", mfe_results['importances'])
    else:
        print(f"   ❌ {mfe_results['error']}")

    # ── MODEL B: Trade Quality ──
    print("\n" + "=" * 70)
    print("🎯 MODEL B: TRADE QUALITY — 'Is this a high-quality setup?'")
    print("=" * 70)
    quality_results = analyzer.run_quality_classification(df, feature_cols)
    if 'error' not in quality_results:
        print(f"   Samples:    {quality_results['samples']:,}")
        print(f"   Classes:    {quality_results['class_distribution']}")
        print(f"   CV Accuracy:{quality_results['cv_accuracy_mean']:.2%} ± {quality_results['cv_accuracy_std']:.2%}")
        print(f"   Fold Scores:{quality_results['cv_scores']}")
        report = quality_results['classification_report']
        for cls in ['HIGH', 'LOW']:
            if cls in report:
                r = report[cls]
                print(f"   {cls:>6}: P={r['precision']:.2%} R={r['recall']:.2%} F1={r['f1-score']:.2%} n={int(r['support'])}")
        print_importances("Top Features for Predicting Trade Quality", quality_results['importances'])
    else:
        print(f"   ❌ {quality_results['error']}")

    # ── MODEL C: Volatility Regime ──
    print("\n" + "=" * 70)
    print("🌊 MODEL C: VOLATILITY REGIME — 'Will volatility expand?'")
    print("=" * 70)
    vol_results = analyzer.run_volatility_prediction(df, feature_cols)
    if 'error' not in vol_results:
        print(f"   Samples:    {vol_results['samples']:,}")
        print(f"   Classes:    {vol_results['class_distribution']}")
        print(f"   CV Accuracy:{vol_results['cv_accuracy_mean']:.2%}")
        print_importances("Top Features for Predicting Volatility", vol_results['importances'])
    else:
        print(f"   ❌ {vol_results['error']}")

    # ── SHAP Analysis ──
    print("\n" + "=" * 70)
    print("🔍 SHAP ANALYSIS — 'HOW does each feature affect MFE?'")
    print("=" * 70)
    if 'model' in mfe_results:
        shap_df = analyzer.run_shap_analysis(df, feature_cols, mfe_results['model'], sample_size=3000)
        print(f"\n  {'Rank':<5}{'Feature':<42}{'|SHAP|':<10}{'Direction':<12}{'Interpretation'}")
        print(f"  {'─' * 75}")
        for i, row in shap_df.head(20).iterrows():
            direction = "↑ Higher=Better" if row['mean_shap'] > 0 else "↓ Higher=Worse"
            print(f"  {i+1:<5}{row['feature']:<42}{row['mean_abs_shap']:<10.4f}{direction:<12}")

    # ── Best vs Worst ──
    print("\n" + "=" * 70)
    print("⚔️  BEST vs WORST TRADES — 'What separates winners from losers?'")
    print("=" * 70)
    bvw = analyzer.run_best_vs_worst(df, feature_cols, top_pct=0.10)
    if not bvw.empty:
        print(f"\n  {'Rank':<5}{'Feature':<42}{'Top 10%':<12}{'Bot 10%':<12}{'Effect':<10}")
        print(f"  {'─' * 75}")
        for i, row in bvw.head(20).iterrows():
            arrow = "▲" if row['effect_size'] > 0 else "▼"
            print(f"  {i+1:<5}{row['feature']:<42}{row['top10_mean']:<12.4f}{row['bottom10_mean']:<12.4f}{arrow} {abs(row['effect_size']):.3f}")

    # ── Stability ──
    print("\n" + "=" * 70)
    print("📊 STABILITY ANALYSIS — 'Are these features stable across time?'")
    print("=" * 70)
    stability = analyzer.run_stability_analysis(df, feature_cols)
    if not stability.empty:
        print(f"\n  {'Rank':<5}{'Feature':<42}{'Mean Imp':<10}{'CV':<8}{'Verdict'}")
        print(f"  {'─' * 70}")
        for i, row in stability.head(15).iterrows():
            cv = row['cv']
            v = "✅ Stable" if cv < 0.3 else ("⚠️ Moderate" if cv < 0.6 else "❌ Unstable")
            print(f"  {i+1:<5}{row['feature']:<42}{row['mean_importance']:<10.4f}{cv:<8.3f}{v}")

    elapsed = time.time() - t0
    print(f"\n⏱️  Research completed in {elapsed:.1f}s")
    print("=" * 70)

    # Save CSVs
    output_dir = 'research_outputs'
    os.makedirs(output_dir, exist_ok=True)
    if 'importances' in mfe_results:
        mfe_results['importances'].to_csv(os.path.join(output_dir, 'research_mfe_importance.csv'), index=False)
    if 'importances' in quality_results:
        quality_results['importances'].to_csv(os.path.join(output_dir, 'research_quality_importance.csv'), index=False)
    if not bvw.empty:
        bvw.to_csv(os.path.join(output_dir, 'research_best_vs_worst.csv'), index=False)
    if 'shap_df' in dir() and shap_df is not None:
        shap_df.to_csv(os.path.join(output_dir, 'research_shap_values.csv'), index=False)
    if not stability.empty:
        stability.to_csv(os.path.join(output_dir, 'research_stability.csv'), index=False)
    print(f"\n💾 All research files saved to {output_dir}/.")


if __name__ == '__main__':
    main()
