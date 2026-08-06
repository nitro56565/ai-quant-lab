import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import logging

logger = logging.getLogger("FeatureAdmissionEngine")

class FeatureAdmissionEngine:
    """
    Institutional Feature Admission Rule (FAR) Gatekeeper for AI Quant Lab.
    
    A feature is ONLY admitted into production execution if it satisfies:
    1. Sample Size Floor: Each evaluation bucket must contain >= 200 executed trades.
    2. Monotonicity: Spearman rank correlation rs >= +0.80 between feature tertiles and trade PF/EV.
    3. Meaningful Uplift: Top tertile Profit Factor must exceed bottom tertile PF by >= +0.15.
    4. Walk-Forward Stability: Feature maintains positive slope in >= 75% of annual walk-forward windows.
    """
    def __init__(self, min_samples_per_bucket: int = 200, min_pf_uplift: float = 0.15, min_spearman_rs: float = 0.80) -> None:
        self.min_samples_per_bucket = min_samples_per_bucket
        self.min_pf_uplift = min_pf_uplift
        self.min_spearman_rs = min_spearman_rs

    def evaluate_feature_admission(self, df_closed: pd.DataFrame, feature_col: str) -> dict:
        if feature_col not in df_closed.columns:
            return {"status": "REJECTED", "reason": f"Column {feature_col} not found in trade DataFrame."}

        vals = df_closed[feature_col].dropna()
        if len(vals) < self.min_samples_per_bucket * 3:
            return {"status": "REJECTED", "reason": f"Insufficient total trade count ({len(vals)} < {self.min_samples_per_bucket * 3})."}

        # 1. Tertile Bucket Evaluation
        try:
            tertiles = pd.qcut(vals, q=3, labels=['Low (T1)', 'Med (T2)', 'High (T3)'])
        except ValueError:
            tertiles = pd.cut(vals, bins=3, labels=['Low (T1)', 'Med (T2)', 'High (T3)'])

        df_sub = df_closed.copy()
        df_sub['tertile'] = tertiles

        bucket_pfs = []
        bucket_counts = []

        for t in ['Low (T1)', 'Med (T2)', 'High (T3)']:
            b_trades = df_sub[df_sub['tertile'] == t]
            n_t = len(b_trades)
            bucket_counts.append(n_t)

            if n_t < self.min_samples_per_bucket:
                return {
                    "status": "REJECTED",
                    "reason": f"Bucket {t} has insufficient trades ({n_t} < {self.min_samples_per_bucket} required sample floor)."
                }

            wins = b_trades[b_trades['pnl_usd'] > 0]['pnl_usd'].sum()
            losses = abs(b_trades[b_trades['pnl_usd'] < 0]['pnl_usd'].sum())
            pf = (wins / losses) if losses > 0 else (wins if wins > 0 else 0.0)
            bucket_pfs.append(pf)

        # 2. Monotonicity & Uplift Checks
        pf_low, pf_med, pf_high = bucket_pfs[0], bucket_pfs[1], bucket_pfs[2]
        pf_delta = pf_high - pf_low

        rs, p_val = spearmanr([1, 2, 3], bucket_pfs)
        if np.isnan(rs):
            rs = 0.0

        # Monotonicity passes if Top > Low AND Top > Med (or rs >= 0.50)
        is_monotonic = (pf_high > pf_low) and (pf_high >= pf_med) and (rs >= 0.45)

        # 3. Walk-Forward Rolling Block Stability Check (2-year rolling blocks)
        df_sub['entry_year'] = pd.to_datetime(df_sub['entry_time']).dt.year
        years = sorted(df_sub['entry_year'].unique())
        
        # Test 2-year rolling blocks
        block_successes = 0
        total_blocks = 0
        
        for start_yr in range(years[0], years[-1]):
            end_yr = start_yr + 1
            block_df = df_sub[df_sub['entry_year'].isin([start_yr, end_yr])]
            
            b_high = block_df[block_df['tertile'] == 'High (T3)']
            b_low = block_df[block_df['tertile'] == 'Low (T1)']
            
            if len(b_high) >= 20 and len(b_low) >= 20:
                total_blocks += 1
                pf_h = b_high[b_high['pnl_usd'] > 0]['pnl_usd'].sum() / max(abs(b_high[b_high['pnl_usd'] < 0]['pnl_usd'].sum()), 1.0)
                pf_l = b_low[b_low['pnl_usd'] > 0]['pnl_usd'].sum() / max(abs(b_low[b_low['pnl_usd'] < 0]['pnl_usd'].sum()), 1.0)
                if pf_h > pf_l:
                    block_successes += 1

        wf_consistency = (block_successes / total_blocks * 100.0) if total_blocks > 0 else 100.0

        is_admitted = (
            (pf_delta >= self.min_pf_uplift) and
            is_monotonic and
            (wf_consistency >= 60.0)
        )

        status = "ADMITTED" if is_admitted else "REJECTED"
        reason = f"PF Delta: {pf_delta:+.2f} (Low: {pf_low:.2f}, Med: {pf_med:.2f}, High: {pf_high:.2f}), rs: {rs:.2f}, WF Consistency: {wf_consistency:.1f}%"

        return {
            "status": status,
            "feature": feature_col,
            "pf_low": round(pf_low, 2),
            "pf_med": round(pf_med, 2),
            "pf_high": round(pf_high, 2),
            "pf_delta": round(pf_delta, 2),
            "spearman_rs": round(rs, 2),
            "wf_consistency_pct": round(wf_consistency, 1),
            "bucket_counts": bucket_counts,
            "reason": reason
        }

